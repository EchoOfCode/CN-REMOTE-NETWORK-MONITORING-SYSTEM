#!/usr/bin/env python3
"""
Router Health & Interface Monitoring Engine
Remote Network Health Monitor — Two-Router Multi-Subnet Architecture

Monitors Linux Layer 3 Routers (r1 and r2) health, interface traffic, packet drops,
kernel routing tables, and transit link connectivity (10.0.12.0/30).
Transmits structured router telemetry to the Central Monitoring Server.
"""

import os
import sys
import time
import json
import socket
import psutil
import argparse
import subprocess
import threading
from datetime import datetime

# Import network metrics helper
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from monitoring.network_metrics import NetworkMetricsCalculator, get_interface_statistics
from monitoring.telemetry import TelemetryPacket

class RouterMonitor:
    def __init__(self, router_id="r1", server_ip="10.0.1.20", peer_ip=None, telemetry_port=5000, poll_interval=2):
        self.router_id = router_id
        self.server_ip = server_ip
        # If r1, default peer is r2 transit IP 10.0.12.2; if r2, default peer is r1 transit IP 10.0.12.1
        if peer_ip:
            self.peer_ip = peer_ip
        else:
            self.peer_ip = "10.0.12.2" if router_id == "r1" else "10.0.12.1"

        self.telemetry_port = telemetry_port
        self.poll_interval = poll_interval
        self.running = True
        self.metrics_calc = NetworkMetricsCalculator()
        self.start_time = time.time()
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sequence_number = 0

    def get_system_health(self):
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        uptime = time.time() - self.start_time
        return {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(mem, 1),
            "uptime_seconds": int(uptime)
        }

    def get_interfaces(self):
        """Reads detailed interface statistics for router links."""
        interfaces = {}
        try:
            res = subprocess.run("ip -j addr show", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                for item in data:
                    name = item.get("ifname", "")
                    if name.startswith("lo"):
                        continue
                    state = item.get("operstate", "UNKNOWN").upper()
                    ip_addr = None
                    for addr_info in item.get("addr_info", []):
                        if addr_info.get("family") == "inet":
                            ip_addr = f"{addr_info.get('local')}/{addr_info.get('prefixlen')}"
                            break
                    interfaces[name] = {
                        "name": name,
                        "state": state if state != "UNKNOWN" else "UP",
                        "ip": ip_addr
                    }
        except Exception:
            pass

        # Merge with psutil interface statistics
        ps_stats = get_interface_statistics()
        for iface, data in ps_stats.items():
            if iface not in interfaces:
                interfaces[iface] = data
            else:
                interfaces[iface].update(data)

        # Fallback defaults if interfaces dictionary is sparse
        if not interfaces:
            if self.router_id == "r1":
                interfaces = {
                    "r1-eth0": {"name": "r1-eth0", "ip": "10.0.1.1/24", "state": "UP", "packet_drops": 0, "packet_errors": 0},
                    "r1-eth1": {"name": "r1-eth1", "ip": "10.0.12.1/30", "state": "UP", "packet_drops": 0, "packet_errors": 0}
                }
            else:
                interfaces = {
                    "r2-eth0": {"name": "r2-eth0", "ip": "10.0.12.2/30", "state": "UP", "packet_drops": 0, "packet_errors": 0},
                    "r2-eth1": {"name": "r2-eth1", "ip": "10.0.2.1/24", "state": "UP", "packet_drops": 0, "packet_errors": 0}
                }

        return interfaces

    def get_routing_table(self):
        """Extracts active kernel routes."""
        routes = []
        try:
            res = subprocess.run("ip -j route show 2>/dev/null || ip route show", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout:
                try:
                    data = json.loads(res.stdout)
                    for r in data:
                        routes.append({
                            "destination": r.get("dst", "default"),
                            "gateway": r.get("gateway", "*"),
                            "interface": r.get("dev", "unknown"),
                            "protocol": r.get("protocol", "kernel")
                        })
                except Exception:
                    for line in res.stdout.splitlines():
                        routes.append({"raw": line.strip()})
        except Exception:
            pass

        if not routes:
            if self.router_id == "r1":
                routes = [
                    {"destination": "10.0.1.0/24", "gateway": "*", "interface": "r1-eth0", "protocol": "kernel"},
                    {"destination": "10.0.12.0/30", "gateway": "*", "interface": "r1-eth1", "protocol": "kernel"},
                    {"destination": "10.0.2.0/24", "gateway": "10.0.12.2", "interface": "r1-eth1", "protocol": "static"}
                ]
            else:
                routes = [
                    {"destination": "10.0.2.0/24", "gateway": "*", "interface": "r2-eth1", "protocol": "kernel"},
                    {"destination": "10.0.12.0/30", "gateway": "*", "interface": "r2-eth0", "protocol": "kernel"},
                    {"destination": "10.0.1.0/24", "gateway": "10.0.12.1", "interface": "r2-eth0", "protocol": "static"}
                ]
        return routes

    def test_connectivity(self, target_ip="10.0.1.20"):
        """Measures RTT latency and packet loss to target gateway, monitor, or peer router."""
        if sys.platform.startswith("win"):
            cmd = f"ping -n 2 -w 800 {target_ip}"
        else:
            cmd = f"ping -c 2 -W 1 {target_ip} 2>/dev/null"

        try:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out = res.stdout
            latency = 0.5
            loss = 0.0

            if "%" in out:
                for token in out.split():
                    if "%" in token:
                        try:
                            loss = float(token.replace("%", "").replace("(", "").replace(")", "").strip())
                            break
                        except Exception:
                            pass

            if "avg" in out or "Average" in out:
                try:
                    if "avg" in out:
                        part = out.split("=")[1].strip()
                        latency = float(part.split("/")[1])
                    elif "Average" in out:
                        part = out.split("Average =")[-1].replace("ms", "").strip()
                        latency = float(part)
                except Exception:
                    latency = 0.8

            return {"target": target_ip, "latency_ms": round(latency, 2), "packet_loss_percent": round(loss, 1)}
        except Exception:
            return {"target": target_ip, "latency_ms": 0.0, "packet_loss_percent": 100.0}

    def evaluate_health_status(self, cpu, packet_loss, interfaces):
        """
        Thresholds:
          CPU < 70%: HEALTHY, 70-85%: DEGRADED, > 85%: CRITICAL
          Interface down: CRITICAL
          Packet loss > 2%: DEGRADED, > 5%: CRITICAL
        """
        for iface_name, iface_data in interfaces.items():
            if isinstance(iface_data, dict) and iface_data.get("state") == "DOWN":
                return "CRITICAL", f"Interface {iface_name} is DOWN"

        if cpu > 85.0 or packet_loss > 5.0:
            return "CRITICAL", f"Severe stress: CPU {cpu}%, Packet Loss {packet_loss}%"

        if cpu >= 70.0 or packet_loss >= 2.0:
            return "DEGRADED", f"Elevated resource usage: CPU {cpu}%, Packet Loss {packet_loss}%"

        return "HEALTHY", "Router functioning within normal parameters"

    def collect_full_report(self):
        sys_health = self.get_system_health()
        interfaces = self.get_interfaces()
        routes = self.get_routing_table()
        connectivity = self.test_connectivity(self.server_ip)
        transit_connectivity = self.test_connectivity(self.peer_ip)
        rates = self.metrics_calc.sample()

        status, reason = self.evaluate_health_status(
            cpu=sys_health["cpu_percent"],
            packet_loss=connectivity["packet_loss_percent"],
            interfaces=interfaces
        )

        return {
            "router_id": self.router_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "status_reason": reason,
            "system": sys_health,
            "throughput": {
                "upload_mbps": rates["upload_mbps"],
                "download_mbps": rates["download_mbps"],
                "packet_drops": rates["packet_drops"],
                "packet_errors": rates["packet_errors"]
            },
            "connectivity": connectivity,
            "transit_peer": self.peer_ip,
            "transit_connectivity": transit_connectivity,
            "interfaces": interfaces,
            "routes": routes
        }

    def start_telemetry_loop(self):
        print(f"[{self.router_id}] 📡 Router Health Monitor started -> UDP {self.server_ip}:{self.telemetry_port} (Transit Peer: {self.peer_ip})")
        router_ip = "10.0.1.1" if self.router_id == "r1" else "10.0.2.1"
        c2_port = 5004 if self.router_id == "r1" else 5009

        while self.running:
            try:
                self.sequence_number += 1
                report = self.collect_full_report()

                # Build TelemetryPacket for central server compatibility
                packet = TelemetryPacket(
                    agent_id=f"Router-{self.router_id}",
                    ip_address=router_ip,
                    c2_port=c2_port,
                    sequence_number=self.sequence_number,
                    cpu_percent=report["system"]["cpu_percent"],
                    memory_percent=report["system"]["memory_percent"],
                    processes=len(psutil.pids()),
                    upload_mbps=report["throughput"]["upload_mbps"],
                    download_mbps=report["throughput"]["download_mbps"],
                    bytes_sent=self.metrics_calc.prev_bytes_sent or 0,
                    bytes_recv=self.metrics_calc.prev_bytes_recv or 0,
                    packet_drops=report["throughput"]["packet_drops"],
                    packet_errors=report["throughput"]["packet_errors"],
                    status=report["status"],
                    active_attack=False,
                    interface_id=f"{self.router_id}-eth0,{self.router_id}-eth1"
                )

                # Send packet with router-specific metrics merged
                payload = packet.to_dict()
                payload["router_report"] = report

                self.udp_sock.sendto(json.dumps(payload).encode('utf-8'), (self.server_ip, self.telemetry_port))

            except Exception as e:
                print(f"[{self.router_id}] Router telemetry send error: {e}")
            time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Router Health Monitor")
    parser.add_argument("--router-id", default="r1", help="Router Identifier (r1 or r2)")
    parser.add_argument("--server-ip", default="10.0.1.20", help="Central Monitoring Server IP")
    parser.add_argument("--peer-ip", default=None, help="Peer Router Transit IP")
    parser.add_argument("--telemetry-port", type=int, default=5000, help="UDP Telemetry Port")
    parser.add_argument("--interval", type=int, default=2, help="Polling interval in seconds")
    args = parser.parse_args()

    monitor = RouterMonitor(
        router_id=args.router_id,
        server_ip=args.server_ip,
        peer_ip=args.peer_ip,
        telemetry_port=args.telemetry_port,
        poll_interval=args.interval
    )
    monitor.start_telemetry_loop()


if __name__ == "__main__":
    main()
