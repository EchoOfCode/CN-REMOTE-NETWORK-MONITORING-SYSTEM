# 📊 PROJECT STATE & MILESTONE TRACKER
**Project**: Remote Network Health Monitor — Industry-Grade Network Monitoring, Traffic Management & SDN Platform  
**Last Updated**: November 5, 2026  
**Status**: Active Development  

---

## 1. Milestone Status Dashboard

| Milestone | Name | Focus | Status | Progress |
|---|---|---|---|---|
| **M0** | **Codebase Audit & Foundation** | File inventory, architecture analysis, port audit, DB schema expansion | **COMPLETED** | 100% |
| **M1** | **Infrastructure & Topology** | Dual-subnet routed Mininet topology, Linux Router `r1`, `s1`, `s2`, `h1`-`h8` | **IN PROGRESS** | 20% |
| **M2** | **Monitoring & Router Telemetry** | True throughput rates (Mbps), router metrics, link status, packet drops | **PENDING** | 0% |
| **M3** | **Load Balancer & Backend Services**| Custom `aiohttp` proxy, RR/LC/WRR, `/health` checking, dynamic failover | **PENDING** | 0% |
| **M4** | **Simulation Engine & Anomaly Engine**| CPU stress, `iperf3` bandwidth stress, backend/router failure, event lifecycle | **PENDING** | 0% |
| **M5** | **Professional NOC Dashboard** | Modular UI assets, tabs for Router, LB, Simulation Lab, Live Telemetry | **PENDING** | 0% |
| **M6** | **Comprehensive Benchmark Suite** | 9-phase evaluation, quantitative metric comparison, JSON/CSV exports | **PENDING** | 0% |

---

## 2. Acceptance Criteria Matrix (Section 21 Mapping)

| ID | Requirement | Verification Method | Status |
|---|---|---|---|
| **AC01** | Existing functionality remains operational | `demo_runner.py` / C2 attack verification | **PASS** |
| **AC02** | Expanded Mininet topology starts correctly | `python3 topology.py` | **IN PROGRESS** |
| **AC03** | Routing between client & backend subnets works | `h1 ping -c 3 h5` via `r1` | **PENDING** |
| **AC04** | All nodes transmit telemetry | Central server UDP ingestion table | **PENDING** |
| **AC05** | Actual CPU spikes are visible | CPU stress simulation + real psutil sampling | **PENDING** |
| **AC06** | Actual network throughput spikes visible | `iperf3` bandwidth test + rate calculation | **PENDING** |
| **AC07** | Historical telemetry stored correctly | SQLite query verification | **PASS** |
| **AC08** | Router health is monitored | `monitoring/router_monitor.py` | **PENDING** |
| **AC09** | Interface failures are detected | `ip link set down` event trigger | **PENDING** |
| **AC10** | Custom LB forwards real HTTP requests | `curl http://10.0.1.30:8000` -> backend | **PENDING** |
| **AC11** | All three balancing algorithms work | Round Robin, Least Conn, Weighted RR | **PENDING** |
| **AC12** | Backend health checks operate correctly | `GET /health` polling | **PENDING** |
| **AC13** | Failed backends removed automatically | Service kill -> LB auto-drain | **PENDING** |
| **AC14** | Recovered backends re-enter service | Service restart -> LB auto-restore | **PENDING** |
| **AC15** | Traffic distribution is measurable | Per-backend request counters | **PENDING** |
| **AC16** | SDN rules verified against switch | `ovs-ofctl -O OpenFlow13 dump-flows s1` | **PASS** |
| **AC17** | Alerts and events are recorded | Event database & audit log | **PASS** |
| **AC18** | Dashboard displays actual system state | Live NOC web interface | **PASS** |
| **AC19** | Simulation controls perform actual operations | Bounded stress workloads | **PENDING** |
| **AC20** | Full demo scenario executes successfully | 7-minute automated demo script | **PENDING** |
| **AC21** | Performance reports generated | `performance_results.json` & `.csv` | **IN PROGRESS** |
| **AC22** | Shutdown and restart work cleanly | Clean interface teardown & process kill | **PASS** |

---

## 3. Known Issues & Resolution Log

1. **Issue**: `ryu-manager` is incompatible with Python 3.12+ and Python 3.14 on Linux due to outdated WebOb/eventlet dependencies and PEP 668.
   - *Status*: **Resolved**. `sdn_controller.py` provides direct Open vSwitch hardware programming via `ovs-ofctl` while offering the exact same REST interface.
2. **Issue**: Mininet `server.py` on host `h4` attempted to reach `127.0.0.1:8080` for SDN controller, hitting `h4`'s internal loopback rather than the host root namespace.
   - *Status*: **Resolved**. `topology.py` configures `10.0.0.254/24` (and `10.0.1.254/24`) on switch `s1` so `h4` routes directly to the controller at `http://10.0.0.254:8080`.
3. **Issue**: Port `8080` socket remaining in `TIME_WAIT` across controller restarts.
   - *Status*: **Resolved**. Added `allow_reuse_address = True` in `sdn_controller.py` and `fuser -k 8080/tcp` cleanup.

---

## 4. Current Work in Progress

- Executing **Milestone 1**:
  - Updating `db.py` to support expanded relational tables.
  - Updating `topology.py` to instantiate `r1` (Linux Layer 3 Router), `s1` (Client OVS), `s2` (Backend OVS), `h1`-`h3` (Clients), `h4` (Monitor), `h8` (Load Balancer), and `h5`-`h7` (Backends).
