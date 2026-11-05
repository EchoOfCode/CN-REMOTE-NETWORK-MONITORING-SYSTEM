# 📋 CODEBASE AUDIT & TECHNICAL BASELINE REPORT
**Project**: Remote Network Health Monitor — Industry-Grade Network Monitoring, Traffic Management & SDN Platform  
**Audit Date**: November 5, 2026  
**Auditor**: Principal Network Software Architect & SRE Team  

---

## 1. Executive Summary

This audit assesses the current state of the **Remote Network Health Monitor** repository (`EchoOfCode/CN-REMOTE-NETWORK-MONITORING-SYSTEM`). The existing platform provides functional socket-based telemetry collection, an authenticated TCP command-and-control (C2) mechanism, an automated traffic-anomaly detector, a standalone/Ryu OpenFlow 1.3 SDN controller, an Open vSwitch (OVS) flow-mod installer, and an enterprise light-theme monitoring dashboard.

To evolve this repository into an industry-grade, production-defensible network operations and traffic management platform meeting all project requirements, the system must undergo structured architectural enhancements across 6 milestones.

---

## 2. File-by-File Audit & Inventory

| File | Lines | Existing Responsibility | Assessment & Status | Technical Debt / Gaps Identified |
|---|---|---|---|---|
| `agent.py` | 224 | Host telemetry collector & TCP C2 server | **Operational** | Uses cumulative byte counts rather than true instantaneous rate ($Mbps = \frac{\Delta \text{bytes} \times 8}{\Delta t \times 10^6}$). Hardcoded 3s loop. |
| `server.py` | 348 | Central Flask web server, UDP receiver, C2 dispatcher, SDN caller | **Operational** | Monolithic design: mixes HTTP routing, UDP socket ingestion, in-memory locking, anomaly detection, and SDN client logic. Needs separation into `services/` and `monitoring/`. |
| `db.py` | 121 | SQLite storage with WAL mode | **Operational** | Only defines `health_data` and `sdn_events`. Lacks tables for routers, interfaces, load balancers, backend nodes, and audit logs. |
| `sdn_controller.py` | 167 | Standalone REST API (port 8080) & direct OVS flowmod manager | **Operational** | Works reliably in Linux/OVS. Needs switch connection tracking for multiple switches (`s1`, `s2`). |
| `ryu_sdn_controller.py` | 308 | Ryu OpenFlow 1.3 controller with WSGI REST API | **Operational** (where Ryu installed) | Fails on Python 3.12+/3.14 due to PEP 668 and legacy dependencies; standalone controller serves as primary Linux fallback. |
| `topology.py` | 138 | Mininet topology script (4 hosts, 1 switch) | **Operational** | Flat Layer 2 topology on `10.0.0.0/24`. Missing Layer 3 router `r1`, backend switch `s2`, subnets `10.0.1.0/24` & `10.0.2.0/24`, load balancer `h8`, and backends `h5`-`h7`. |
| `demo_runner.py` | 294 | Automated end-to-end verification script | **Operational** | Verifies 5 checks for flat topology. Needs expansion for dual-subnet and load-balancer validation. |
| `performance_eval.py` | 255 | Quantitative benchmark suite | **Operational** | Implements 3 phases (Baseline, Flood, Mitigated). Needs expansion to all 9 evaluation phases. |
| `templates/index.html` | 1,180 | NOC Dashboard Web Interface | **Operational** | Fully implemented enterprise light-theme UI, but inline CSS/JS (58KB). Needs modular assets in `static/css/` and `static/js/`. |
| `requirements.txt` | 14 | Python dependencies | **Operational** | Minimal dependencies (`flask`, `psutil`, `webob`, `requests`). Missing `aiohttp` for async load balancer. |

---

## 3. Detailed Component Breakdown

### 3.1 Telemetry & Agent Plane (`agent.py`)
- **Strengths**:
  - Clean separation between UDP telemetry loop and TCP C2 listener using daemon threads.
  - Sockets properly bound with `SO_REUSEADDR`.
  - Secure C2 command handling requiring `token == C2_SHARED_SECRET`.
  - Accurate CPU and memory metrics via `psutil`.
- **Gaps & Defects**:
  - `bytes_sent` and `bytes_recv` are cumulative integers from system boot. When an attack starts, the agent adds synthetic packet counts to `bytes_sent`. True network rate ($Mbps$) is not calculated per interval.
  - Lacks sequence numbering, packet drop/error tracking, and interface-level statistics.
  - Telemetry interval is fixed at 3 seconds without dynamic adjustment.

### 3.2 Ingestion & Orchestration Plane (`server.py`)
- **Strengths**:
  - Non-blocking UDP socket ingestion in a background thread.
  - Thread-safe state updates using `threading.Lock()`.
  - Dynamic discovery of SDN controller between Mininet bridge IP (`10.0.0.254:8080`) and localhost (`127.0.0.1:8080`).
  - Automated mitigation trigger on delta byte surge (`sent_delta > 2,000,000`).
- **Gaps & Defects**:
  - High cyclomatic complexity in `server.py`.
  - Lacks structured event management and alert lifecycle tracking (`DETECTED -> ACKNOWLEDGED -> MITIGATING -> RECOVERED`).
  - No endpoints for router metrics, load balancer configuration, or controlled stress testing.

### 3.3 SDN & Data Plane (`sdn_controller.py`, `ryu_sdn_controller.py`)
- **Strengths**:
  - Direct kernel programming via `ovs-ofctl -O OpenFlow13 add-flow` bypasses legacy library incompatibilities.
  - Exposes REST endpoints: `GET /api/v1/sdn/stats`, `POST /api/v1/sdn/mitigate`, `POST /api/v1/sdn/unblock`.
  - Flow table verification against actual switch state.
