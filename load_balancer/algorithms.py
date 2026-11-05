#!/usr/bin/env python3
"""
Load Balancing Algorithms
Implements Round Robin, Least Connections, and Weighted Round Robin selection.
"""

import threading

class LoadBalancingAlgorithm:
    def select(self, backends):
        raise NotImplementedError


class RoundRobinAlgorithm(LoadBalancingAlgorithm):
    def __init__(self):
        self.current_idx = 0
        self.lock = threading.Lock()

    def select(self, backends):
        if not backends:
            return None
        with self.lock:
            selected = backends[self.current_idx % len(backends)]
            self.current_idx = (self.current_idx + 1) % len(backends)
            return selected


class LeastConnectionsAlgorithm(LoadBalancingAlgorithm):
    def select(self, backends):
        if not backends:
            return None
        # Select backend with minimum active_connections; tie-break on total_requests
        return min(backends, key=lambda b: (b.active_connections, b.total_requests))


class WeightedRoundRobinAlgorithm(LoadBalancingAlgorithm):
    """
    Smooth Weighted Round-Robin (Nginx style).
    Distributes requests smoothly according to backend weights.
    """
    def __init__(self):
        self.lock = threading.Lock()

    def select(self, backends):
        if not backends:
            return None
        with self.lock:
            total_weight = sum(b.weight for b in backends)
            best_backend = None

            for b in backends:
                b.current_weight += b.weight
                if best_backend is None or b.current_weight > best_backend.current_weight:
                    best_backend = b

            if best_backend:
                best_backend.current_weight -= total_weight

            return best_backend


def get_algorithm(name):
    name = (name or "").lower().replace("-", "_")
    if name == "least_connections" or name == "least_conn":
        return LeastConnectionsAlgorithm()
    elif name == "weighted_round_robin" or name == "wrr":
        return WeightedRoundRobinAlgorithm()
    else:
        return RoundRobinAlgorithm()
