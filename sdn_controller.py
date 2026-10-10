#!/usr/bin/env python3
"""
SDN Controller Entrypoint.
Provides the Ryu OpenFlow 1.3 Controller application with REST mitigation API.

Run with Ryu Manager:
    ryu-manager ryu_sdn_controller.py --wsapi-port 8080
    (or: ryu-manager sdn_controller.py --wsapi-port 8080)
"""

try:
    from ryu_sdn_controller import RyuSDNController, SDNRestController
    __all__ = ['RyuSDNController', 'SDNRestController']
except ImportError:
    # Fallback only when Ryu is not installed (e.g. non-Linux / development environment)
    import json
    import time
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    flow_rules = []
    switch_stats = {
        "switch_id": "s1",
        "dpid": "0000000000000001",
        "active_flows": 0,
        "blocked_ips": []
    }
    lock = threading.Lock()

    class SDNRESTHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send_response(self, code, data):
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))

        def do_GET(self):
            if self.path == '/api/v1/sdn/stats':
                with lock:
                    response = {
                        "status": "ONLINE",
                        "switch": switch_stats,
                        "active_rules": flow_rules
                    }
                self._send_response(200, response)
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

            if self.path == '/api/v1/sdn/mitigate':
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
                    "target_ip": target_ip
                }
                with lock:
                    if src_ip not in switch_stats["blocked_ips"]:
                        switch_stats["blocked_ips"].append(src_ip)
                    flow_rules.append(rule)
                    switch_stats["active_flows"] = len(flow_rules)

                self._send_response(200, {"status": "SUCCESS", "action": "FLOWMOD_DROP_INSTALLED", "rule": rule})
            elif self.path == '/api/v1/sdn/unblock':
                src_ip = payload.get('src_ip')
                with lock:
                    if src_ip in switch_stats["blocked_ips"]:
                        switch_stats["blocked_ips"].remove(src_ip)
                    flow_rules = [r for r in flow_rules if r["match"].get("ipv4_src") != src_ip]
                    switch_stats["active_flows"] = len(flow_rules)
                self._send_response(200, {"status": "SUCCESS", "action": "FLOWMOD_REMOVED", "src_ip": src_ip})
            else:
                self._send_response(404, {"error": "Endpoint not found"})

    def run_sdn_controller(port=8080):
        print("[NOTICE] Ryu not installed in current environment. Running standalone REST mock.")
        server = HTTPServer(('0.0.0.0', port), SDNRESTHandler)
        server.serve_forever()

    if __name__ == '__main__':
        run_sdn_controller()
