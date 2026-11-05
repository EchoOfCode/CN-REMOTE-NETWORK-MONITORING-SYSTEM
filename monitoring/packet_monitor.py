#!/usr/bin/env python3
"""
Real-Time Packet Monitor & Ring Buffer Capture Engine
Remote Network Health Monitor — Operator-Controlled NOC

Provides bounded ring-buffer packet logging and statistical sampling across all hops:
  Client -> Switch s1 -> Router 1 -> Transit Link -> Router 2 -> Switch s2 -> Load Balancer -> Backend

Features:
  - Ring buffer of recent packet events (default 500 entries)
  - Packet fields: timestamp, src_ip, dst_ip, src_port, dst_port, protocol, size, interface, status
  - Filterable by source, destination, protocol, interface, status
  - Lightweight statistical counters to avoid memory saturation
"""

import os
import sys
import time
import threading
from datetime import datetime

class PacketMonitor:
    def __init__(self, buffer_size=500):
        self.buffer_size = buffer_size
        self.packet_buffer = []
        self.total_observed = 0
        self.total_dropped = 0
        self.protocol_counts = {"TCP": 0, "UDP": 0, "ICMP": 0, "HTTP": 0}
        self.interface_counts = {}
        self.lock = threading.Lock()

        # Seed initial baseline packets so table renders immediately
        self._seed_baseline_packets()

    def _seed_baseline_packets(self):
        baseline_samples = [
            {"src": "10.0.1.11", "dst": "10.0.1.20", "sport": 5001, "dport": 5000, "proto": "UDP", "size": 248, "intf": "s1", "dir": "INGRESS", "status": "DELIVERED"},
            {"src": "10.0.1.12", "dst": "10.0.1.20", "sport": 5002, "dport": 5000, "proto": "UDP", "size": 248, "intf": "s1", "dir": "INGRESS", "status": "DELIVERED"},
            {"src": "10.0.1.1", "dst": "10.0.12.2", "sport": 0, "dport": 0, "proto": "ICMP", "size": 64, "intf": "r1-eth1", "dir": "TRANSIT", "status": "DELIVERED"},
            {"src": "10.0.12.2", "dst": "10.0.2.30", "sport": 45120, "dport": 8000, "proto": "TCP", "size": 512, "intf": "r2-eth1", "dir": "EGRESS", "status": "DELIVERED"},
            {"src": "10.0.2.30", "dst": "10.0.2.12", "sport": 8000, "dport": 8002, "proto": "HTTP", "size": 1024, "intf": "s2", "dir": "BACKEND", "status": "DELIVERED"}
        ]
        now = datetime.now().strftime("%H:%M:%S")
        for s in baseline_samples:
            self.record_packet(
                src_ip=s["src"], dst_ip=s["dst"],
                src_port=s["sport"], dst_port=s["dport"],
                protocol=s["proto"], packet_size=s["size"],
                interface=s["intf"], direction=s["dir"],
                status=s["status"], timestamp=now
            )

    def record_packet(self, src_ip, dst_ip, src_port=0, dst_port=0, protocol="TCP", packet_size=64, interface="s1", direction="INGRESS", status="DELIVERED", timestamp=None):
        """Records an observed packet in the bounded ring buffer."""
        ts = timestamp or datetime.now().strftime("%H:%M:%S")
        pkt = {
            "timestamp": ts,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "src_port": src_port,
            "dst_port": dst_port,
            "protocol": protocol.upper(),
            "packet_size": packet_size,
            "interface": interface,
            "direction": direction,
            "status": status
        }

        with self.lock:
            self.packet_buffer.insert(0, pkt)
            if len(self.packet_buffer) > self.buffer_size:
                self.packet_buffer.pop()

            self.total_observed += 1
            if status == "DROPPED":
                self.total_dropped += 1

            p_key = protocol.upper()
            self.protocol_counts[p_key] = self.protocol_counts.get(p_key, 0) + 1
            self.interface_counts[interface] = self.interface_counts.get(interface, 0) + 1

    def get_packets(self, limit=50, src_filter=None, dst_filter=None, proto_filter=None, intf_filter=None):
        with self.lock:
            filtered = []
            for p in self.packet_buffer:
                if src_filter and src_filter not in p["src_ip"]:
                    continue
                if dst_filter and dst_filter not in p["dst_ip"]:
                    continue
                if proto_filter and proto_filter.upper() != p["protocol"]:
                    continue
                if intf_filter and intf_filter != p["interface"]:
                    continue
                filtered.append(p)
                if len(filtered) >= limit:
                    break
            return filtered

    def get_summary(self):
        with self.lock:
            loss_rate = round((self.total_dropped / self.total_observed) * 100.0, 2) if self.total_observed > 0 else 0.0
            return {
                "total_observed": self.total_observed,
                "total_dropped": self.total_dropped,
                "loss_rate_percent": loss_rate,
                "protocol_distribution": dict(self.protocol_counts),
                "interface_distribution": dict(self.interface_counts),
                "recent_packet_count": len(self.packet_buffer)
            }

# Global singleton
packet_monitor = PacketMonitor()

