#!/usr/bin/env python3
"""
Lightweight Backend HTTP Microservice
Part of the Remote Network Health Monitor Platform.
Runs inside backend hosts (h5, h6, h7) in Mininet.

Endpoints:
  GET  /               -> Returns backend identity and service status
  GET  /health         -> Active health check endpoint
  GET  /metrics        -> Request throughput and latency metrics
  GET  /simulate-work  -> Bounded workload simulator for load balancing benchmarks
  POST /admin/status   -> Admin control to simulate failures (healthy/unhealthy/draining)
"""

import sys
import time
import json
import socket
import argparse
import threading
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class BackendState:
    def __init__(self, backend_id, hostname, port):
        self.backend_id = backend_id
        self.hostname = hostname
        self.port = port
        self.status = "healthy"  # healthy, unhealthy, draining
        self.start_time = time.time()
        self.total_requests = 0
        self.active_requests = 0
        self.failed_requests = 0
        self.latencies = []
        self.lock = threading.Lock()

    def record_request_start(self):
        with self.lock:
            self.total_requests += 1
            self.active_requests += 1

    def record_request_end(self, duration_sec, success=True):
        with self.lock:
            self.active_requests = max(0, self.active_requests - 1)
            if not success:
                self.failed_requests += 1
            self.latencies.append(duration_sec * 1000.0)
            if len(self.latencies) > 500:
                self.latencies.pop(0)

    def get_metrics(self):
        with self.lock:
            uptime = time.time() - self.start_time
            avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0
            rps = self.total_requests / uptime if uptime > 0 else 0.0
            return {
                "backend_id": self.backend_id,
                "hostname": self.hostname,
                "port": self.port,
                "status": self.status,
                "uptime_seconds": round(uptime, 1),
                "total_requests": self.total_requests,
                "active_requests": self.active_requests,
                "failed_requests": self.failed_requests,
                "average_latency_ms": round(avg_latency, 2),
                "requests_per_second": round(rps, 2)
            }


class BackendRequestHandler(BaseHTTPRequestHandler):
    server_version = "BackendService/1.0"

    def log_message(self, format, *args):
        pass  # Suppress default request logging to avoid terminal clutter

    def _send_json(self, status_code, data, extra_headers=None):
        payload = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Backend-Id", self.server.state.backend_id)
        self.send_header("X-Backend-Host", self.server.state.hostname)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        start_time = time.time()

        state = self.server.state
        state.record_request_start()

        try:
            if path == "/health":
                if state.status == "healthy":
                    self._send_json(200, {
                        "status": "healthy",
                        "backend_id": state.backend_id,
                        "hostname": state.hostname,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                elif state.status == "draining":
                    self._send_json(200, {
                        "status": "draining",
                        "backend_id": state.backend_id,
                        "message": "Backend is draining existing connections"
                    })
                else:
                    self._send_json(503, {
                        "status": "unhealthy",
                        "backend_id": state.backend_id,
                        "error": "Backend marked unhealthy by simulation or error"
                    })

            elif path == "/metrics":
                self._send_json(200, state.get_metrics())

            elif path == "/simulate-work":
                ms = int(query.get("ms", [10])[0])
                burn_cpu = query.get("cpu", ["false"])[0].lower() in ["true", "1"]
                
                # Bounded workload
                if burn_cpu:
                    end_burn = time.time() + (ms / 1000.0)
                    while time.time() < end_burn:
                        _ = 3.14159 * 2.71828
                else:
                    time.sleep(ms / 1000.0)

                self._send_json(200, {
                    "backend_id": state.backend_id,
                    "hostname": state.hostname,
                    "simulated_ms": ms,
                    "status": state.status,
                    "request_count": state.total_requests
                })

            elif path == "/" or path == "/api" or path == "/api/info":
                self._send_json(200, {
                    "backend_id": state.backend_id,
                    "hostname": state.hostname,
                    "status": state.status,
                    "request_count": state.total_requests,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": f"Processed request successfully on {state.backend_id} ({state.hostname})"
                })

            else:
                self._send_json(404, {"error": "Not Found", "backend_id": state.backend_id})

            duration = time.time() - start_time
            state.record_request_end(duration, success=True)

        except Exception as e:
            duration = time.time() - start_time
            state.record_request_end(duration, success=False)
            self._send_json(500, {"error": str(e), "backend_id": state.backend_id})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        state = self.server.state

        if path == "/admin/status":
            try:
                content_len = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_len) if content_len > 0 else b'{}'
                data = json.loads(body.decode('utf-8'))
                new_status = data.get("status")
                if new_status in ["healthy", "unhealthy", "draining"]:
                    with state.lock:
                        state.status = new_status
                    self._send_json(200, {"status": "SUCCESS", "new_status": new_status, "backend_id": state.backend_id})
                else:
                    self._send_json(400, {"error": "Invalid status. Use healthy, unhealthy, or draining"})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Endpoint not found"})


def run_backend(backend_id="backend-1", host="0.0.0.0", port=8001):
    hostname = socket.gethostname()
    state = BackendState(backend_id=backend_id, hostname=hostname, port=port)
    server = ThreadedHTTPServer((host, port), BackendRequestHandler)
    server.state = state

    print(f"[{backend_id}] 🚀 Backend service online at http://{host}:{port} (Hostname: {hostname})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{backend_id}] Shutting down backend service...")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backend HTTP Microservice")
    parser.add_argument("--id", default="backend-1", help="Backend identifier")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    parser.add_argument("--port", type=int, default=8001, help="Listen port")
    args = parser.parse_args()

    run_backend(backend_id=args.id, host=args.host, port=args.port)