- **Gaps & Defects**:
  - Currently hardcoded for single switch `s1`. Must support multi-switch environments (`s1` and `s2`).
  - Flow stats currently track in-memory blocked list; should poll real OVS flow counters (`n_packets`, `n_bytes`).

### 3.4 Storage Plane (`db.py`)
- **Strengths**:
  - SQLite with WAL (`PRAGMA journal_mode=WAL;`) ensures concurrent readers and writers without lock contention.
  - Indexed queries for `agent_id` and `timestamp`.
- **Gaps & Defects**:
  - Missing operational tables: `nodes`, `routers`, `router_interfaces`, `backend_nodes`, `load_balancer_config`, `lb_metrics`, `system_events`, `simulation_events`, `audit_logs`.

### 3.5 Network Topology Plane (`topology.py`)
- **Strengths**:
  - Deterministic startup and shutdown with process cleanup (`pkill`).
  - Assigns `10.0.0.254` to switch `s1` so host OS can reach Mininet web server.
- **Gaps & Defects**:
  - Flat L2 broadcast domain (`10.0.0.0/24`). Lacks Layer 3 segmentation, router `r1`, backend switch `s2`, load balancer `h8`, and backends `h5`-`h7`.

---

## 4. Port Allocation & Conflict Audit

| Port | Protocol | Component | Role | Conflict Risk & Mitigation |
|---|---|---|---|---|
| `5000` | UDP | `server.py` | Telemetry Ingestion | **Low**: Dedicated UDP socket. Use `SO_REUSEADDR`. |
| `5001-5003` | TCP | `agent.py` (`h1`-`h3`) | C2 Command Listeners | **Low**: Scoped to individual host namespaces. |
| `5004` | TCP | `r1` (Router) | Router Telemetry / Management | **Planned**: Dedicated to router `r1`. |
| `5005-5007` | TCP | `agent.py` (`h5`-`h7`) | Backend Node C2 Listeners | **Planned**: Backend node namespaces. |
| `5008` | TCP | `h8` (LB) | Load Balancer C2 / Management | **Planned**: Dedicated to `h8`. |
| `5050` | TCP | `server.py` (`h4`) | Flask Web Dashboard & API | **Low**: Host bridge mapped via `s1`. |
| `6653` | TCP | `c0` (SDN) | OpenFlow 1.3 Control Channel | **Medium**: Avoid multiple controllers binding simultaneously. |
| `8000` | TCP | `h8` (LB) | HTTP Reverse Proxy Ingress | **Planned**: Bound inside `h8` namespace. |
| `8001-8003` | TCP | `h5`-`h7` | Backend Microservices | **Planned**: Bound inside `h5`, `h6`, `h7` namespaces. |
| `8080` | TCP | `sdn_controller.py` | SDN REST Mitigation API | **Medium**: Managed with `allow_reuse_address = True`. |
| `5201` | TCP | `iperf3` | Network Throughput Stress Testing | **Planned**: Transient benchmark listener. |

---

## 5. Architectural Risks & Mitigation Strategies

1. **Dual-Subnet Routing in Mininet Namespaces**:
   - *Risk*: Backend nodes (`10.0.2.0/24`) cannot communicate with Central Server `h4` (`10.0.1.20`) if routing tables or ARP resolution fail on `r1`.
   - *Mitigation*: Program explicit default gateways on all hosts (`ip route add default via 10.0.1.1` on Subnet 1, `via 10.0.2.1` on Subnet 2), enable kernel IP forwarding on `r1` (`net.ipv4.ip_forward=1`), and add automated ping sweep tests during topology boot.

2. **Python 3.14 PEP 668 & Ryu Compatibility**:
   - *Risk*: Legacy Ryu controller cannot be installed on modern Linux distributions without custom patches.
   - *Mitigation*: Maintain `sdn_controller.py` as a zero-dependency standalone OpenFlow manager that directly invokes `ovs-ofctl` while offering the exact same REST interface.

3. **Background Process Orphanage**:
   - *Risk*: Exiting Mininet or crashing leaves python processes holding ports `5000`, `5050`, `8000`, `8080`.
   - *Mitigation*: Add robust exit traps and process cleanup scripts (`fuser -k`, `pkill -f`) in `topology.py`, `cleanup.sh`, and test harnesses.

---

## 6. Migration & Modernization Roadmap

- **Milestone 1**: Expand Mininet topology to dual subnets (`10.0.1.0/24` and `10.0.2.0/24`), Linux Router `r1`, switches `s1` and `s2`, load balancer `h8`, and backends `h5`-`h7`.
- **Milestone 2**: Build modular telemetry calculation (`monitoring/network_metrics.py`) and router monitor (`monitoring/router_monitor.py`).
- **Milestone 3**: Build custom Python HTTP load balancer (`load_balancer/`) with Round Robin, Least Connections, Weighted Round Robin, active health checks, and dynamic failover.
- **Milestone 4**: Build simulation engine (`simulation/`) for CPU stress, `iperf3` bandwidth stress, backend failure, and router interface failure, integrated with anomaly detector (`monitoring/anomaly_detector.py`).
- **Milestone 5**: Redesign NOC dashboard with modular assets and dedicated operational views.
- **Milestone 6**: Expand benchmark suite (`performance_eval.py`) to 9 comprehensive evaluation phases.
