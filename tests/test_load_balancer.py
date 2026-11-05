#!/usr/bin/env python3
"""
Unit Tests for Load Balancer Algorithms & Health Checks
"""

import unittest
from load_balancer.config import BackendConfig, LoadBalancerConfig
from load_balancer.algorithms import RoundRobinAlgorithm, LeastConnectionsAlgorithm, WeightedRoundRobinAlgorithm

class TestLoadBalancer(unittest.TestCase):
    def setUp(self):
        self.b1 = BackendConfig("b1", "10.0.2.11", 8001, weight=1)
        self.b2 = BackendConfig("b2", "10.0.2.12", 8002, weight=2)
        self.b3 = BackendConfig("b3", "10.0.2.13", 8003, weight=1)
        self.backends = [self.b1, self.b2, self.b3]

    def test_round_robin_distribution(self):
        rr = RoundRobinAlgorithm()
        # 6 sequential selections across 3 backends
        selections = [rr.select(self.backends).backend_id for _ in range(6)]
        self.assertEqual(selections, ["b1", "b2", "b3", "b1", "b2", "b3"])

    def test_least_connections_selection(self):
        lc = LeastConnectionsAlgorithm()
        self.b1.active_connections = 5
        self.b2.active_connections = 1
        self.b3.active_connections = 3

        selected = lc.select(self.backends)
        self.assertEqual(selected.backend_id, "b2")

        self.b2.active_connections = 10
        selected_next = lc.select(self.backends)
        self.assertEqual(selected_next.backend_id, "b3")

    def test_weighted_round_robin_proportion(self):
        wrr = WeightedRoundRobinAlgorithm()
        # b1: weight 1, b2: weight 2, b3: weight 1 (Total: 4)
        # In 8 rounds, b2 should receive exactly 4 requests (50%)
        counts = {"b1": 0, "b2": 0, "b3": 0}
        for _ in range(8):
            chosen = wrr.select(self.backends)
            counts[chosen.backend_id] += 1

        self.assertEqual(counts["b2"], 4)
        self.assertEqual(counts["b1"], 2)
        self.assertEqual(counts["b3"], 2)

    def test_power_off_and_traffic_shares(self):
        cfg = LoadBalancerConfig()
        cfg.add_backend("b1", "10.0.2.11", 8001, weight=1)
        cfg.add_backend("b2", "10.0.2.12", 8002, weight=1)
        cfg.add_backend("b3", "10.0.2.13", 8003, weight=1)

        # Baseline: 3 healthy backends -> 33.3% each
        shares = cfg.get_traffic_shares()
        self.assertEqual(shares["b1"], 33.3)
        self.assertEqual(shares["b2"], 33.3)
        self.assertEqual(shares["b3"], 33.3)

        # Power OFF b2 -> b2 is excluded, b1 and b3 get 50% each!
        cfg.backends["b2"].power_off()
        self.assertEqual(cfg.backends["b2"].power_state, "OFF")
        self.assertEqual(cfg.backends["b2"].status, "offline")

        shares_after = cfg.get_traffic_shares()
        self.assertEqual(shares_after["b2"], 0.0)
        self.assertEqual(shares_after["b1"], 50.0)
        self.assertEqual(shares_after["b3"], 50.0)

        # Power ON b2 -> restored to 33.3%
        cfg.backends["b2"].power_on()
        self.assertEqual(cfg.backends["b2"].power_state, "ON")
        self.assertEqual(cfg.backends["b2"].status, "healthy")
        shares_restored = cfg.get_traffic_shares()
        self.assertEqual(shares_restored["b2"], 33.3)

if __name__ == '__main__':
    unittest.main()

