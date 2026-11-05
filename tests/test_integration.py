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

    def test_flask_server_endpoints(self):
        from server import app
        client = app.test_client()

        # 1. Health check
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertIn("TWO_ROUTER_MULTI_SUBNET", res.get_json().get("architecture", ""))

        # 2. Automated Remediation Toggle
        res = client.post("/api/sdn/remediation_toggle", json={"enabled": False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json().get("auto_remediation_enabled"))

        res = client.get("/api/sdn/remediation_status")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json().get("auto_remediation_enabled"))

        # Re-enable
        res = client.post("/api/sdn/remediation_toggle", json={"enabled": True})
        self.assertTrue(res.get_json().get("auto_remediation_enabled"))

        # 3. Two Routers & Transit Link
        res = client.get("/api/routers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("r1", data)
        self.assertIn("r2", data)
        self.assertIn("transit_link", data)

        # 4. Packet Loss Localization
        res = client.get("/api/network/packet_loss")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("overall_loss_percent", data)
        self.assertIn("diagnosis", data)

        # 5. Backend Status & Power Controls
        res = client.get("/api/backend/status")
        self.assertEqual(res.status_code, 200)
        backends = res.get_json()
        self.assertIn("backend-1", backends)
        self.assertIn("backend-2", backends)
        self.assertIn("backend-3", backends)

        # Power OFF Backend 2
        res = client.post("/api/backend/backend-2/power_off")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json().get("power_state"), "OFF")

        # Power ON Backend 2
        res = client.post("/api/backend/backend-2/power_on")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json().get("power_state"), "ON")

if __name__ == '__main__':
    unittest.main()

