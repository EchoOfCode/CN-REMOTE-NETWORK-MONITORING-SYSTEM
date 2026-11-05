#!/usr/bin/env python3
"""
Integration Tests: Load Balancer Proxy + Upstream Backends
"""

import time
import socket
import threading
import unittest
from backend.app import BackendState, ThreadedHTTPServer, BackendRequestHandler
from load_balancer.config import LoadBalancerConfig
from load_balancer.algorithms import RoundRobinAlgorithm
import urllib.request
import json

class TestLoadBalancerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start a test backend server on port 8991
        cls.state1 = BackendState("test-b1", "localhost", 8991)
        cls.server1 = ThreadedHTTPServer(("127.0.0.1", 8991), BackendRequestHandler)
        cls.server1.state = cls.state1
        cls.t1 = threading.Thread(target=cls.server1.serve_forever, daemon=True)
        cls.t1.start()

        # Start a test backend server on port 8992
        cls.state2 = BackendState("test-b2", "localhost", 8992)
        cls.server2 = ThreadedHTTPServer(("127.0.0.1", 8992), BackendRequestHandler)
        cls.server2.state = cls.state2
        cls.t2 = threading.Thread(target=cls.server2.serve_forever, daemon=True)
        cls.t2.start()

        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server1.shutdown()
        cls.server2.shutdown()

    def test_backend_direct_health_and_metrics(self):
        with urllib.request.urlopen("http://127.0.0.1:8991/health", timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(resp.status, 200)
            self.assertEqual(data.get("status"), "healthy")
            self.assertEqual(data.get("backend_id"), "test-b1")

        with urllib.request.urlopen("http://127.0.0.1:8992/health", timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(resp.status, 200)
            self.assertEqual(data.get("status"), "healthy")
            self.assertEqual(data.get("backend_id"), "test-b2")

    def test_backend_admin_status_failover(self):
        # Mark backend 1 unhealthy
        req_data = json.dumps({"status": "unhealthy"}).encode('utf-8')
        req = urllib.request.Request("http://127.0.0.1:8991/admin/status", data=req_data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            self.assertEqual(resp.status, 200)

        # Query /health -> Must now return 503
        try:
            urllib.request.urlopen("http://127.0.0.1:8991/health", timeout=2)
            self.fail("Expected HTTP 503 from unhealthy backend")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)

        # Restore backend 1
        req_data = json.dumps({"status": "healthy"}).encode('utf-8')
        req = urllib.request.Request("http://127.0.0.1:8991/admin/status", data=req_data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            self.assertEqual(resp.status, 200)

if __name__ == '__main__':
    unittest.main()
