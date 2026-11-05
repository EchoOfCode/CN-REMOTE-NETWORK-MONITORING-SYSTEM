#!/usr/bin/env python3
"""
Active Asynchronous Health Checker
Polls upstream backends (/health) via aiohttp.
Enforces multi-failure confirmation and multi-success recovery hysteresis.
"""

import asyncio
import aiohttp
import time

class HealthChecker:
    def __init__(self, config, metrics):
        self.config = config
        self.metrics = metrics
        self.running = False
        self.session = None

    async def start(self):
        self.running = True
        timeout = aiohttp.ClientTimeout(total=self.config.health_check_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        print(f"[LB HEALTH] 🩺 Background health checker started (Polling every {self.config.health_check_interval}s)")

        while self.running:
            try:
                tasks = [self._check_backend(backend) for backend in self.config.backends.values()]
                if tasks:
                    await asyncio.gather(*tasks)
            except Exception as e:
                print(f"[LB HEALTH] Health check cycle exception: {e}")
            await asyncio.sleep(self.config.health_check_interval)

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()

    async def _check_backend(self, backend):
        # Skip if backend is intentionally disabled or in manual drain
        if backend.status in ["disabled", "draining"]:
            return

        health_url = f"{backend.url}/health"
        is_healthy = False

        try:
            async with self.session.get(health_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") in ["healthy", "draining"]:
                        is_healthy = True
        except Exception:
            is_healthy = False

        if is_healthy:
            backend.consecutive_failures = 0
            backend.consecutive_successes += 1

            if backend.status == "unhealthy" and backend.consecutive_successes >= self.config.recovery_successes:
                backend.status = "healthy"
                print(f"[LB HEALTH] 🟢 Backend {backend.backend_id} RECOVERED! Reintroduced to rotation.")
                self.metrics.record_failover(backend.backend_id, "RECOVERED_HEALTH_CHECK_PASSED")
        else:
            backend.consecutive_successes = 0
            backend.consecutive_failures += 1

            if backend.status == "healthy" and backend.consecutive_failures >= self.config.max_failures:
                backend.status = "unhealthy"
                print(f"[LB HEALTH] 🔴 Backend {backend.backend_id} FAILED ({backend.consecutive_failures} timeouts)! Removed from rotation.")
                self.metrics.record_failover(backend.backend_id, f"FAILED_HEALTH_CHECK_{backend.consecutive_failures}_CONSECUTIVE_ERRORS")
