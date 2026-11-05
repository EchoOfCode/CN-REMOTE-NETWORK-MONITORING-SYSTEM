# 🌐 Remote Network Health Monitor
### Industry-Grade Network Intelligence, Telemetry Monitoring, Traffic Management & SDN Platform
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![SDN](https://img.shields.io/badge/SDN-OpenFlow%201.3-purple.svg)](https://opennetworking.org/)
[![Load%20Balancer](https://img.shields.io/badge/Load%20Balancer-Async%20aiohttp-green.svg)](https://docs.aiohttp.org/)
[![Network](https://img.shields.io/badge/Mininet-Dual--Subnet%20Routed-orange.svg)](http://mininet.org/)
[![Database](https://img.shields.io/badge/SQLite-WAL%20Mode-blue.svg)](https://www.sqlite.org/)

---

## 1. Project Overview & Vision

**Remote Network Health Monitor** is a production-grade, centralized network observability, traffic management, and automated remediation platform. It bridges distributed host-level and router-level telemetry with software-defined networking (OpenFlow 1.3) and custom application-level load balancing.

The system is engineered for dual operations:
1. **Continuous Observability**: Real-time distributed telemetry ingestion, accurate bandwidth throughput tracking ($Mbps$), router CPU/interface health monitoring, and deterministic anomaly detection.
2. **Active Network Control**: Automated OpenFlow hardware-level flow mitigation, custom HTTP reverse-proxy traffic balancing with dynamic backend failover, and controlled laboratory stress simulations.

---

## 2. Multi-Subnet Architecture

The platform operates across two isolated Layer 3 subnets connected by a dedicated Linux Layer 3 Router (`r1`) and controlled by an OpenFlow 1.3 SDN Controller (`c0`):

```
       [ Client Subnet: 10.0.1.0/24 ]                             [ Backend Subnet: 10.0.2.0/24 ]
 ┌────────────────────────────────────────┐                 ┌────────────────────────────────────────┐
 │ h1: Client 1 (10.0.1.11, Agent 1)      │                 │ h5: Backend Server 1 (10.0.2.11)       │
 │ h2: Client 2 (10.0.1.12, Agent 2)      │                 │ h6: Backend Server 2 (10.0.2.12)       │
 │ h3: Client 3 (10.0.1.13, Agent 3)      │                 │ h7: Backend Server 3 (10.0.2.13)       │
 │ h4: Monitor & Web UI (10.0.1.20:5050)  │                 └───────────────────┬────────────────────┘
 │ h8: Load Balancer (10.0.1.30:8000)     │                                     │
 └───────────────────┬────────────────────┘                                     │
                     │                                                          │
          ┌──────────┴──────────┐                                    ┌──────────┴──────────┐
          │  Open vSwitch s1    │                                    │  Open vSwitch s2    │
          │   (Client Switch)   │                                    │  (Backend Switch)   │
          └──────────┬──────────┘                                    └──────────┬──────────┘
                     │                                                          │
                     │  r1-eth0 (10.0.1.1)                  r1-eth1 (10.0.2.1)  │
                     └────────────────────┐                ┌────────────────────┘
                                          │                │
                                      ┌───┴────────────────┴───┐
                                      │  Linux Layer 3 Router  │
                                      │   (r1: ip_forward=1)   │
                                      └────────────────────────┘
```

---

## 3. Key Capabilities & Features

1. **Distributed Host & Router Telemetry**:
   - High-performance UDP socket streaming (port 5000) with sequence tracking.
   - Dynamic bandwidth rate calculation ($Mbps = \frac{\Delta \text{bytes} \times 8}{\Delta t \times 10^6}$).
   - Router `r1` interface status, packet drops, and kernel routing table inspection.

2. **Custom Python Async HTTP Load Balancer (`load_balancer/`)**:
   - Built on Python `asyncio` and `aiohttp`.
   - **Algorithms**: Round Robin, Least Connections, Smooth Weighted Round Robin.
   - **Active Health Checking**: Background polling (`GET /health`) with multi-failure eviction and multi-success recovery hysteresis.
   - **Zero-Downtime Failover**: Automatically excludes failing upstream backends (`h5`-`h7`) and redistributes incoming requests.

3. **SDN Hardware Flow Mitigation (`OpenFlow 1.3`)**:
   - Zero-dependency standalone SDN controller and Ryu controller compatibility.
   - Dynamic kernel flow injection on Open vSwitch switches `s1` and `s2`:
     `priority=1000, ip, nw_src=<attacker_ip>, actions=drop`.
   - Neutralizes volumetric floods at wire speed before reaching the target.

4. **Deterministic Anomaly & Event Engine (`monitoring/`, `services/`)**:
   - Configurable consecutive-sample thresholds with hysteresis to prevent status oscillation.
   - Formal alert lifecycle: `DETECTED -> ACKNOWLEDGED -> MITIGATING -> RECOVERED`.

5. **Controlled Simulation Engine (`simulation/`)**:
   - Bounded CPU stress generator (85-95% burn) with safety timeouts.
   - Network throughput burst testing via `iperf3` or socket burst.
   - Controlled backend outage injection and automatic recovery.

6. **Enterprise NOC Light-Theme Dashboard (`templates/index.html`)**:
   - Five dedicated operational workspaces: Overview & SDN Defense, Router Health, Load Balancer, Simulation Lab, and Events & Alerts.
   - Live Chart.js telemetry with visual spike detection and threshold markers.

---

## 4. Quick Start & Execution Guide

### 4.1 Prerequisites (Linux / WSL2 / Remote VM)
```bash
sudo apt update
sudo apt install -y openvswitch-switch mininet iperf3 python3-pip
pip install -r requirements.txt
```

### 4.2 Step 1: Start the SDN Controller
In Terminal 1 (Host root namespace):
```bash
python3 sdn_controller.py
```
*Listens on port `8080` (REST API) and manages OpenFlow datapaths on switches `s1` and `s2`.*

### 4.3 Step 2: Launch the Mininet Topology
In Terminal 2 (with root privileges):
```bash
sudo python3 topology.py
```
*Creates the dual-subnet routed network, starts router `r1` with IP forwarding, and launches all background services (`server.py`, `agent.py`, `load_balancer`, `backend/app.py`, `router_monitor`).*

### 4.4 Step 3: Access the Web Dashboard
Open your web browser:
- Direct access: `http://10.0.1.20:5050`
- Host port-forward: `http://localhost:5050`
- Custom Load Balancer ingress: `http://10.0.1.30:8000`

### 4.5 Step 4: Run Automated Verification & Benchmarks
In a separate terminal:
```bash
# Run unit and integration test suite
python3 -m unittest discover -s tests -p "test_*.py"

# Run end-to-end pipeline verification
python3 demo_runner.py

# Run comprehensive 9-phase performance benchmark suite
python3 performance_eval.py
```

---

## 5. Directory Structure

```
CN-REMOTE-NETWORK-MONITORING-SYSTEM/
├── agent.py                 # Host telemetry & C2 agent
├── server.py                # Central Flask ingestion & control plane
├── db.py                    # SQLite persistence with WAL mode
├── topology.py              # Mininet multi-subnet routed topology
├── sdn_controller.py        # Standalone OpenFlow 1.3 controller & REST API
├── ryu_sdn_controller.py    # Ryu controller implementation
├── demo_runner.py           # E2E pipeline verification script
├── performance_eval.py      # 9-Phase quantitative benchmark suite
│
├── load_balancer/           # Custom Python HTTP reverse proxy
│   ├── proxy.py             # aiohttp async reverse proxy server
│   ├── algorithms.py        # Round Robin, Least Conn, Weighted RR
│   ├── health_checker.py    # Active background /health checking
│   ├── metrics.py           # Latency percentiles & RPS tracker
│   └── config.py            # Backend targets & configuration
│
├── monitoring/              # Real-time monitoring & metrics
│   ├── network_metrics.py   # True throughput rate calculator (Mbps)
│   ├── telemetry.py         # Packet schemas & validation
│   ├── router_monitor.py    # Router r1 health, interface & routing table
│   └── anomaly_detector.py  # Deterministic anomaly detection engine
│
├── simulation/              # Controlled laboratory stress simulation
│   ├── cpu_stress.py        # Bounded CPU load generator
│   ├── network_stress.py    # iperf3 & socket bandwidth burst generator
│   ├── node_failure.py      # Backend outage & failover test
│   ├── router_failure.py    # Router link toggle simulation
│   └── scenarios.py         # Pre-built 8-stage automated demo
│
├── backend/                 # Backend HTTP microservices
│   └── app.py               # Lightweight backend instance (h5-h7)
│
├── services/                # Core platform services
│   └── event_manager.py     # Event lifecycle management & audit trail
│
├── templates/               # Frontend interface
│   └── index.html           # Enterprise NOC light-theme dashboard
│
├── tests/                   # Automated test suite
│   ├── test_telemetry.py    # Unit tests for rates & packets
│   ├── test_router.py       # Unit tests for router classification
│   ├── test_load_balancer.py# Unit tests for RR/LC/WRR algorithms
│   ├── test_anomaly.py      # Unit tests for hysteresis anomaly detection
│   └── test_integration.py  # Integration tests for LB + Backends
│
├── requirements.txt         # Python dependencies
├── CODEBASE_AUDIT.md        # Technical baseline audit report
├── ARCHITECTURE.md          # Complete architectural specification
├── PROJECT_STATE.md         # Milestone status tracking
├── DEMO_GUIDE.md            # Step-by-step evaluator demonstration guide
└── API_DOCUMENTATION.md     # REST API specification
```
