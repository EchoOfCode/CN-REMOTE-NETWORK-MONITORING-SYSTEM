# 📡 REST API SPECIFICATION
**Remote Network Health Monitor — Operator-Controlled NOC Lab**
**Architecture**: Two-Router Multi-Subnet Architecture (`v3.0.0`)

---

## Table of Contents
1. [General Telemetry & Monitoring APIs](#1-general-telemetry--monitoring-apis)
2. [System Lifecycle & Health APIs](#2-system-lifecycle--health-apis)
3. [Node Lifecycle Management APIs](#3-node-lifecycle-management-apis)
4. [Two-Router Management APIs](#4-two-router-management-apis)
5. [Open vSwitch & OpenFlow Switch APIs](#5-open-vswitch--openflow-switch-apis)
6. [Link Impairment & Traffic Control (`tc netem`) APIs](#6-link-impairment--traffic-control-tc-netem-apis)
7. [Traffic Generator & Benchmark APIs](#7-traffic-generator--benchmark-apis)
8. [Real-Time Packet Monitor & Ring Buffer Capture APIs](#8-real-time-packet-monitor--ring-buffer-capture-apis)
9. [Custom Load Balancer APIs](#9-custom-load-balancer-apis)
10. [SDN Controller & OpenFlow APIs](#10-sdn-controller--openflow-apis)
11. [Operations Audit, Diagnostics & Forensic Reporting APIs](#11-operations-audit-diagnostics--forensic-reporting-apis)

---

## 1. General Telemetry & Monitoring APIs

### `GET /api/health`
Checks server health.
- **Response**: `200 OK`
```json
{
  "status": "HEALTHY",
  "service": "CENTRAL_MONITORING_PLANE",
  "timestamp": "2026-11-05 10:50:00"
}
```

### `GET /api/metrics`
Aggregated telemetry, two-router state, transit metrics, SDN rules, load balancer state, packet loss localization, active operations, traffic jobs, and bounded packet ring buffer summary.
- **Response**: `200 OK`

---

## 2. System Lifecycle & Health APIs

### `GET /api/system/status`
Performs an audit across all 11 infrastructure planes (Monitor API, SDN Ryu, Load Balancer, Backends 1–3, Database WAL, Routers r1/r2, Switches s1/s2, Transit Link).

### `POST /api/system/reset`
Triggers full deterministic baseline reconciliation: reverses all link impairments, ensures all router interfaces are UP, restores backends, and clears temporary SDN rules.

### `POST /api/system/emergency-stop`
Immediate kill switch that halts all active background traffic generators and CPU stress tasks, and clears link drops.

---

## 3. Node Lifecycle Management APIs

### `GET /api/nodes/all`
Returns full registry status for all topology hosts (`h1` through `h8`).

### `GET /api/nodes/<node_id>/details`
Returns deep inspection metrics including CPU, RAM, active process counts, and interface counters.

### `POST /api/nodes/<node_id>/isolate`
Simulates link disconnection by bringing interface DOWN.

### `POST /api/nodes/<node_id>/restore`
Restores host link connection to switch.

### `POST /api/nodes/<node_id>/power_off`
Shuts down host service/process; if backend node, automatically coordinates with Load Balancer upstream rotation.

### `POST /api/nodes/<node_id>/power_on`
Restores host service/process and re-admits to Load Balancer rotation.

### `POST /api/nodes/<node_id>/ping`
Executes real ICMP reachability probe from the node.
- **Request Body**:
```json
{ "target_ip": "10.0.1.20", "count": 4 }
```

---

## 4. Two-Router Management APIs

### `GET /api/routers`
Returns status of Router 1 (`r1`), Router 2 (`r2`), and the point-to-point transit link (`10.0.12.0/30`).

### `GET /api/routers/<router_id>/details`
Returns per-interface health, routing tables, and forwarding state.

### `POST /api/routers/<router_id>/interfaces/<interface>/<action>`
Controls individual router interface state (`up`, `down`, or `restart`) with pre-flight impact audit.

### `POST /api/routers/<router_id>/ping`
Runs ping test from router namespace across transit link.

---

## 5. Open vSwitch & OpenFlow Switch APIs

### `GET /api/switches`
Returns controller connection state and port registry for `s1` and `s2`.

### `GET /api/switches/<switch_id>/flows`
Dumps active OpenFlow 1.3 flow table with match fields and packet/byte counters.

### `POST /api/switches/<switch_id>/ports/<port>/<action>`
Enables or disables OpenFlow switch port (`UP` or `DOWN`).

### `POST /api/switches/<switch_id>/flows/delete`
Deletes a matching OpenFlow rule from the switch data plane.

---

## 6. Link Impairment & Traffic Control (`tc netem`) APIs

### `GET /api/links`
Returns status and active impairment parameters for all 5 topology links:
- `r1-r2` (Transit Link)
- `h1-s1` (Client Link)
- `s1-r1` (Gateway Link)
- `r2-s2` (Backend Switch Link)
- `s2-h8` (Load Balancer Link)

### `POST /api/links/<link_id>/configure`
Applies real Linux Traffic Control (`tc netem`) impairments:
```json
{
  "loss_percent": 24.0,
  "delay_ms": 50.0,
  "jitter_ms": 10.0,
  "rate_mbps": 10.0
}
```

### `POST /api/links/<link_id>/reset`
Clears all `tc netem` rules and restores clean 0% loss baseline.

---

## 7. Traffic Generator & Benchmark APIs

### `GET /api/traffic/jobs`
Returns all active and completed traffic generator jobs.

### `POST /api/traffic/ping/start`
Starts an asynchronous ICMP probe job with target, packet count, and interval.

### `POST /api/traffic/udp/start`
Starts a controlled UDP bandwidth surge job with specified Mbps rate, duration, and packet size.

### `POST /api/traffic/http/start`
Starts concurrent HTTP benchmark requests against the Load Balancer proxy.

### `POST /api/traffic/<job_id>/stop`
Stops a specific running traffic job.

### `POST /api/traffic/stop-all`
Stops all running traffic generator jobs immediately.

---

## 8. Real-Time Packet Monitor & Ring Buffer Capture APIs

### `GET /api/packets/summary`
Returns total observed packets, dropped packets, overall loss rate %, and protocol distribution.

### `GET /api/packets/capture?limit=50&proto=UDP`
Queries the bounded 500-packet ring buffer with optional filtering by protocol, source IP, destination IP, and status.

### `GET /api/metrics/packet-loss`
Returns three-segment packet loss localization diagnosis with plain-English human-friendly explanations.

---

## 9. Custom Load Balancer APIs

### `GET /api/lb/status`
Returns active algorithm, healthy backend count, and traffic distribution.

### `POST /api/lb/algorithm`
Dynamically switches algorithm between `round_robin`, `least_connections`, and `weighted_round_robin`.

### `POST /api/backend/<id>/power_off` & `power_on`
Controls power state and redistributes traffic shares dynamically (e.g. 50% / 0% / 50%).

---

## 10. SDN Controller & OpenFlow APIs

### `POST /api/sdn/remediation_toggle`
Toggles automated SDN defense (`ON` = active mitigation in < 2s; `OFF` = observation mode to observe raw traffic spikes).

### `POST /api/sdn/mitigate`
Installs OpenFlow 1.3 DROP flowmod rule for specified source IP.

### `POST /api/sdn/unblock`
Removes OpenFlow DROP flowmod rule for specified source IP or `"ALL"`.

---

## 11. Operations Audit, Diagnostics & Forensic Reporting APIs

### `GET /api/operations?limit=50`
Queries execution lifecycle of all operator commands (`REQUESTED -> VALIDATING -> EXECUTING -> VERIFYING -> SUCCESS/FAILED`).

### `GET /api/diagnostics`
Gathers full JSON diagnostic forensic snapshot.

### `GET /api/diagnostics/export.csv`
Streams CSV-formatted audit log and system events for forensic evaluation.
