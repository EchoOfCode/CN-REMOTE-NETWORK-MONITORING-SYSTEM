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

if __name__ == '__main__':
    unittest.main()
