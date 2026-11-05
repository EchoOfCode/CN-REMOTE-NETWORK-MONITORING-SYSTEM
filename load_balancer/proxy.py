#!/usr/bin/env python3
"""
Custom Asynchronous HTTP Load Balancer & Reverse Proxy
Built using Python asyncio and aiohttp.
Part of the Remote Network Health Monitor Platform.
"""

import os
import sys
import time
import asyncio
import argparse
from aiohttp import web, ClientSession, ClientTimeout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from load_balancer.config import LoadBalancerConfig
from load_balancer.algorithms import get_algorithm
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.health_checker import HealthChecker

# Hop-by-hop headers that should not be forwarded
HOP_BY_HOP = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade'
}


class ReverseProxy:
    def __init__(self, config):
        self.config = config
        self.metrics = LoadBalancerMetrics()
        self.algorithm = get_algorithm(config.algorithm)
        self.health_checker = HealthChecker(self.config, self.metrics)
        self.client_session = None

    async def init_session(self, app):
        timeout = ClientTimeout(total=self.config.request_timeout)
        self.client_session = ClientSession(timeout=timeout)
        asyncio.create_task(self.health_checker.start())

    async def cleanup_session(self, app):
        await self.health_checker.stop()
        if self.client_session:
            await self.client_session.close()

    # --- ADMIN / CONTROL ENDPOINTS ---

    async def handle_status(self, request):
        return web.json_response({
            "status": "ONLINE",
            "service": "LOAD_BALANCER",
            "config": self.config.to_dict(),
            "metrics": self.metrics.get_summary()
        })

    async def handle_metrics(self, request):
        return web.json_response(self.metrics.get_summary())

    async def handle_set_algorithm(self, request):
        try:
            data = await request.json()
            new_algo = data.get("algorithm")
            if new_algo in ["round_robin", "least_connections", "weighted_round_robin"]:
                self.config.algorithm = new_algo
                self.algorithm = get_algorithm(new_algo)
                print(f"[LOAD BALANCER] 🔄 Switched algorithm to: {new_algo}")
                return web.json_response({"status": "SUCCESS", "algorithm": new_algo})
            return web.json_response({"error": "Invalid algorithm. Use round_robin, least_connections, or weighted_round_robin"}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def handle_backend_power_off(self, request):
        bid = request.match_info.get("id")
        backend = self.config.backends.get(bid)
        if backend:
            backend.power_off()
            self.metrics.record_failover(bid, "MANUAL_POWER_OFF")
            print(f"[LOAD BALANCER] 🛑 Backend {bid} powered OFF. Recalculated traffic shares: {self.config.get_traffic_shares()}")
            return web.json_response({
                "status": "SUCCESS",
                "backend": backend.to_dict(),
                "traffic_shares": self.config.get_traffic_shares()
            })
        return web.json_response({"error": "Backend not found"}, status=404)

    async def handle_backend_power_on(self, request):
        bid = request.match_info.get("id")
        backend = self.config.backends.get(bid)
        if backend:
            backend.power_on()
            self.metrics.record_failover(bid, "MANUAL_POWER_ON")
            print(f"[LOAD BALANCER] 🟢 Backend {bid} powered ON. Recalculated traffic shares: {self.config.get_traffic_shares()}")
            return web.json_response({
                "status": "SUCCESS",
                "backend": backend.to_dict(),
                "traffic_shares": self.config.get_traffic_shares()
            })
        return web.json_response({"error": "Backend not found"}, status=404)

    async def handle_backend_drain(self, request):
        bid = request.match_info.get("id")
        backend = self.config.backends.get(bid)
        if backend:
            backend.status = "draining"
            self.metrics.record_failover(bid, "MANUAL_DRAIN_INITIATED")
            return web.json_response({"status": "SUCCESS", "backend": backend.to_dict()})
        return web.json_response({"error": "Backend not found"}, status=404)

    async def handle_backend_restore(self, request):
        bid = request.match_info.get("id")
        backend = self.config.backends.get(bid)
        if backend:
            backend.status = "healthy"
            backend.consecutive_failures = 0
            self.metrics.record_failover(bid, "MANUAL_RESTORE_INITIATED")
            return web.json_response({"status": "SUCCESS", "backend": backend.to_dict()})
        return web.json_response({"error": "Backend not found"}, status=404)

    async def handle_backend_weight(self, request):
        bid = request.match_info.get("id")
        backend = self.config.backends.get(bid)
        if backend:
            data = await request.json()
            weight = int(data.get("weight", 1))
            backend.weight = max(1, weight)
            return web.json_response({"status": "SUCCESS", "backend": backend.to_dict()})
        return web.json_response({"error": "Backend not found"}, status=404)

    # --- REVERSE PROXY FORWARDING ---

    async def forward_request(self, request):
        path = request.path
        if path.startswith("/lb/"):
            # Route internal control commands
            if path == "/lb/status":
                return await self.handle_status(request)
            elif path == "/lb/metrics":
                return await self.handle_metrics(request)
            elif path == "/lb/algorithm":
                return await self.handle_set_algorithm(request)
            elif "/drain" in path:
                return await self.handle_backend_drain(request)
            elif "/restore" in path:
                return await self.handle_backend_restore(request)
            elif "/weight" in path:
                return await self.handle_backend_weight(request)

        # 1. Select eligible healthy backend
        healthy_backends = self.config.get_healthy_backends()
        if not healthy_backends:
            return web.json_response({
                "error": "503 Service Unavailable",
                "message": "All backend servers are unhealthy or unreachable"
            }, status=503)

        backend = self.algorithm.select(healthy_backends)
        if not backend:
            return web.json_response({"error": "No backend available"}, status=503)

        # 2. Track connection concurrency
        backend.active_connections += 1
        backend.total_requests += 1
        self.metrics.record_request_start(backend.backend_id)
        start_time = time.time()

        # 3. Clean headers
        req_headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
        req_headers['X-Forwarded-For'] = request.remote or '127.0.0.1'
        req_headers['X-Forwarded-Proto'] = request.scheme

        body = await request.read()
        target_url = f"{backend.url}{request.rel_url}"

        try:
            async with self.client_session.request(
                method=request.method,
                url=target_url,
                headers=req_headers,
                data=body if body else None,
                allow_redirects=False
            ) as resp:
                resp_body = await resp.read()
                latency_ms = (time.time() - start_time) * 1000.0

                resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP}
                resp_headers['X-Served-By'] = backend.backend_id
                resp_headers['X-Served-Host'] = backend.host
                resp_headers['X-Load-Balancer-Algorithm'] = self.config.algorithm
                resp_headers['X-Response-Time-Ms'] = str(round(latency_ms, 2))

                self.metrics.record_request_end(backend.backend_id, latency_ms, success=True)
                return web.Response(status=resp.status, body=resp_body, headers=resp_headers)

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            self.metrics.record_request_end(backend.backend_id, latency_ms, success=False)
            return web.json_response({
                "error": "502 Bad Gateway",
                "backend_id": backend.backend_id,
                "message": f"Upstream proxy failed to connect: {e}"
            }, status=502)

        finally:
            backend.active_connections = max(0, backend.active_connections - 1)


