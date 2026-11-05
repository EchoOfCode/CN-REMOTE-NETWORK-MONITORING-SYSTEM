#!/usr/bin/env python3
"""
Central Ingestion, Orchestration & Web Control Plane
Remote Network Health Monitor — Industry-Grade Network Operations Platform
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import threading
from flask import Flask, render_template, jsonify, request

# Ensure local packages are importable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import db
from monitoring.anomaly_detector import AnomalyDetector
from services.event_manager import event_manager
from simulation.cpu_stress import run_cpu_stress, stop_all_cpu_stress
from simulation.network_stress import run_network_stress
from simulation.node_failure import simulate_backend_failure, restore_backend

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))

# Server Configuration
UDP_TELEMETRY_PORT = 5000
NODE_TIMEOUT = 12
C2_SHARED_SECRET = os.getenv("C2_SECRET_TOKEN", "sdn_cn_c2_token_secret_2026")
LB_URL = os.getenv("LB_URL", "http://10.0.1.30:8000")

# In-memory registry & anomaly detector
active_nodes = {}
router_state = {
    "router_id": "r1",
    "status": "HEALTHY",
    "system": {"cpu_percent": 4.2, "memory_percent": 18.5, "uptime_seconds": 120},
    "throughput": {"upload_mbps": 0.45, "download_mbps": 0.38, "packet_drops": 0, "packet_errors": 0},
    "connectivity": {"target": "10.0.1.20", "latency_ms": 0.45, "packet_loss_percent": 0.0},
    "interfaces": {
        "r1-eth0": {"name": "r1-eth0", "ip": "10.0.1.1/24", "state": "UP"},
        "r1-eth1": {"name": "r1-eth1", "ip": "10.0.2.1/24", "state": "UP"}
    },
    "routes": [
        {"destination": "10.0.1.0/24", "gateway": "*", "interface": "r1-eth0", "protocol": "kernel"},
        {"destination": "10.0.2.0/24", "gateway": "*", "interface": "r1-eth1", "protocol": "kernel"}
    ],
    "last_seen": time.time()
}

node_lock = threading.Lock()
anomaly_engine = AnomalyDetector()

# Initialize DB Schema
db.create_database()


def get_sdn_controller_url():
    """Dynamically probes Mininet bridge IP (10.0.1.254/10.0.0.254:8080) and local loopback."""
    candidates = [
        os.getenv("SDN_CONTROLLER_URL"),
        "http://10.0.1.254:8080",
        "http://10.0.0.254:8080",
        "http://127.0.0.1:8080"
    ]
    for url in candidates:
        if not url:
            continue
        try:
            req = urllib.request.Request(f"{url}/api/v1/sdn/stats")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                return url
        except Exception:
            pass
    return os.getenv("SDN_CONTROLLER_URL", "http://10.0.1.254:8080")


def send_c2_command(agent_ip, c2_port, payload):
    try:
        payload["token"] = C2_SHARED_SECRET
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4)
        s.connect((agent_ip, c2_port))
        s.sendall(json.dumps(payload).encode('utf-8'))
        response = s.recv(4096)
        s.close()
        return json.loads(response.decode('utf-8'))
    except Exception as e:
        return {"status": "ERROR", "message": f"C2 Connection failed: {e}"}


def sdn_mitigate_api(src_ip, agent_id="Unknown"):
    controller_url = get_sdn_controller_url()
    try:
        req_data = json.dumps({"src_ip": src_ip, "agent_id": agent_id}).encode('utf-8')
        req = urllib.request.Request(
            f"{controller_url}/api/v1/sdn/mitigate",
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
        print(f"[SDN Error] Could not connect to SDN controller at {controller_url}: {e}")
        return {"status": "WARNING", "message": f"SDN Controller unreachable at {controller_url}"}


def udp_telemetry_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_TELEMETRY_PORT))
    print(f"[SERVER] 📡 Listening for Host & Router Telemetry on UDP port {UDP_TELEMETRY_PORT}")

    while True:
        try:
            raw_data, addr = sock.recvfrom(8192)
            data = json.loads(raw_data.decode('utf-8'))

            agent_id = data.get("agent_id", "Unknown")
            ip_address = data.get("ip_address", addr[0])
            c2_port = data.get("c2_port", 5001)

            # Check if this is router telemetry
            if agent_id.startswith("Router-"):
                with node_lock:
                    router_state["status"] = data.get("status", "HEALTHY")
                    router_state["system"]["cpu_percent"] = data.get("cpu_percent", 0.0)
                    router_state["system"]["memory_percent"] = data.get("memory_percent", 0.0)
                    router_state["throughput"]["upload_mbps"] = data.get("upload_mbps", 0.0)
                    router_state["throughput"]["download_mbps"] = data.get("download_mbps", 0.0)
                    router_state["throughput"]["packet_drops"] = data.get("packet_drops", 0)
                    router_state["last_seen"] = time.time()
                db.update_router_metrics("r1", data.get("cpu_percent", 0.0), data.get("memory_percent", 0.0), data.get("status", "HEALTHY"))
                continue

            with node_lock:
                prev_node = active_nodes.get(agent_id, {})
                prev_sent = prev_node.get("bytes_sent", 0)
                sent_delta = data.get("bytes_sent", 0) - prev_sent

                # Anomaly Evaluation via AnomalyDetector Engine
                anomalies = anomaly_engine.evaluate_telemetry(data)
                for anom in anomalies:
                    event_manager.publish_event(anom)
                    if anom.get("action_taken") == "TRIGGER_SDN_MITIGATION" and not prev_node.get("sdn_mitigated"):
                        print(f"[ANOMALY DETECTED] Traffic surge from {agent_id} ({ip_address})! Triggering SDN Mitigation...")
                        sdn_mitigate_api(ip_address, agent_id)
                        data["sdn_mitigated"] = True

                # Backward compatibility check for packet burst
                if (sent_delta > 2000000 or data.get("status") == "ATTACKING") and not prev_node.get("sdn_mitigated"):
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
                active_attack=data.get("active_attack", False),
                upload_mbps=data.get("upload_mbps", 0.0),
                download_mbps=data.get("download_mbps", 0.0),
                sequence_number=data.get("sequence_number", 0)
            )

        except Exception:
            pass


def node_liveness_checker():
    while True:
        time.sleep(3)
        now = time.time()
        with node_lock:
            for agent_id in list(active_nodes.keys()):
                if now - active_nodes[agent_id].get("last_seen", 0) > NODE_TIMEOUT:
                    if active_nodes[agent_id]["status"] != "DOWN":
                        active_nodes[agent_id]["status"] = "DOWN"
                        event_manager.publish_event({
                            "event_id": f"evt_down_{agent_id}_{int(now)}",
                            "component": agent_id,
                            "event_type": "NODE_OFFLINE",
                            "severity": "CRITICAL",
                            "description": f"Node {agent_id} heartbeat expired (> {NODE_TIMEOUT}s)",
                            "status": "DETECTED"
                        })
            # Router liveness
            if now - router_state.get("last_seen", 0) > NODE_TIMEOUT:
                router_state["status"] = "OFFLINE"


# --- FLASK API ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    return jsonify({"status": "HEALTHY", "service": "CENTRAL_MONITORING_PLANE", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/metrics")
def get_metrics():
    with node_lock:
        nodes = list(active_nodes.values())
        r_state = dict(router_state)

    # Query SDN Controller Stats
    sdn_stats = {"status": "OFFLINE", "active_rules": [], "switches": ["s1", "s2"]}
    controller_url = get_sdn_controller_url()
    try:
        with urllib.request.urlopen(f"{controller_url}/api/v1/sdn/stats", timeout=0.8) as resp:
            sdn_stats = json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass

    # Query Load Balancer Metrics if running
    lb_stats = {"status": "STANDBY"}
    try:
        with urllib.request.urlopen(f"{LB_URL}/lb/status", timeout=0.8) as resp:
            lb_stats = json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass

    return jsonify({
        "nodes": nodes,
        "router": r_state,
        "sdn": sdn_stats,
        "load_balancer": lb_stats,
        "events": event_manager.get_recent_events(limit=15),
        "db_history": db.get_recent_telemetry(limit=25)
    })


@app.route("/api/nodes")
def get_nodes():
    with node_lock:
        return jsonify(list(active_nodes.values()))


@app.route("/api/nodes/<node_id>")
def get_node_by_id(node_id):
    with node_lock:
        node = active_nodes.get(node_id)
    if node:
        return jsonify(node)
    return jsonify({"error": "Node not found"}), 404


@app.route("/api/router")
@app.route("/api/router/health")
def get_router():
    with node_lock:
        return jsonify(router_state)


@app.route("/api/router/interfaces")
def get_router_interfaces():
    with node_lock:
        return jsonify(router_state.get("interfaces", {}))


@app.route("/api/router/routes")
def get_router_routes():
    with node_lock:
        return jsonify(router_state.get("routes", []))


# --- LOAD BALANCER APIS ---

@app.route("/api/lb/status")
def get_lb_status():
    try:
        with urllib.request.urlopen(f"{LB_URL}/lb/status", timeout=1.5) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"status": "STANDBY", "message": f"Load Balancer standby or unreachable at {LB_URL}"})


@app.route("/api/lb/metrics")
def get_lb_metrics():
    try:
        with urllib.request.urlopen(f"{LB_URL}/lb/metrics", timeout=1.5) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/lb/algorithm", methods=["POST"])
def set_lb_algorithm():
    data = request.json or {}
    try:
        req = urllib.request.Request(f"{LB_URL}/lb/algorithm", data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lb/backend/<backend_id>/drain", methods=["POST"])
def drain_lb_backend(backend_id):
    try:
        req = urllib.request.Request(f"{LB_URL}/lb/backend/{backend_id}/drain", data=b"{}", headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lb/backend/<backend_id>/restore", methods=["POST"])
def restore_lb_backend(backend_id):
    try:
        req = urllib.request.Request(f"{LB_URL}/lb/backend/{backend_id}/restore", data=b"{}", headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- SIMULATION LAB APIS ---

@app.route("/api/simulation/cpu/start", methods=["POST"])
def sim_cpu_start():
    data = request.json or {}
    duration = data.get("duration", 10)
    intensity = data.get("intensity", 0.95)
    threading.Thread(target=run_cpu_stress, kwargs={"duration": duration, "intensity": intensity}, daemon=True).start()
    db.log_audit("START_CPU_STRESS", "Cluster/Local", "SUCCESS", "OPERATOR")
    return jsonify({"status": "SUCCESS", "message": f"CPU Stress launched for {duration}s"})


@app.route("/api/simulation/network/start", methods=["POST"])
def sim_network_start():
    data = request.json or {}
    target = data.get("target", "10.0.1.20")
    mbps = data.get("mbps", 50)
    duration = data.get("duration", 10)
    threading.Thread(target=run_network_stress, kwargs={"target_ip": target, "bandwidth_mbps": mbps, "duration": duration}, daemon=True).start()
    db.log_audit("START_NETWORK_STRESS", target, "SUCCESS", "OPERATOR")
    return jsonify({"status": "SUCCESS", "message": f"Network Stress launched toward {target} for {duration}s"})


@app.route("/api/simulation/backend/fail", methods=["POST"])
def sim_backend_fail():
    data = request.json or {}
    bid = data.get("backend_id", "backend-2")
    ip = data.get("ip", "10.0.2.12")
    port = data.get("port", 8002)
    res = simulate_backend_failure(backend_id=bid, backend_ip=ip, port=port, lb_url=LB_URL)
    return jsonify(res)


@app.route("/api/simulation/backend/restore", methods=["POST"])
def sim_backend_restore():
    data = request.json or {}
    bid = data.get("backend_id", "backend-2")
    ip = data.get("ip", "10.0.2.12")
    port = data.get("port", 8002)
    res = restore_backend(backend_id=bid, backend_ip=ip, port=port, lb_url=LB_URL)
    return jsonify(res)


@app.route("/api/simulation/stop", methods=["POST"])
def sim_stop_all():
    stop_all_cpu_stress()
    return jsonify({"status": "SUCCESS", "message": "All simulation stressors halted."})


# --- SDN MITIGATION APIS ---

@app.route("/api/sdn/mitigate", methods=["POST"])
def manual_sdn_mitigate():
    req_json = request.json or {}
    src_ip = req_json.get("src_ip")
    agent_id = req_json.get("agent_id", "Manual")
    res = sdn_mitigate_api(src_ip, agent_id)
    return jsonify(res)


@app.route("/api/sdn/unblock", methods=["POST"])
def manual_sdn_unblock():
    req_json = request.json or {}
    src_ip = req_json.get("src_ip")
    controller_url = get_sdn_controller_url()
    try:
        req_data = json.dumps({"src_ip": src_ip}).encode('utf-8')
        req_obj = urllib.request.Request(
            f"{controller_url}/api/v1/sdn/unblock",
            data=req_data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req_obj, timeout=3) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            with node_lock:
                for node in active_nodes.values():
                    if node.get("ip_address") == src_ip:
                        node["sdn_mitigated"] = False
            db.log_sdn_event(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                "SDN-Controller",
                "FLOW_UNBLOCKED",
                f"Removed OpenFlow DROP rule for src_ip {src_ip}",
                "REMOVED"
            )
            return jsonify(res)
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)})


# --- ATTACK & C2 DISPATCH APIS ---

@app.route("/api/attack/start", methods=["POST"])
def start_attack():
    req_json = request.json or {}
    agent_id = req_json.get("agent_id")
    c2_port = req_json.get("c2_port", 5001)
    duration = req_json.get("duration", 15)

    with node_lock:
        node = active_nodes.get(agent_id)

    agent_ip = node.get("ip_address", "127.0.0.1") if node else "127.0.0.1"

    payload = {
        "command": "START_ATTACK",
        "target_ip": "10.0.1.20",
        "target_port": 8080,
        "duration": duration,
        "packet_size": 1024
    }

    res = send_c2_command(agent_ip, c2_port, payload)
    return jsonify(res)


@app.route("/api/attack/stop", methods=["POST"])
def stop_attack():
    req_json = request.json or {}
    agent_id = req_json.get("agent_id")
    c2_port = req_json.get("c2_port", 5001)

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
            return

        print(f"[CAMPAIGN] 🚀 Starting Sequential Attack Campaign on {len(nodes)} nodes...")
        for node in nodes:
            agent_id = node.get("agent_id")
            c2_port = node.get("c2_port", 5001)
            agent_ip = node.get("ip_address", "127.0.0.1")

            print(f"[CAMPAIGN] 💣 Step: Attacking via {agent_id} for 10 seconds...")
            send_c2_command(agent_ip, c2_port, {
                "command": "START_ATTACK",
                "target_ip": "10.0.1.20",
                "target_port": 8080,
                "duration": 10
            })
            time.sleep(12)

    threading.Thread(target=campaign_worker, daemon=True).start()
    return jsonify({"status": "SUCCESS", "message": "Sequential Attack Campaign launched across nodes."})


@app.route("/api/campaign/multi_vector", methods=["POST"])
def start_multi_vector_campaign():
    req_json = request.json or {}
    duration = req_json.get("duration", 15)

    def multi_attack_worker():
        with node_lock:
            nodes = list(active_nodes.values())

        target_nodes = nodes[:2] if len(nodes) >= 2 else nodes
        print(f"[MULTI-ATTACK] 🚀 Launching SIMULTANEOUS Multi-Vector Attack from {len(target_nodes)} nodes...")
        threads = []
        for node in target_nodes:
            agent_id = node.get("agent_id")
            c2_port = node.get("c2_port", 5001)
            agent_ip = node.get("ip_address", "127.0.0.1")

            t = threading.Thread(
                target=send_c2_command,
                args=(agent_ip, c2_port, {
                    "command": "START_ATTACK",
                    "target_ip": "10.0.1.20",
                    "target_port": 8080,
                    "duration": duration
                })
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    threading.Thread(target=multi_attack_worker, daemon=True).start()
    return jsonify({"status": "SUCCESS", "message": f"Simultaneous Multi-Vector DDoS launched for {duration}s."})


@app.route("/api/events")
def get_events():
    return jsonify(event_manager.get_recent_events(limit=50))


@app.route("/api/alerts/<alert_id>/acknowledge", methods=["POST"])
def ack_alert(alert_id):
    success = event_manager.acknowledge_event(alert_id)
    return jsonify({"status": "SUCCESS" if success else "NOT_FOUND"})


def run_server():
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
