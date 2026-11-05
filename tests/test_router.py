#!/usr/bin/env python3
"""
Unit Tests for Router Health Classification & Metrics
"""

import unittest
from monitoring.router_monitor import RouterMonitor

class TestRouterHealth(unittest.TestCase):
    def setUp(self):
        self.router = RouterMonitor(router_id="r1", server_ip="127.0.0.1")

    def test_health_classification_normal(self):
        interfaces = {"r1-eth0": {"state": "UP"}, "r1-eth1": {"state": "UP"}}
        status, reason = self.router.evaluate_health_status(cpu=15.0, packet_loss=0.0, interfaces=interfaces)
        self.assertEqual(status, "HEALTHY")

    def test_health_classification_degraded_cpu(self):
        interfaces = {"r1-eth0": {"state": "UP"}, "r1-eth1": {"state": "UP"}}
        status, reason = self.router.evaluate_health_status(cpu=78.0, packet_loss=0.0, interfaces=interfaces)
        self.assertEqual(status, "DEGRADED")

    def test_health_classification_critical_cpu(self):
        interfaces = {"r1-eth0": {"state": "UP"}, "r1-eth1": {"state": "UP"}}
        status, reason = self.router.evaluate_health_status(cpu=92.0, packet_loss=0.0, interfaces=interfaces)
        self.assertEqual(status, "CRITICAL")

    def test_health_classification_interface_down(self):
        interfaces = {"r1-eth0": {"state": "UP"}, "r1-eth1": {"state": "DOWN"}}
        status, reason = self.router.evaluate_health_status(cpu=20.0, packet_loss=0.0, interfaces=interfaces)
        self.assertEqual(status, "CRITICAL")
        self.assertIn("DOWN", reason)

    def test_health_classification_packet_loss(self):
        interfaces = {"r1-eth0": {"state": "UP"}, "r1-eth1": {"state": "UP"}}
        status_deg, _ = self.router.evaluate_health_status(cpu=10.0, packet_loss=3.0, interfaces=interfaces)
        self.assertEqual(status_deg, "DEGRADED")
        status_crit, _ = self.router.evaluate_health_status(cpu=10.0, packet_loss=8.0, interfaces=interfaces)
        self.assertEqual(status_crit, "CRITICAL")

if __name__ == '__main__':
    unittest.main()
