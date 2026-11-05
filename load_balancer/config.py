#!/usr/bin/env python3
"""
Load Balancer Configuration & Backend Target Definitions
Supports dynamic power control (POWER ON / POWER OFF) and traffic redistribution.
"""

class BackendConfig:
    def __init__(self, backend_id, host, port, weight=1):
        self.backend_id = backend_id
        self.host = host
        self.port = port
        self.weight = max(1, weight)
        self.status = "healthy"  # healthy, unhealthy, draining, offline
        self.power_state = "ON"  # ON, OFF
        self.active_connections = 0
        self.total_requests = 0
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.current_weight = 0  # Used in smooth weighted round robin

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    def power_off(self):
        self.power_state = "OFF"
        self.status = "offline"

    def power_on(self):
        self.power_state = "ON"
        self.status = "healthy"
        self.consecutive_failures = 0

    def to_dict(self):
        return {
            "backend_id": self.backend_id,
            "host": self.host,
            "port": self.port,
            "weight": self.weight,
            "status": self.status,
            "power_state": self.power_state,
            "active_connections": self.active_connections,
            "total_requests": self.total_requests,
            "consecutive_failures": self.consecutive_failures,
            "url": self.url
        }


class LoadBalancerConfig:
    def __init__(self, host="0.0.0.0", port=8000, algorithm="round_robin"):
        self.host = host
        self.port = port
        self.algorithm = algorithm  # round_robin, least_connections, weighted_round_robin
        self.health_check_interval = 2.0  # seconds
        self.health_check_timeout = 1.0   # seconds
        self.request_timeout = 5.0        # seconds
        self.max_failures = 3             # fail threshold
        self.recovery_successes = 2       # recovery threshold
        self.backends = {}

    def add_backend(self, backend_id, host, port, weight=1):
        self.backends[backend_id] = BackendConfig(backend_id, host, port, weight)

    def get_healthy_backends(self):
        # Eligible backends: healthy AND powered ON
        return [b for b in self.backends.values() if b.status == "healthy" and b.power_state == "ON"]

    def get_traffic_shares(self):
        """Calculates expected percentage distribution across all backends."""
        healthy = self.get_healthy_backends()
        shares = {}
        total_weight = sum(b.weight for b in healthy) if healthy else 0

        for bid, b in self.backends.items():
            if b.status == "healthy" and b.power_state == "ON":
                if self.algorithm == "weighted_round_robin" and total_weight > 0:
                    pct = round((b.weight / total_weight) * 100.0, 1)
                else:
                    pct = round(100.0 / len(healthy), 1) if healthy else 0.0
                shares[bid] = pct
            else:
                shares[bid] = 0.0

        return shares

    def to_dict(self):
        healthy_list = self.get_healthy_backends()
        return {
            "host": self.host,
            "port": self.port,
            "algorithm": self.algorithm,
            "health_check_interval": self.health_check_interval,
            "healthy_backend_count": len(healthy_list),
            "total_backends": len(self.backends),
            "traffic_shares": self.get_traffic_shares(),
            "backends": {bid: b.to_dict() for bid, b in self.backends.items()}
        }
