#!/usr/bin/env python3
"""
Unit Tests for Packet Loss Detection & Localization Engine
"""

import unittest
from monitoring.packet_loss import PacketLossDetector

class TestPacketLossLocalization(unittest.TestCase):
    def setUp(self):
        self.detector = PacketLossDetector()

    def test_healthy_baseline_zero_loss(self):
        res = self.detector.evaluate_loss_state(
            router1={"throughput": {"packet_drops": 0}},
            router2={"throughput": {"packet_drops": 0}},
            nodes=[{"agent_id": "Node-1", "status": "NORMAL"}],
            simulated_drops={"transit_link": 0.0}
        )
        self.assertEqual(res["overall_loss_percent"], 0.0)
        self.assertEqual(res["packets_lost_per_100"], 0)
        self.assertEqual(res["diagnosis"]["severity"], "NORMAL")
        self.assertIn("0%", res["diagnosis"]["explanation"])

    def test_transit_link_loss_localization(self):
        res = self.detector.evaluate_loss_state(
            router1={"throughput": {"packet_drops": 24}},
            router2={"throughput": {"packet_drops": 0}},
            nodes=[{"agent_id": "Node-1", "status": "NORMAL"}],
            simulated_drops={"transit_link": 24.0}
        )
        self.assertEqual(res["overall_loss_percent"], 24.0)
        self.assertEqual(res["packets_lost_per_100"], 24)
        self.assertIn("Router 1 to Router 2", res["diagnosis"]["location"])
        self.assertIn("24 out of every 100", res["diagnosis"]["explanation"])
        self.assertEqual(res["diagnosis"]["severity"], "CRITICAL")

    def test_backend_loss_localization_on_down_server(self):
        nodes = [
            {"agent_id": "Backend-1", "status": "NORMAL"},
            {"agent_id": "Backend-2", "status": "DOWN"},
            {"agent_id": "Backend-3", "status": "NORMAL"}
        ]
        res = self.detector.evaluate_loss_state(
            router1={"throughput": {"packet_drops": 0}},
            router2={"throughput": {"packet_drops": 0}},
            nodes=nodes,
            simulated_drops={}
        )
        self.assertGreater(res["overall_loss_percent"], 10.0)
        self.assertIn("Backend Server Cluster", res["diagnosis"]["location"])
        self.assertIn("backend servers", res["diagnosis"]["explanation"].lower())

if __name__ == '__main__':
    unittest.main()

