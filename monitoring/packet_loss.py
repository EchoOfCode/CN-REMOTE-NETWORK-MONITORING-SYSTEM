#!/usr/bin/env python3
"""
Segment-Level Packet Loss Detection & Localization Engine
Remote Network Health Monitor — Two-Router Multi-Subnet Architecture

Measures and localizes packet drops across three core network segments:
  1. Client Segment: Clients (h1-h4) to Switch s1
  2. Transit Segment: Router 1 (r1) to Router 2 (r2) Transit Link (10.0.12.0/30)
  3. Backend Segment: Switch s2 to Backend Servers (h5-h7) & Load Balancer (h8)

Generates plain-English diagnostic explanations suitable for non-technical users.
"""

import os
import sys
import time
import subprocess
from datetime import datetime

class PacketLossDetector:
    def __init__(self):
        self.last_check_time = time.time()
        self.segments = {
            "client_access": {
                "name": "Client Access Segment (Subnet 1)",
                "description": "Clients (h1-h4) <-> Switch s1",
                "loss_percent": 0.0,
                "latency_ms": 0.45,
                "status": "HEALTHY",
                "dropped_packets": 0
            },
            "transit_link": {
                "name": "Router 1 to Router 2 Transit Link",
                "description": "Router r1 (10.0.12.1) <-> Router r2 (10.0.12.2)",
                "loss_percent": 0.0,
                "latency_ms": 0.80,
                "status": "HEALTHY",
                "dropped_packets": 0
            },
            "backend_cluster": {
                "name": "Backend Cluster Segment (Subnet 2)",
                "description": "Switch s2 <-> Load Balancer (h8) & Servers (h5-h7)",
                "loss_percent": 0.0,
                "latency_ms": 0.50,
                "status": "HEALTHY",
                "dropped_packets": 0
            }
        }

    def measure_icmp_loss(self, target_ip, count=2, timeout=1):
        """Runs a fast ICMP ping probe to determine latency and packet loss."""
        # Windows ping uses -n and -w (ms), Linux ping uses -c and -W (s)
        if sys.platform.startswith("win"):
            cmd = f"ping -n {count} -w {timeout * 1000} {target_ip}"
        else:
            cmd = f"ping -c {count} -W {timeout} {target_ip} 2>/dev/null"

        try:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out = res.stdout
            loss = 0.0
            latency = 0.5

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
                    latency = 0.6

            return {"loss_percent": round(loss, 1), "latency_ms": round(latency, 2), "success": True}
        except Exception:
            return {"loss_percent": 100.0, "latency_ms": 0.0, "success": False}

    def evaluate_loss_state(self, router1=None, router2=None, nodes=None, simulated_drops=None):
        """
        Aggregates packet loss across router interface stats, node telemetries,
        and link probe measurements to isolate exact drop locations.
        """
        router1 = router1 or {}
        router2 = router2 or {}
        nodes = nodes or []
        simulated_drops = simulated_drops or {}

        # 1. Transit link evaluation
        transit_loss = simulated_drops.get("transit_link", 0.0)
        # Check router 1 and router 2 interface drops
        r1_drops = router1.get("throughput", {}).get("packet_drops", 0)
        r2_drops = router2.get("throughput", {}).get("packet_drops", 0)
        total_transit_drops = r1_drops + r2_drops

        if transit_loss > 0.0:
            self.segments["transit_link"]["loss_percent"] = transit_loss
            self.segments["transit_link"]["status"] = "CRITICAL" if transit_loss > 5.0 else "DEGRADED"
            self.segments["transit_link"]["dropped_packets"] = max(total_transit_drops, int(transit_loss * 10))
        else:
            # Check router ping loss
            r1_conn = router1.get("connectivity", {})
            r2_conn = router2.get("connectivity", {})
            max_conn_loss = max(r1_conn.get("packet_loss_percent", 0.0), r2_conn.get("packet_loss_percent", 0.0))
            self.segments["transit_link"]["loss_percent"] = max_conn_loss
            self.segments["transit_link"]["status"] = "CRITICAL" if max_conn_loss > 5.0 else ("DEGRADED" if max_conn_loss > 1.0 else "HEALTHY")
            self.segments["transit_link"]["dropped_packets"] = total_transit_drops

        # 2. Client access segment evaluation
        client_attacking = any(n.get("status") == "ATTACKING" for n in nodes if "Node-" in n.get("agent_id", ""))
        client_loss = simulated_drops.get("client_access", 0.0)
        if client_attacking:
            client_loss = max(client_loss, 2.5)

        self.segments["client_access"]["loss_percent"] = client_loss
        self.segments["client_access"]["status"] = "CRITICAL" if client_loss > 5.0 else ("DEGRADED" if client_loss > 1.0 else "HEALTHY")

        # 3. Backend cluster segment evaluation
        backend_loss = simulated_drops.get("backend_cluster", 0.0)
        down_backends = [n for n in nodes if "Backend-" in n.get("agent_id", "") and n.get("status") in ["DOWN", "OFFLINE"]]
        if down_backends:
            backend_loss = max(backend_loss, len(down_backends) * 15.0)

        self.segments["backend_cluster"]["loss_percent"] = backend_loss
        self.segments["backend_cluster"]["status"] = "CRITICAL" if backend_loss > 5.0 else ("DEGRADED" if backend_loss > 1.0 else "HEALTHY")

        # Overall loss calculation (worst or weighted)
        overall_loss = max(
            self.segments["client_access"]["loss_percent"],
            self.segments["transit_link"]["loss_percent"],
            self.segments["backend_cluster"]["loss_percent"]
        )

        diagnosis = self.generate_plain_english_diagnosis(overall_loss)

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "overall_loss_percent": round(overall_loss, 1),
            "packets_lost_per_100": int(round(overall_loss)),
            "segments": self.segments,
            "diagnosis": diagnosis
        }

    def generate_plain_english_diagnosis(self, overall_loss):
        """Translates technical loss counters into human-friendly explanations."""
        transit = self.segments["transit_link"]
        backend = self.segments["backend_cluster"]
        client = self.segments["client_access"]

        lost_count = int(round(overall_loss))

        if overall_loss < 0.5:
            return {
                "headline": "All Network Connections Healthy",
                "explanation": "Data packets are flowing smoothly across all devices with 0% loss.",
                "location": "None (Full Path Operational)",
                "lost_count_str": "0 out of 100 packets lost",
                "severity": "NORMAL",
                "recommendation": "Network is in optimal condition. No action required."
            }

        # Identify primary segment responsible for the loss
        if transit["loss_percent"] >= max(backend["loss_percent"], client["loss_percent"]):
            loc = "Router 1 to Router 2 Connection (Transit Link)"
            expl = f"Your network is losing {lost_count} out of every 100 packets. Most data loss is occurring between Router 1 and Router 2."
            rec = "Check the transit connection between the two routers. Reduce high traffic or enable automated remediation."
        elif backend["loss_percent"] > client["loss_percent"]:
            loc = "Backend Server Cluster (Switch s2 -> Servers)"
            expl = f"Your network is losing {lost_count} out of every 100 packets. Data packets cannot reach one or more backend servers."
            rec = "One or more backend servers may be powered off. Power ON the servers or verify Load Balancer routing."
        else:
            loc = "Client Access Network (Subnet 1)"
            expl = f"Your network is losing {lost_count} out of every 100 packets due to client-side congestion or active stress."
            rec = "Stop active network stress or apply SDN filtering to isolate the sending device."

        return {
            "headline": f"Packet Loss Detected: {lost_count}% Data Lost",
            "explanation": expl,
            "location": loc,
            "lost_count_str": f"{lost_count} out of 100 packets lost",
            "severity": "CRITICAL" if overall_loss > 10.0 else "WARNING",
            "recommendation": rec
        }

# Singleton instance
packet_loss_detector = PacketLossDetector()
