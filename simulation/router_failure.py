#!/usr/bin/env python3
"""
Router Interface Failure & Recovery Simulation Engine
Simulates router link degradation and failure by toggling interface operational states.
"""

import sys
import time
import argparse
import subprocess

def toggle_router_interface(interface="r1-eth1", state="down", duration=10):
    state = state.lower()
    print(f"[ROUTER SIM] ⚠️ Simulating router failure: setting interface {interface} to {state.upper()}...")

    cmds = [
        f"ip link set dev {interface} {state}",
        f"sudo ip link set dev {interface} {state}"
    ]
    success = False
    for cmd in cmds:
        res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            success = True
            break

    if success:
        print(f"    ✔ Interface {interface} is now {state.upper()}. Cross-subnet connectivity interrupted.")
        if state == "down" and duration > 0:
            print(f"    -> Waiting {duration}s before automated recovery...")
            time.sleep(duration)
            toggle_router_interface(interface=interface, state="up", duration=0)
            return {"status": "SUCCESS", "interface": interface, "recovered": True}
        return {"status": "SUCCESS", "interface": interface, "state": state}
    else:
        print(f"    Notice: Interface command requires root or Mininet namespace execution.")
        return {"status": "SKIPPED", "interface": interface, "reason": "Requires root or Mininet namespace"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Router Interface Failure Simulator")
    parser.add_argument("--interface", default="r1-eth1", help="Router interface name")
    parser.add_argument("--state", choices=["down", "up"], default="down", help="Interface state")
    parser.add_argument("--duration", type=int, default=10, help="Duration in seconds before auto-restore")
    args = parser.parse_args()

    toggle_router_interface(interface=args.interface, state=args.state, duration=args.duration)

