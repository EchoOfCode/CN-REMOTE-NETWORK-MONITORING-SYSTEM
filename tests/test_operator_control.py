#!/usr/bin/env python3
"""
Unit & Integration Tests for Operator Control Plane
Remote Network Health Monitor — Operator-Controlled NOC
"""

import unittest
import json
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from server import app
from control.operation_manager import operation_manager
from control.node_manager import node_manager
from control.router_manager import router_manager
from control.switch_manager import switch_manager
from control.link_manager import link_manager
from traffic.traffic_manager import traffic_manager
from monitoring.packet_monitor import packet_monitor

class TestOperatorControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_system_status_and_health(self):
        resp = self.client.get('/api/system/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("overall_status", data)
        self.assertIn("components", data)

    def test_node_lifecycle_controls(self):
        # 1. Inspect node details
        resp = self.client.get('/api/nodes/h1/details')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["node_id"], "h1")
        self.assertIn("ip", data)

        # 2. Isolate node
        resp = self.client.post('/api/nodes/h1/isolate')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

        # 3. Restore node
        resp = self.client.post('/api/nodes/h1/restore')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

        # 4. Power off and on backend
        resp = self.client.post('/api/nodes/h5/power_off')
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post('/api/nodes/h5/power_on')
        self.assertEqual(resp.status_code, 200)

    def test_router_controls(self):
        # 1. Router details
        resp = self.client.get('/api/routers/r1/details')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["router_id"], "r1")
        self.assertIn("r1-eth0", data["interfaces"])

        # 2. Interface action DOWN
        resp = self.client.post('/api/routers/r1/interfaces/r1-eth0/down')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

        # 3. Interface action UP
        resp = self.client.post('/api/routers/r1/interfaces/r1-eth0/up')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

    def test_switch_controls(self):
        # 1. Switches list
        resp = self.client.get('/api/switches')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("s1", data)
        self.assertIn("s2", data)

        # 2. Flow table dump
        resp = self.client.get('/api/switches/s1/flows')
        self.assertEqual(resp.status_code, 200)
        self.assertIn("flows", resp.get_json())

        # 3. Switch port action
        resp = self.client.post('/api/switches/s1/ports/s1-eth1/down')
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post('/api/switches/s1/ports/s1-eth1/up')
        self.assertEqual(resp.status_code, 200)

    def test_link_controls(self):
        # 1. Configure link impairment
        resp = self.client.post('/api/links/r1-r2/configure', json={
            "loss_percent": 15.0,
            "delay_ms": 25.0,
            "jitter_ms": 5.0,
            "rate_mbps": 50.0
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "SUCCESS")

        # 2. Verify link status
        resp = self.client.get('/api/links/r1-r2')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["loss_percent"], 15.0)

        # 3. Reset link
        resp = self.client.post('/api/links/r1-r2/reset')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

    def test_traffic_generation_and_capture(self):
        # 1. Start Ping job
        resp = self.client.post('/api/traffic/ping/start', json={
            "source": "h1",
            "destination": "127.0.0.1",
            "count": 2,
            "interval": 0.2
        })
        self.assertEqual(resp.status_code, 200)
        job = resp.get_json()
        job_id = job["job_id"]

        # 2. Inspect active traffic jobs
        resp = self.client.get('/api/traffic/jobs')
        self.assertEqual(resp.status_code, 200)
        jobs = resp.get_json()
        self.assertTrue(any(j["job_id"] == job_id for j in jobs))

        # 3. Stop all jobs
        resp = self.client.post('/api/traffic/stop-all')
        self.assertEqual(resp.status_code, 200)

        # 4. Packet summary & capture query
        resp = self.client.get('/api/packets/summary')
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_observed", resp.get_json())

        resp = self.client.get('/api/packets/capture?limit=10')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)

    def test_recovery_and_diagnostics(self):
        # 1. Full system recovery
        resp = self.client.post('/api/recovery/execute')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "SUCCESS")

        # 2. Operations audit
        resp = self.client.get('/api/operations?limit=10')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)

        # 3. Diagnostics snapshot
        resp = self.client.get('/api/diagnostics')
        self.assertEqual(resp.status_code, 200)
        self.assertIn("report_timestamp", resp.get_json())

        # 4. Diagnostics CSV export
        resp = self.client.get('/api/diagnostics/export.csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
        self.assertIn("Timestamp,Component,Event", resp.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()

