# 🎬 DEMONSTRATION & EVALUATION GUIDE (5–7 MINUTES)
**Remote Network Health Monitor — Industry-Grade Network Operations Platform**

---

## 1. Quick Startup Sequence

To demonstrate the full platform, execute these steps in order:

### Terminal 1: Launch SDN Controller (Root Namespace)
```bash
python3 sdn_controller.py
```
*Expected: "STANDALONE SDN REST CONTROLLER (OVS) Listening on http://0.0.0.0:8080"*

### Terminal 2: Launch Mininet Multi-Subnet Topology
```bash
sudo python3 topology.py
```
*Expected:*
- Creates Switch `s1` (Clients) and `s2` (Backends).
- Starts Linux Layer 3 Router `r1` with `ip_forward=1`.
- Assigns Subnet 1 (`10.0.1.0/24`) and Subnet 2 (`10.0.2.0/24`).
- Launches Central Server on `h4` (`10.0.1.20:5050`).
- Launches Telemetry Agents on `h1`, `h2`, `h3`, `h5`, `h6`, `h7`, and `h8`.
- Launches Backend Microservices on `h5` (8001), `h6` (8002), `h7` (8003).
- Launches Custom Async Load Balancer on `h8` (`10.0.1.30:8000`).
- Launches Router Monitor on `r1`.
- Enters `mininet>` prompt.

### Terminal 3: Access Web Dashboard
Open browser at:
`http://10.0.1.20:5050` (or `http://localhost:5050`)

---

## 2. Seven-Stage Live Demonstration Script

| Stage | Duration | Action Taken | Expected Observation in Dashboard | Technical Explanation |
|---|---|---|---|---|
| **Stage 1: Normal Operation** | 30s | View Overview Tab | All 7 host nodes online, Router `r1` healthy, LB active with 3 backends. | Telemetry streams over UDP 5000; router forwards packets across subnets at wire speed. |
| **Stage 2: CPU Spike** | 45s | Click *Simulation Lab &rarr; Launch CPU Stress* (10s) | Target CPU rises to ~90%. Anomaly detector triggers `CPU_UTILIZATION_CRITICAL` alert. | Bounded worker consumes CPU; 3 consecutive samples above 85% trigger alert; hysteresis recovers when <75%. |
| **Stage 3: Network Throughput Spike** | 45s | Click *Simulation Lab &rarr; Launch Throughput Spike* (50 Mbps) | Telemetry chart visually spikes to ~50 Mbps. `chart-spike-badge` lights up. | `monitoring/network_metrics.py` calculates true instantaneous rate ($\Delta\text{bytes} \times 8 / \Delta t$). |
| **Stage 4: Load Balancer Traffic** | 45s | Switch to *Load Balancer Tab* &rarr; Click *Send HTTP Burst* | Requests distribute across Backend-1, Backend-2, Backend-3. RPS and latency update. | `aiohttp` reverse proxy forwards HTTP requests, tracking per-backend counters and p95 latency. |
| **Stage 5: Backend Outage & Failover** | 60s | Click *Simulation Lab &rarr; Fail Backend-2* | LB health check detects 3 timeouts, marks Backend-2 UNHEALTHY, reroutes all requests to Backend-1 & 3 with 0 errors. Click *Restore* to re-admit. | Active background polling detects failure; dynamic failover excludes failed backend without downtime. |
| **Stage 6: SDN Flow Mitigation** | 60s | Click *Attack* on Node-1 in Overview Tab | Node-1 floods UDP. Server detects surge and calls SDN controller. Switch installs `DROP` rule. Attacker throughput drops to 0 Mbps. Target CPU normalizes. | Controller pushes OpenFlow 1.3 `OFPFlowMod` to Open vSwitch `s1` (`priority=1000, nw_src=10.0.1.11, DROP`). |
| **Stage 7: Full Recovery** | 30s | Click *Clear Rules* & *Stop All Stress* | All metrics return to baseline. Event stream shows `RECOVERED` status. | System restores normal flow tables and state. |

---

## 3. Automated Benchmark Execution

In a separate terminal:
```bash
python3 performance_eval.py
```
This runs all 9 evaluation phases automatically, prints the quantitative benchmark table, and exports `performance_results.json` and `performance_results.csv`.
