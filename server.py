import os
import sys
import time
import json
import socket
import urllib.request
import threading
from flask import Flask, render_template, jsonify, request

# Ensure db module can be imported
sys.path.insert(0, os.path.dirname(__file__))
import db

app = Flask(__name__, template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "templates")))

# Server Configuration
UDP_TELEMETRY_PORT = 5000
SDN_CONTROLLER_URL = "http://127.0.0.1:8080"
NODE_TIMEOUT = 12
C2_SHARED_SECRET = os.getenv("C2_SECRET_TOKEN", "sdn_cn_c2_token_secret_2026")

# In-memory registry of active agents
active_nodes = {}
node_lock = threading.Lock()

# Initialize DB Schema
db.create_database()


def send_c2_command(agent_ip, c2_port, payload):
    try:
        # Inject shared authentication secret into all C2 commands
        payload["token"] = C2_SHARED_SECRET
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((agent_ip, c2_port))
        s.sendall(json.dumps(payload).encode('utf-8'))
        response = s.recv(4096)
        s.close()
        return json.loads(response.decode('utf-8'))
    except Exception as e:
        return {"status": "ERROR", "message": f"C2 Connection failed: {e}"}


def sdn_mitigate_api(src_ip, agent_id="Unknown"):
    try:
        req_data = json.dumps({"src_ip": src_ip, "agent_id": agent_id}).encode('utf-8')
        req = urllib.request.Request(
            f"{SDN_CONTROLLER_URL}/api/v1/sdn/mitigate",
            data=req_data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            db.log_sdn_event(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                agent_id,
                "AUTOMATED_SDN_MITIGATION",
                f"Pushed OpenFlow DROP rule for src_ip {src_ip}",
                "INSTALLED"
            )
            return res
    except Exception as e:
        print(f"[SDN Integration Error] Could not connect to SDN controller: {e}")
        return {"status": "WARNING", "message": "SDN Controller unreachable"}


def udp_telemetry_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_TELEMETRY_PORT))
    print(f"[SERVER] 📡 Listening for Agent Health Telemetry on UDP port {UDP_TELEMETRY_PORT}")

    while True:
        try:
            raw_data, addr = sock.recvfrom(4096)
            data = json.loads(raw_data.decode('utf-8'))

            agent_id = data.get("agent_id")
            ip_address = data.get("ip_address", addr[0])
            c2_port = data.get("c2_port", 5001)

            with node_lock:
                # Detect byte spikes for anomaly alert
                prev_node = active_nodes.get(agent_id, {})
                prev_sent = prev_node.get("bytes_sent", 0)
                sent_delta = data.get("bytes_sent", 0) - prev_sent

                # Anomaly check: high packet flood or explicit attack status
                if (sent_delta > 2000000 or data.get("status") == "ATTACKING") and not prev_node.get("sdn_mitigated"):
                    print(f"[ANOMALY DETECTED] High traffic flood from {agent_id} ({ip_address})! Triggering SDN Mitigation...")
                    sdn_mitigate_api(ip_address, agent_id)
                    data["sdn_mitigated"] = True

                data["last_seen"] = time.time()
                data["c2_port"] = c2_port
                active_nodes[agent_id] = data

            # Save to Database
            db.insert_data(
                agent_id=data.get("agent_id"),
                ip_address=ip_address,
                timestamp=data.get("timestamp"),
                cpu=data.get("cpu_percent"),
                memory=data.get("memory_percent"),
                processes=data.get("processes"),
                sent=data.get("bytes_sent"),
                received=data.get("bytes_recv"),
                status=data.get("status"),
                active_attack=data.get("active_attack", False)
            )

        except Exception as e:
            pass


def node_liveness_checker():
    while True:
        time.sleep(4)
        now = time.time()
        with node_lock:
            for agent_id in list(active_nodes.keys()):
                if now - active_nodes[agent_id].get("last_seen", 0) > NODE_TIMEOUT:
                    active_nodes[agent_id]["status"] = "DOWN"