def create_app(config):
    proxy = ReverseProxy(config)
    app = web.Application()
    app.on_startup.append(proxy.init_session)
    app.on_cleanup.append(proxy.cleanup_session)

    # Route all incoming requests to forward_request
    app.router.add_route('*', '/{path:.*}', proxy.forward_request)
    return app


def main():
    parser = argparse.ArgumentParser(description="Custom Async HTTP Load Balancer")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8000, help="Listen port")
    parser.add_argument("--algo", default="round_robin", help="Balancing algorithm (round_robin, least_connections, weighted_round_robin)")
    args = parser.parse_args()

    config = LoadBalancerConfig(host=args.host, port=args.port, algorithm=args.algo)
    # Register the 3 backend instances on Subnet 2 (10.0.2.11, 10.0.2.12, 10.0.2.13)
    # Also support localhost ports 8001, 8002, 8003 for local simulation
    config.add_backend("backend-1", "10.0.2.11", 8001, weight=1)
    config.add_backend("backend-2", "10.0.2.12", 8002, weight=2)
    config.add_backend("backend-3", "10.0.2.13", 8003, weight=1)

    print("========================================")
    print(" ⚖️ CUSTOM ASYNC HTTP LOAD BALANCER")
    print("========================================")
    print(f"Listening on: http://{args.host}:{args.port}")
    print(f"Algorithm:    {args.algo}")
    print(f"Registered Backends:")
    for b in config.backends.values():
        print(f"  - {b.backend_id} -> {b.url} (Weight: {b.weight})")
    print("========================================\n")

    app = create_app(config)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

