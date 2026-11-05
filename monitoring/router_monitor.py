#!/usr/bin/env python3
"""
Router Health & Interface Monitoring Engine
Monitors Linux Layer 3 Router (r1) health, interface traffic, packet drops,
kernel routing tables, and ICMP connectivity.
Transmits structured router telemetry to Central Monitoring Server.
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
    def __init__(self, router_id="r1", server_ip="10.0.1.20", telemetry_port=5000, poll_interval=2):
        self.router_id = router_id
        self.server_ip = server_ip
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
        """Reads detailed interface statistics for router links (e.g. r1-eth0, r1-eth1)."""
        interfaces = {}
        try:
            # Query ip -j addr or ip link if on Linux
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

        # Fallback/merge with psutil
        ps_stats = get_interface_statistics()
        for iface, data in ps_stats.items():
            if iface not in interfaces:
                interfaces[iface] = data
            else:
                interfaces[iface].update(data)
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
                    # Parse standard text output
                    for line in res.stdout.splitlines():
                        routes.append({"raw": line.strip()})
        except Exception:
            pass
        return routes

    def test_connectivity(self, target_ip="10.0.1.20"):
        """Measures RTT latency and packet loss to target gateway or node."""
        cmd = f"ping -c 2 -W 1 {target_ip} 2>/dev/null || ping -n 2 -w 1000 {target_ip}"
        try:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out = res.stdout
            latency = 0.5
            loss = 0.0

            if "% packet loss" in out or "loss" in out:
                for token in out.split():
                    if "%" in token:
                        try:
                            loss = float(token.replace("%", "").strip())
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
        # Check interfaces
        for iface_name, iface_data in interfaces.items():
            if iface_data.get("state") == "DOWN":
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
            "interfaces": interfaces,
            "routes": routes
        }

    def start_telemetry_loop(self):
        print(f"[{self.router_id}] 📡 Router Health Monitor started -> UDP {self.server_ip}:{self.telemetry_port}")
        while self.running:
            try:
                self.sequence_number += 1
                report = self.collect_full_report()

                # Build TelemetryPacket for central server compatibility
                packet = TelemetryPacket(
                    agent_id=f"Router-{self.router_id}",
                    ip_address="10.0.1.1",
                    c2_port=5004,
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
                    interface_id="r1-eth0,r1-eth1"
                )

                # Send standard packet
                self.udp_sock.sendto(packet.to_bytes(), (self.server_ip, self.telemetry_port))

                # Also send detailed router payload to server router endpoint if needed
            except Exception as e:
                print(f"[{self.router_id}] Router telemetry send error: {e}")
            time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Router Health Monitor")
    parser.add_argument("--router-id", default="r1", help="Router Identifier")
    parser.add_argument("--server-ip", default="10.0.1.20", help="Central Monitoring Server IP")
    parser.add_argument("--telemetry-port", type=int, default=5000, help="UDP Telemetry Port")
    parser.add_argument("--interval", type=int, default=2, help="Polling interval in seconds")
    args = parser.parse_args()

    monitor = RouterMonitor(
        router_id=args.router_id,
        server_ip=args.server_ip,
        telemetry_port=args.telemetry_port,
        poll_interval=args.interval
    )
    monitor.start_telemetry_loop()


if __name__ == "__main__":
    main()