# --- FLASK API ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/metrics")
def get_metrics():
    with node_lock:
        nodes = list(active_nodes.values())
    
    # Query SDN Controller Stats
    sdn_stats = {"status": "OFFLINE", "active_rules": []}
    try:
        with urllib.request.urlopen(f"{SDN_CONTROLLER_URL}/api/v1/sdn/stats", timeout=1) as resp:
            sdn_stats = json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass

    return jsonify({
        "nodes": nodes,
        "sdn": sdn_stats,
        "db_history": db.get_recent_telemetry(limit=20)
    })


@app.route("/api/attack/start", methods=["POST"])
def start_attack():
    req = request.json or {}
    agent_id = req.get("agent_id")
    c2_port = req.get("c2_port", 5001)
    duration = req.get("duration", 15)

    with node_lock:
        node = active_nodes.get(agent_id)

    agent_ip = node.get("ip_address", "127.0.0.1") if node else "127.0.0.1"

    payload = {
        "command": "START_ATTACK",
        "target_ip": "10.0.0.4",
        "target_port": 8080,
        "duration": duration,
        "packet_size": 1024
    }

    res = send_c2_command(agent_ip, c2_port, payload)
    return jsonify(res)


@app.route("/api/attack/stop", methods=["POST"])
def stop_attack():
    req = request.json or {}
    agent_id = req.get("agent_id")
    c2_port = req.get("c2_port", 5001)

    with node_lock:
        node = active_nodes.get(agent_id)

    agent_ip = node.get("ip_address", "127.0.0.1") if node else "127.0.0.1"
    res = send_c2_command(agent_ip, c2_port, {"command": "STOP_ATTACK"})
    return jsonify(res)


@app.route("/api/campaign/start", methods=["POST"])
def start_sequential_campaign():
    def campaign_worker():
        with node_lock:
            nodes = list(active_nodes.values())

        if not nodes:
            print("[CAMPAIGN] No connected agents found for campaign execution.")
            return

        print(f"[CAMPAIGN] 🚀 Starting Sequential Attack Campaign on {len(nodes)} nodes...")
        for node in nodes:
            agent_id = node.get("agent_id")
            c2_port = node.get("c2_port", 5001)
            agent_ip = node.get("ip_address", "127.0.0.1")

            print(f"[CAMPAIGN] 💣 Step: Attacking via {agent_id} for 10 seconds...")
            send_c2_command(agent_ip, c2_port, {
                "command": "START_ATTACK",
                "target_ip": "10.0.0.4",
                "target_port": 8080,
                "duration": 10
            })
            time.sleep(12)  # Wait for attack cycle to complete before moving to next node

        print("[CAMPAIGN] ✅ Sequential Campaign Completed!")

    threading.Thread(target=campaign_worker, daemon=True).start()
    return jsonify({"status": "SUCCESS", "message": "Sequential Attack Campaign launched across nodes."})


@app.route("/api/sdn/mitigate", methods=["POST"])
def manual_sdn_mitigate():
    req = request.json or {}
    src_ip = req.get("src_ip")
    agent_id = req.get("agent_id", "Manual")
    res = sdn_mitigate_api(src_ip, agent_id)
    return jsonify(res)


@app.route("/api/sdn/unblock", methods=["POST"])
def manual_sdn_unblock():
    req = request.json or {}
    src_ip = req.get("src_ip")
    try:
        req_data = json.dumps({"src_ip": src_ip}).encode('utf-8')
        req = urllib.request.Request(
            f"{SDN_CONTROLLER_URL}/api/v1/sdn/unblock",
            data=req_data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)})


def run_server():
    # Start UDP listener & Liveness threads
    threading.Thread(target=udp_telemetry_listener, daemon=True).start()
    threading.Thread(target=node_liveness_checker, daemon=True).start()

    print("========================================")
    print("  CENTRAL MONITORING & C2 WEB SERVER    ")
    print("========================================")
    print("Web Dashboard: http://127.0.0.1:5050")
    print("UDP Telemetry Port: 5000")
    print("========================================\n")

    app.run(host="0.0.0.0", port=5050, debug=False)


if __name__ == "__main__":
    run_server()