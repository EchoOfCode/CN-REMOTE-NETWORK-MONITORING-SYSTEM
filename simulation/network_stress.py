#!/usr/bin/env python3
"""
Controlled Network Throughput Stress Simulation Engine
Generates bandwidth spikes using iperf3 or high-frequency socket burst streams.
Traverses Mininet virtual switches and router to demonstrate real traffic spikes.
"""

import os
import sys
import time
import socket
import argparse
import subprocess
import threading

def run_network_stress(target_ip="10.0.1.20", target_port=5201, bandwidth_mbps=50, duration=10, protocol="UDP"):
    """
    Generates controlled network load toward target_ip for duration seconds.
    """
    duration = min(max(2, duration), 30)
    print(f"[SIMULATION]  Generating {bandwidth_mbps} Mbps {protocol} traffic surge to {target_ip}:{target_port} for {duration}s...")

    # Check for iperf3
    res = subprocess.run("which iperf3", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        proto_flag = "-u" if protocol.upper() == "UDP" else ""
        cmd = f"iperf3 -c {target_ip} -p {target_port} {proto_flag} -b {bandwidth_mbps}M -t {duration} --json"
        try:
            out = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=duration + 3)
            if out.returncode == 0:
                print("[SIMULATION] ✅ iperf3 stress test finished successfully.")
                return {"status": "SUCCESS", "engine": "iperf3", "target": target_ip, "mbps": bandwidth_mbps, "duration": duration}
        except Exception:
            pass

    # High-throughput socket burst fallback
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if protocol.upper() == "UDP" else socket.SOCK_STREAM)
    payload = b"N" * 1400  # Standard MTU payload
    end_time = time.time() + duration
    bytes_sent = 0

    try:
        if protocol.upper() == "TCP":
            sock.settimeout(2.0)
            sock.connect((target_ip, target_port))

        while time.time() < end_time:
            # Batch packets
            for _ in range(30):
                sock.sendto(payload, (target_ip, target_port)) if protocol.upper() == "UDP" else sock.sendall(payload)
                bytes_sent += len(payload)
            time.sleep(0.002)

    except Exception as e:
        print(f"[SIMULATION] Socket burst completed with condition: {e}")
    finally:
        sock.close()

    mb_sent = bytes_sent / (1024 * 1024.0)
    actual_mbps = (bytes_sent * 8.0) / (duration * 1_000_000.0)
    print(f"[SIMULATION] ✅ Socket burst complete: {mb_sent:.2f} MB transmitted ({actual_mbps:.2f} Mbps effective).")
    return {
        "status": "SUCCESS",
        "engine": "socket_stream",
        "target": target_ip,
        "total_mb_sent": round(mb_sent, 2),
        "effective_mbps": round(actual_mbps, 2),
        "duration": duration
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Network Traffic Stress Simulator")
    parser.add_argument("--target", default="10.0.1.20", help="Target IP address")
    parser.add_argument("--port", type=int, default=5000, help="Target Port")
    parser.add_argument("--mbps", type=int, default=50, help="Target bandwidth in Mbps")
    parser.add_argument("--duration", type=int, default=10, help="Duration in seconds")
    parser.add_argument("--proto", default="UDP", help="Protocol: UDP or TCP")
    args = parser.parse_args()

    run_network_stress(
        target_ip=args.target,
        target_port=args.port,
        bandwidth_mbps=args.mbps,
        duration=args.duration,
        protocol=args.proto
    )
