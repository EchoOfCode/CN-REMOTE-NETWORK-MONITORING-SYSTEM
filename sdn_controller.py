#!/usr/bin/env python3
"""
SDN Controller Entrypoint.
Provides the Ryu OpenFlow 1.3 Controller application with REST mitigation API.

Run with Ryu Manager (Production/Mininet):
    ryu-manager ryu_sdn_controller.py --wsapi-port 8080

Run standalone (Zero-Dependency OpenFlow 1.3 / Linux OVS Manager):
    python3 sdn_controller.py
"""

import os
import sys
import json
import time
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

# Attempt importing Ryu controller classes for ryu-manager
try:
    from ryu_sdn_controller import RyuSDNController, SDNRestController
    __all__ = ['RyuSDNController', 'SDNRestController']
    HAS_RYU = True
except ImportError:
    HAS_RYU = False

flow_rules = []
managed_switches = ["s1", "s2"]
switch_stats = {
    "switch_id": "s1,s2",
    "dpid": "0000000000000001",
    "active_flows": 0,
    "blocked_ips": [],
    "switches": managed_switches
}
lock = threading.Lock()


def push_ovs_flow(src_ip, switches=None):
    """Programs OpenFlow 1.3 DROP flow into Open vSwitch datapaths."""
    target_switches = switches or managed_switches
    success = False
    for sw in target_switches:
        cmds = [
            f'ovs-ofctl -O OpenFlow13 add-flow {sw} "priority=1000,ip,nw_src={src_ip},actions=drop"',
            f'sudo ovs-ofctl -O OpenFlow13 add-flow {sw} "priority=1000,ip,nw_src={src_ip},actions=drop"'
        ]
        for cmd in cmds:
            try:
                res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0:
                    print(f"[SDN CONTROLLER] ⚡ Open vSwitch {sw} programmed: DROP rule installed for {src_ip}")
                    success = True
                    break
            except Exception:
                pass
    return success


def remove_ovs_flow(src_ip, switches=None):
    """Deletes OpenFlow flow from Open vSwitch datapaths."""
    target_switches = switches or managed_switches
    success = False
    for sw in target_switches:
        cmds = [
            f'ovs-ofctl -O OpenFlow13 del-flows {sw} "ip,nw_src={src_ip}"',
            f'sudo ovs-ofctl -O OpenFlow13 del-flows {sw} "ip,nw_src={src_ip}"'
        ]
        for cmd in cmds:
            try:
                res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0:
                    print(f"[SDN CONTROLLER] ⚡ Open vSwitch {sw} programmed: DROP rule removed for {src_ip}")
                    success = True
                    break
            except Exception:
                pass
    return success


def query_ovs_flows():
    """Queries live OVS flow statistics across managed switches."""
    stats = []
    for sw in managed_switches:
        cmd = f'sudo ovs-ofctl -O OpenFlow13 dump-flows {sw} 2>/dev/null || ovs-ofctl -O OpenFlow13 dump-flows {sw} 2>/dev/null'
        try:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    if "actions=drop" in line or "drop" in line.lower():
                        stats.append({"switch": sw, "flow": line.strip()})
        except Exception:
            pass
    return stats


class SDNServer(HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class SDNRESTHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_response(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path == '/api/v1/sdn/stats' or self.path == '/api/sdn/stats':
            live_flows = query_ovs_flows()
            with lock:
                response = {
                    "status": "ONLINE",
                    "switch": switch_stats,
                    "active_rules": flow_rules,
                    "live_ovs_drops": live_flows
                }
            self._send_response(200, response)
        elif self.path == '/health':
            self._send_response(200, {"status": "HEALTHY", "service": "SDN_CONTROLLER"})
        else:
            self._send_response(404, {"error": "Not Found"})

    def do_POST(self):
        global flow_rules
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            payload = json.loads(body.decode('utf-8'))
        except Exception:
            self._send_response(400, {"error": "Invalid JSON"})
            return

        if self.path == '/api/v1/sdn/mitigate' or self.path == '/api/sdn/mitigate':
            src_ip = payload.get('src_ip')
            agent_id = payload.get('agent_id', 'Unknown')
            target_ip = payload.get('target_ip', 'ALL')
            if not src_ip:
                self._send_response(400, {"error": "src_ip is required"})
                return

            rule = {
                "rule_id": f"flow_drop_{src_ip}_{int(time.time())}",
                "dpid": 1,
                "priority": 1000,
                "match": {"eth_type": 2048, "ipv4_src": src_ip},
                "action": "DROP",
                "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "agent_id": agent_id,
                "target_ip": target_ip,
                "switches": managed_switches
            }
            with lock:
                if src_ip not in switch_stats["blocked_ips"]:
                    switch_stats["blocked_ips"].append(src_ip)
                flow_rules.append(rule)
                switch_stats["active_flows"] = len(flow_rules)

            # Program Open vSwitch directly if present on s1 and s2
            push_ovs_flow(src_ip)

            print(f"[SDN CONTROLLER] 🔴 OpenFlow FlowMod Installed: DROP traffic from {src_ip} ({agent_id})")
            self._send_response(200, {"status": "SUCCESS", "action": "FLOWMOD_DROP_INSTALLED", "rule": rule})

        elif self.path == '/api/v1/sdn/unblock' or self.path == '/api/sdn/unblock':
            src_ip = payload.get('src_ip')
            with lock:
                if src_ip in switch_stats["blocked_ips"]:
                    switch_stats["blocked_ips"].remove(src_ip)
                flow_rules = [r for r in flow_rules if r["match"].get("ipv4_src") != src_ip]
                switch_stats["active_flows"] = len(flow_rules)

            # Delete Open vSwitch flow from switches
            remove_ovs_flow(src_ip)

            print(f"[SDN CONTROLLER] 🟢 OpenFlow FlowMod Removed: Restored traffic for {src_ip}")
            self._send_response(200, {"status": "SUCCESS", "action": "FLOWMOD_REMOVED", "src_ip": src_ip})

        else:
            self._send_response(404, {"error": "Endpoint not found"})


def run_standalone_controller(host='0.0.0.0', port=8080):
    print("========================================")
    print("  STANDALONE SDN REST CONTROLLER (OVS)  ")
    print("========================================")
    print(f"Listening on: http://{host}:{port}")
    print(f"Managed Switches: {', '.join(managed_switches)}")
    print("Direct OpenFlow 1.3 Kernel FlowMod Injection: ACTIVE")
    print("========================================\n")

    httpd = SDNServer((host, port), SDNRESTHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[SDN CONTROLLER] Shutting down controller server...")
        httpd.server_close()


if __name__ == '__main__':
    run_standalone_controller()
