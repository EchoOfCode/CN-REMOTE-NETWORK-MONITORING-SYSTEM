#!/usr/bin/env python3
"""
Load Balancer Real-Time Metrics & Latency Percentile Tracker
"""

import time
import threading
import numpy as np

class LoadBalancerMetrics:
    def __init__(self):
        self.start_time = time.time()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.active_requests = 0
        self.requests_by_backend = {}
        self.latencies = []
        self.failover_events = []
        self.lock = threading.Lock()

    def record_request_start(self, backend_id):
        with self.lock:
            self.total_requests += 1
            self.active_requests += 1
            self.requests_by_backend[backend_id] = self.requests_by_backend.get(backend_id, 0) + 1

    def record_request_end(self, backend_id, latency_ms, success=True):
        with self.lock:
            self.active_requests = max(0, self.active_requests - 1)
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            self.latencies.append(latency_ms)
            if len(self.latencies) > 2000:
                self.latencies.pop(0)

    def record_failover(self, backend_id, reason):
        with self.lock:
            evt = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "backend_id": backend_id,
                "reason": reason
            }
            self.failover_events.append(evt)
            if len(self.failover_events) > 50:
                self.failover_events.pop(0)

    def get_summary(self):
        with self.lock:
            uptime = time.time() - self.start_time
            rps = self.total_requests / uptime if uptime > 0 else 0.0

            if self.latencies:
                sorted_lat = sorted(self.latencies)
                avg_lat = sum(sorted_lat) / len(sorted_lat)
                p50_lat = sorted_lat[int(len(sorted_lat) * 0.50)]
                p95_lat = sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)]
                p99_lat = sorted_lat[min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)]
            else:
                avg_lat = p50_lat = p95_lat = p99_lat = 0.0

            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "active_requests": self.active_requests,
                "requests_per_second": round(rps, 2),
                "latency_ms": {
                    "average": round(avg_lat, 2),
                    "p50": round(p50_lat, 2),
                    "p95": round(p95_lat, 2),
                    "p99": round(p99_lat, 2)
                },
                "traffic_distribution": dict(self.requests_by_backend),
                "failover_events": list(self.failover_events)
            }
