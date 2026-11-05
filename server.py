#!/usr/bin/env python3
"""
Central Ingestion, Orchestration & Web Control Plane
Remote Network Health Monitor — Two-Router Multi-Subnet Architecture
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
from monitoring.packet_loss import packet_loss_detector
from monitoring.packet_monitor import packet_monitor
from monitoring.switch_monitor import switch_monitor
from services.event_manager import event_manager
from services.recovery import recovery_manager
from services.diagnostics import diagnostics_service
from control.operation_manager import operation_manager
from control.node_manager import node_manager
from control.router_manager import router_manager
from control.switch_manager import switch_manager
from control.link_manager import link_manager
from control.service_manager import service_manager
from control.lab_manager import lab_manager
from traffic.traffic_manager import traffic_manager
from simulation.cpu_stress import run_cpu_stress, stop_all_cpu_stress
from simulation.network_stress import run_network_stress
from simulation.node_failure import simulate_backend_failure, restore_backend

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))

# Server Configuration
UDP_TELEMETRY_PORT = 5000
NODE_TIMEOUT = 12
C2_SHARED_SECRET = os.getenv("C2_SECRET_TOKEN", "sdn_cn_c2_token_secret_2026")

# Automated Remediation Switch (Defaults to True; user can toggle off to observe spikes!)
auto_remediation_enabled = True

# Simulated link drops dictionary for demonstration
simulated_drops = {"transit_link": 0.0, "client_access": 0.0, "backend_cluster": 0.0}

# In-memory registry & anomaly detector
active_nodes = {}

# Backend server cluster registry (h5, h6, h7)
BACKENDS = {
    "backend-1": {
        "id": "backend-1",
        "name": "Server 1 (h5)",
        "ip": "10.0.2.11",
        "port": 8001,
        "power_state": "ON",
        "status": "healthy",
        "weight": 1
    },
    "backend-2": {
        "id": "backend-2",
        "name": "Server 2 (h6)",
        "ip": "10.0.2.12",
        "port": 8002,
        "power_state": "ON",
        "status": "healthy",
        "weight": 2
    },
    "backend-3": {
        "id": "backend-3",
        "name": "Server 3 (h7)",
        "ip": "10.0.2.13",
        "port": 8003,
        "power_state": "ON",
        "status": "healthy",
        "weight": 1
    }
}

# Two-Router State
routers_state = {
    "r1": {
        "router_id": "r1",
        "name": "Router 1 (Client Gateway)",
        "role": "Subnet 1 Gateway & Transit Link",
        "status": "HEALTHY",
        "system": {"cpu_percent": 3.8, "memory_percent": 18.2, "uptime_seconds": 120},
        "throughput": {"upload_mbps": 0.45, "download_mbps": 0.38, "packet_drops": 0, "packet_errors": 0},
        "connectivity": {"target": "10.0.1.20", "latency_ms": 0.45, "packet_loss_percent": 0.0},
        "transit_peer": "10.0.12.2",
        "transit_connectivity": {"target": "10.0.12.2", "latency_ms": 0.80, "packet_loss_percent": 0.0},
        "interfaces": {
            "r1-eth0": {"name": "r1-eth0", "ip": "10.0.1.1/24", "state": "UP"},
            "r1-eth1": {"name": "r1-eth1", "ip": "10.0.12.1/30", "state": "UP"}
        },
        "routes": [
            {"destination": "10.0.1.0/24", "gateway": "*", "interface": "r1-eth0", "protocol": "kernel"},
            {"destination": "10.0.12.0/30", "gateway": "*", "interface": "r1-eth1", "protocol": "kernel"},
            {"destination": "10.0.2.0/24", "gateway": "10.0.12.2", "interface": "r1-eth1", "protocol": "static"}
        ],
        "last_seen": time.time()
    },
    "r2": {
        "router_id": "r2",
        "name": "Router 2 (Backend Gateway)",
        "role": "Transit Link & Subnet 2 Gateway",
        "status": "HEALTHY",
        "system": {"cpu_percent": 3.4, "memory_percent": 17.9, "uptime_seconds": 120},
        "throughput": {"upload_mbps": 0.42, "download_mbps": 0.35, "packet_drops": 0, "packet_errors": 0},
        "connectivity": {"target": "10.0.1.20", "latency_ms": 0.75, "packet_loss_percent": 0.0},
        "transit_peer": "10.0.12.1",
        "transit_connectivity": {"target": "10.0.12.1", "latency_ms": 0.80, "packet_loss_percent": 0.0},
        "interfaces": {
            "r2-eth0": {"name": "r2-eth0", "ip": "10.0.12.2/30", "state": "UP"},
            "r2-eth1": {"name": "r2-eth1", "ip": "10.0.2.1/24", "state": "UP"}
        },
        "routes": [
            {"destination": "10.0.2.0/24", "gateway": "*", "interface": "r2-eth1", "protocol": "kernel"},
            {"destination": "10.0.12.0/30", "gateway": "*", "interface": "r2-eth0", "protocol": "kernel"},
            {"destination": "10.0.1.0/24", "gateway": "10.0.12.1", "interface": "r2-eth0", "protocol": "static"}
        ],
        "last_seen": time.time()
    }
}

# Backward compatibility alias
router_state = routers_state["r1"]

node_lock = threading.Lock()
anomaly_engine = AnomalyDetector()

# Initialize DB Schema
db.create_database()


_sdn_cached_url = None
_sdn_cache_time = 0

def get_sdn_controller_url():
    """Dynamically probes Mininet bridge IP (10.0.1.254/10.0.0.254:8080) and local loopback with 5s cache."""
    global _sdn_cached_url, _sdn_cache_time
    now = time.time()
    if _sdn_cached_url and (now - _sdn_cache_time < 5.0):
        return _sdn_cached_url

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
            with urllib.request.urlopen(req, timeout=0.15) as resp:
                _sdn_cached_url = url
                _sdn_cache_time = now
                return url
        except Exception:
            pass

    fallback = os.getenv("SDN_CONTROLLER_URL", "http://10.0.1.254:8080")
    _sdn_cached_url = fallback
    _sdn_cache_time = now
    return fallback


_lb_cached_url = None
_lb_cache_time = 0

def get_lb_url():
    """Dynamically probes Load Balancer URL with 5s cache."""
    global _lb_cached_url, _lb_cache_time
    now = time.time()
    if _lb_cached_url and (now - _lb_cache_time < 5.0):
        return _lb_cached_url

    candidates = [
        os.getenv("LB_URL"),
        "http://10.0.2.30:8000",
        "http://10.0.1.30:8000",
        "http://127.0.0.1:8000"
    ]
    for url in candidates:
        if not url:
            continue
        try:
            req = urllib.request.Request(f"{url}/lb/status")
            with urllib.request.urlopen(req, timeout=0.15) as resp:
                _lb_cached_url = url
                _lb_cache_time = now
                return url
        except Exception:
            pass

    fallback = os.getenv("LB_URL", "http://10.0.2.30:8000")
    _lb_cached_url = fallback
    _lb_cache_time = now
    return fallback


def get_all_backends_status():
    """Returns current status and traffic share calculation of all 3 backends."""
    lb_url = get_lb_url()
    lb_shares = {}
    try:
        with urllib.request.urlopen(f"{lb_url}/lb/status", timeout=0.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            lb_shares = data.get("config", {}).get("traffic_shares", {})
    except Exception:
        pass

    # If LB unreachable, calculate local fallback shares
    if not lb_shares:
        active_weights = {bid: b["weight"] for bid, b in BACKENDS.items() if b["power_state"] == "ON" and b["status"] == "healthy"}
        tot = sum(active_weights.values())
        for bid in BACKENDS:
            if bid in active_weights and tot > 0:
                lb_shares[bid] = round((active_weights[bid] / tot) * 100.0, 1)
            else:
                lb_shares[bid] = 0.0

    res = {}
    for bid, b in BACKENDS.items():
        res[bid] = {
            **b,
            "traffic_share_percent": lb_shares.get(bid, 0.0)
        }
    return res


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
    global auto_remediation_enabled
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

            # Check if this is router telemetry (Router-r1 or Router-r2)
            if agent_id.startswith("Router-"):
                rid = agent_id.replace("Router-", "").lower()  # "r1" or "r2"
                if rid not in routers_state:
                    rid = "r1"
                r_rep = data.get("router_report", {})
                with node_lock:
                    target_router = routers_state[rid]
                    target_router["status"] = data.get("status", "HEALTHY")
                    target_router["system"]["cpu_percent"] = data.get("cpu_percent", 0.0)
                    target_router["system"]["memory_percent"] = data.get("memory_percent", 0.0)
                    target_router["throughput"]["upload_mbps"] = data.get("upload_mbps", 0.0)
                    target_router["throughput"]["download_mbps"] = data.get("download_mbps", 0.0)
                    target_router["throughput"]["packet_drops"] = data.get("packet_drops", 0)
                    target_router["last_seen"] = time.time()
                    if r_rep:
                        if "interfaces" in r_rep:
                            target_router["interfaces"] = r_rep["interfaces"]
                        if "routes" in r_rep:
                            target_router["routes"] = r_rep["routes"]
                        if "connectivity" in r_rep:
                            target_router["connectivity"] = r_rep["connectivity"]
                        if "transit_connectivity" in r_rep:
                            target_router["transit_connectivity"] = r_rep["transit_connectivity"]

                db.update_router_metrics(rid, data.get("cpu_percent", 0.0), data.get("memory_percent", 0.0), data.get("status", "HEALTHY"))
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
                        if auto_remediation_enabled:
                            print(f"[ANOMALY DETECTED] Traffic surge from {agent_id} ({ip_address})! Auto-Remediation ON -> Pushing SDN DROP...")
                            sdn_mitigate_api(ip_address, agent_id)
                            data["sdn_mitigated"] = True
                        else:
                            print(f"[ANOMALY DETECTED] Traffic surge from {agent_id} ({ip_address})! Auto-Remediation OFF -> Observing spike!")
                            data["sdn_mitigated"] = False
                            event_manager.publish_event({
                                "event_id": f"evt_unmit_{agent_id}_{int(time.time())}",
                                "component": agent_id,
                                "event_type": "UNMITIGATED_SURGE_OBSERVED",
                                "severity": "CRITICAL",
                                "description": f"High traffic surge observed on {agent_id}. Auto-remediation is OFF (Observation Mode).",
                                "status": "OBSERVING"
                            })

                # Backward compatibility check for packet burst
                if (sent_delta > 2000000 or data.get("status") == "ATTACKING") and not prev_node.get("sdn_mitigated"):
                    if auto_remediation_enabled:
                        sdn_mitigate_api(ip_address, agent_id)
                        data["sdn_mitigated"] = True
                    else:
                        data["sdn_mitigated"] = False

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
            # Check both routers
            for rid, r in routers_state.items():
                if now - r.get("last_seen", 0) > NODE_TIMEOUT:
                    r["status"] = "OFFLINE"


# --- FLASK API ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "HEALTHY",
        "service": "CENTRAL_MONITORING_PLANE",
        "architecture": "TWO_ROUTER_MULTI_SUBNET",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/metrics")
def get_metrics():
    with node_lock:
        nodes = list(active_nodes.values())
        r1_copy = dict(routers_state["r1"])
        r2_copy = dict(routers_state["r2"])

    # Query SDN Controller Stats
    sdn_stats = {"status": "OFFLINE", "active_rules": [], "switches": ["s1", "s2"]}
    controller_url = get_sdn_controller_url()
    try:
        with urllib.request.urlopen(f"{controller_url}/api/v1/sdn/stats", timeout=0.8) as resp:
            sdn_stats = json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass

    # Query Load Balancer Metrics
    lb_stats = {"status": "STANDBY"}
    lb_url = get_lb_url()
    try:
        with urllib.request.urlopen(f"{lb_url}/lb/status", timeout=0.8) as resp:
            lb_stats = json.loads(resp.read().decode('utf-8'))
    except Exception:
        pass

    # Segment Packet Loss Evaluation
    loss_data = packet_loss_detector.evaluate_loss_state(
        router1=r1_copy,
        router2=r2_copy,
        nodes=nodes,
        simulated_drops=simulated_drops
    )

    # Transit Link Summary (r1 <-> r2)
    transit_summary = {
        "network": "10.0.12.0/30",
        "r1_ip": "10.0.12.1",
        "r2_ip": "10.0.12.2",
        "latency_ms": r1_copy.get("transit_connectivity", {}).get("latency_ms", 0.80),
        "loss_percent": loss_data["segments"]["transit_link"]["loss_percent"],
        "status": loss_data["segments"]["transit_link"]["status"]
    }

    return jsonify({
        "nodes": nodes,
        "router": r1_copy,  # Backwards compatibility
        "routers": {
            "r1": r1_copy,
            "r2": r2_copy,
            "transit": transit_summary
        },
        "sdn": sdn_stats,
        "load_balancer": lb_stats,
        "backends": get_all_backends_status(),
        "packet_loss": loss_data,
        "auto_remediation_enabled": auto_remediation_enabled,
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


# --- TWO-ROUTER APIS ---

@app.route("/api/routers")
def get_all_routers():
    with node_lock:
        r1_copy = dict(routers_state["r1"])
        r2_copy = dict(routers_state["r2"])
    return jsonify({
        "r1": r1_copy,
        "r2": r2_copy,
        "transit_link": {
            "network": "10.0.12.0/30",
            "r1_interface": "r1-eth1 (10.0.12.1/30)",
            "r2_interface": "r2-eth0 (10.0.12.2/30)",
            "latency_ms": r1_copy.get("transit_connectivity", {}).get("latency_ms", 0.80),
            "loss_percent": simulated_drops.get("transit_link", 0.0)
        }
    })


@app.route("/api/router")
@app.route("/api/router/r1")
@app.route("/api/router/health")
def get_router_r1():
    with node_lock:
        return jsonify(routers_state["r1"])


@app.route("/api/router/r2")
def get_router_r2():
    with node_lock:
        return jsonify(routers_state["r2"])


@app.route("/api/router/interfaces")
def get_router_interfaces():
    with node_lock:
        return jsonify({
            "r1": routers_state["r1"].get("interfaces", {}),
            "r2": routers_state["r2"].get("interfaces", {})
        })


@app.route("/api/router/routes")
def get_router_routes():
    with node_lock:
        return jsonify({
            "r1": routers_state["r1"].get("routes", []),
            "r2": routers_state["r2"].get("routes", [])
        })


# --- PACKET LOSS LOCALIZATION APIS ---

@app.route("/api/network/packet_loss")
def get_packet_loss_diagnosis():
    with node_lock:
        r1_copy = dict(routers_state["r1"])
        r2_copy = dict(routers_state["r2"])
        nodes = list(active_nodes.values())
    res = packet_loss_detector.evaluate_loss_state(r1_copy, r2_copy, nodes, simulated_drops)
    return jsonify(res)


@app.route("/api/network/packet_loss/simulate", methods=["POST"])
def set_simulated_loss():
    global simulated_drops
    data = request.json or {}
    simulated_drops["transit_link"] = float(data.get("transit_link", 0.0))
    simulated_drops["client_access"] = float(data.get("client_access", 0.0))
    simulated_drops["backend_cluster"] = float(data.get("backend_cluster", 0.0))
    return jsonify({"status": "SUCCESS", "simulated_drops": simulated_drops})


# --- AUTOMATED REMEDIATION TOGGLE API ---

@app.route("/api/sdn/remediation_toggle", methods=["POST"])
def toggle_auto_remediation():
    global auto_remediation_enabled
    data = request.json or {}
    if "enabled" in data:
        auto_remediation_enabled = bool(data["enabled"])
    else:
        auto_remediation_enabled = not auto_remediation_enabled

    state_str = "ENABLED" if auto_remediation_enabled else "DISABLED"
    db.log_audit("SDN_REMEDIATION_TOGGLE", state_str, "SUCCESS", "OPERATOR")

    event_manager.publish_event({
        "event_id": f"evt_rem_{int(time.time())}",
        "component": "SDN_AUTOMATION",
        "event_type": "REMEDIATION_TOGGLE",
        "severity": "NORMAL" if auto_remediation_enabled else "WARNING",
        "description": f"Automated SDN Remediation has been turned {state_str}. {'Attacks will be automatically mitigated.' if auto_remediation_enabled else 'Spikes will run unmitigated for live observation.'}",
        "status": "CONFIGURED"
    })

    return jsonify({
        "status": "SUCCESS",
        "auto_remediation_enabled": auto_remediation_enabled,
        "mode_description": "Active Defense" if auto_remediation_enabled else "Observation Mode (Unmitigated)"
    })


@app.route("/api/sdn/remediation_status")
def get_remediation_status():
    return jsonify({
        "auto_remediation_enabled": auto_remediation_enabled,
        "mode": "ACTIVE_DEFENSE" if auto_remediation_enabled else "OBSERVATION_MODE"
    })


# --- BACKEND POWER CONTROLS (POWER ON / POWER OFF) ---

@app.route("/api/backend/status")
def api_backend_status():
    return jsonify(get_all_backends_status())


@app.route("/api/backend/<backend_id>/power_off", methods=["POST"])
def power_off_backend(backend_id):
    b_info = BACKENDS.get(backend_id)
    if not b_info:
        return jsonify({"error": f"Backend '{backend_id}' not found"}), 404

    b_info["power_state"] = "OFF"
    b_info["status"] = "offline"

    # 1. Inform the individual backend microservice
    try:
        req_data = json.dumps({"status": "offline"}).encode('utf-8')
        req = urllib.request.Request(f"http://{b_info['ip']}:{b_info['port']}/admin/status", data=req_data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=0.2)
    except Exception:
        pass

    # 2. Inform the Load Balancer
    lb_url = get_lb_url()
    lb_res = {}
    try:
        req = urllib.request.Request(f"{lb_url}/lb/backend/{backend_id}/power_off", data=b"{}", headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=0.2) as resp:
            lb_res = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        lb_res = {"notice": f"LB notify error: {e}"}

    db.log_audit("BACKEND_POWER_OFF", backend_id, "SUCCESS", "OPERATOR")
    event_manager.publish_event({
        "event_id": f"evt_pwr_off_{backend_id}_{int(time.time())}",
        "component": backend_id,
        "event_type": "BACKEND_POWER_OFF",
        "severity": "WARNING",
        "description": f"Server {b_info['name']} powered OFF. Traffic automatically redistributed across surviving servers.",
        "status": "POWERED_OFF"
    })

    return jsonify({
        "status": "SUCCESS",
        "backend_id": backend_id,
        "power_state": "OFF",
        "lb_response": lb_res,
        "backends": get_all_backends_status()
    })


@app.route("/api/backend/<backend_id>/power_on", methods=["POST"])
def power_on_backend(backend_id):
    b_info = BACKENDS.get(backend_id)
    if not b_info:
        return jsonify({"error": f"Backend '{backend_id}' not found"}), 404

    b_info["power_state"] = "ON"
    b_info["status"] = "healthy"

    # 1. Inform the individual backend microservice
    try:
        req_data = json.dumps({"status": "healthy"}).encode('utf-8')
        req = urllib.request.Request(f"http://{b_info['ip']}:{b_info['port']}/admin/status", data=req_data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=0.2)
    except Exception:
        pass

    # 2. Inform the Load Balancer
    lb_url = get_lb_url()
    lb_res = {}
    try:
        req = urllib.request.Request(f"{lb_url}/lb/backend/{backend_id}/power_on", data=b"{}", headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=0.2) as resp:
            lb_res = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        lb_res = {"notice": f"LB notify error: {e}"}

    db.log_audit("BACKEND_POWER_ON", backend_id, "SUCCESS", "OPERATOR")
    event_manager.publish_event({
        "event_id": f"evt_pwr_on_{backend_id}_{int(time.time())}",
        "component": backend_id,
        "event_type": "BACKEND_POWER_ON",
        "severity": "NORMAL",
        "description": f"Server {b_info['name']} powered ON. Re-admitted to Load Balancer rotation.",
        "status": "RESTORED"
    })

    return jsonify({
        "status": "SUCCESS",
        "backend_id": backend_id,
        "power_state": "ON",
        "lb_response": lb_res,
        "backends": get_all_backends_status()
    })


# --- LOAD BALANCER APIS ---

@app.route("/api/lb/status")
def get_lb_status():
    lb_url = get_lb_url()
    try:
        with urllib.request.urlopen(f"{lb_url}/lb/status", timeout=1.5) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"status": "STANDBY", "message": f"Load Balancer standby or unreachable at {lb_url}"})


@app.route("/api/lb/metrics")
def get_lb_metrics():
    lb_url = get_lb_url()
    try:
        with urllib.request.urlopen(f"{lb_url}/lb/metrics", timeout=1.5) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/lb/algorithm", methods=["POST"])
def set_lb_algorithm():
    data = request.json or {}
    lb_url = get_lb_url()
    try:
        req = urllib.request.Request(f"{lb_url}/lb/algorithm", data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lb/backend/<backend_id>/drain", methods=["POST"])
def drain_lb_backend(backend_id):
    lb_url = get_lb_url()
    try:
        req = urllib.request.Request(f"{lb_url}/lb/backend/{backend_id}/drain", data=b"{}", headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return jsonify(json.loads(resp.read().decode('utf-8')))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lb/backend/<backend_id>/restore", methods=["POST"])
def restore_lb_backend(backend_id):
    lb_url = get_lb_url()
    try:
        req = urllib.request.Request(f"{lb_url}/lb/backend/{backend_id}/restore", data=b"{}", headers={'Content-Type': 'application/json'})
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
    return power_off_backend(bid)


@app.route("/api/simulation/backend/restore", methods=["POST"])
def sim_backend_restore():
    data = request.json or {}
    bid = data.get("backend_id", "backend-2")
    return power_on_backend(bid)


@app.route("/api/simulation/stop", methods=["POST"])
def sim_stop_all():
    global simulated_drops
    stop_all_cpu_stress()
    simulated_drops = {"transit_link": 0.0, "client_access": 0.0, "backend_cluster": 0.0}
    return jsonify({"status": "SUCCESS", "message": "All simulation stressors halted and link loss reset."})


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
    print("  Two-Router Multi-Subnet Architecture  ")
    print("========================================")
    print("Web Dashboard: http://127.0.0.1:5050")
    print("UDP Telemetry Port: 5000")
    print("========================================\n")

    app.run(host="0.0.0.0", port=5050, debug=False)


if __name__ == "__main__":
    run_server()
