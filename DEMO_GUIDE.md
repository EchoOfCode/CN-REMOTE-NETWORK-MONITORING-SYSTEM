# 🎬 DEMONSTRATION & EVALUATOR WALKTHROUGH GUIDE
**Remote Network Health Monitor — Operator-Controlled NOC Lab**
**Architecture**: Two-Router Multi-Subnet Topology with Open vSwitch & Custom Async Load Balancer

---

## 1. Quick Startup Sequence

### Step 1: Launch SDN Controller (Terminal 1)
```bash
python3 sdn_controller.py
```
*Expected output*: `STANDALONE SDN REST CONTROLLER (OVS) Listening on http://0.0.0.0:8080`

### Step 2: Launch Mininet Two-Router Topology (Terminal 2)
```bash
sudo python3 topology.py
```
*Expected topology elements automatically launched*:
- **Router 1 (`r1`)**: Client Gateway (`r1-eth0: 10.0.1.1/24`) and Transit Trunk (`r1-eth1: 10.0.12.1/30`)
- **Router 2 (`r2`)**: Transit Trunk (`r2-eth0: 10.0.12.2/30`) and Backend Gateway (`r2-eth1: 10.0.2.1/24`)
- **Point-to-Point Transit Link**: Subnet `10.0.12.0/30` interconnecting `r1` & `r2`
- **Clients (`h1`, `h2`, `h3`)**: Subnet 1 (`10.0.1.11`, `10.0.1.12`, `10.0.1.13`)
- **Monitoring & C2 Server (`h4`)**: `10.0.1.20:5050`
- **Backends (`h5`, `h6`, `h7`)**: Subnet 2 microservices on ports `8001`, `8002`, `8003`
- **Load Balancer (`h8`)**: High-performance async proxy on `10.0.2.30:8000`

### Step 3: Access Web Dashboard (Browser)
Open your browser at:
`http://10.0.1.20:5050` (or `http://localhost:5050`)

---

## 2. Ten-Section Operator NOC Tour

| Section | Key Capability | Demonstration Highlights |
|---|---|---|
| **1. Overview & Topology** | Visual Canvas & Metrics | Animated 60fps packet canvas, dynamic auto-scaling Chart.js (idle 0.003 Mbps at ~40% height, expands on spikes), backend power toggles. |
| **2. System Control Centre** | Granular Lab Control | Sub-tabs for Nodes ($h_1$–$h_8$), Routers ($r_1$, $r_2$), Switches ($s_1$, $s_2$), and Link `tc netem` impairments. |
| **3. Traffic & Packet Ops** | Probes & Ring Buffer | Synthetic ICMP Ping, UDP Bandwidth surge, HTTP benchmarks, bounded 500-packet ring buffer capture. |
| **4. Two Routers & Transit** | L3 Routing Observability | Inspect `r1`, `r2`, and `10.0.12.0/30` transit link latency, drops, and routing tables. |
| **5. Load Balancer** | Traffic Management | Real-time Round Robin, Least Connections, and Weighted RR; live RPS & latency. |
| **6. SDN & OpenFlow** | Programmable Data Plane | Dump OpenFlow 1.3 flow tables, install manual DROP rules, clear FlowMods. |
| **7. Fault Injection Lab** | Controlled Stressors | One-click triggers for CPU stress, network surge, link packet loss, server power failure. |
| **8. 9-Phase Scenarios** | Evaluator Rubric | Automated one-click execution of all 9 core demonstration rubric scenarios. |
| **9. Events & Audit Log** | Traceability | Plain-English event lifecycle (`DETECTED -> MITIGATING -> RECOVERED`) & SQLite operations audit trail. |
| **10. Diagnostics & Reports**| Forensics & Reconciliation | 11-plane deep health check, CSV forensic report download, one-click full baseline recovery. |

---

## 3. Evaluator 9-Phase Rubric Walkthrough

| Phase | Duration | Operator Action | Expected Observable Outcome | Technical Plain-English Explanation |
|---|---|---|---|---|
| **Phase 1: Baseline** | 30s | Click *Run Baseline Check* | All 7 agents online, 0% packet loss, R1 & R2 healthy, chart shows smooth 0.003 Mbps baseline. | Packets cross Subnet 1 $\rightarrow$ R1 $\rightarrow$ Transit $\rightarrow$ R2 $\rightarrow$ Subnet 2 at wire speed. |
| **Phase 2: CPU Spike** | 30s | Click *Trigger CPU Spike* | Workload climbs to 90%+. `CPU_UTILIZATION_CRITICAL` alert triggers. | Multiprocessing burner stresses cores; anomaly engine detects surge; hysteresis clears after load normalizes. |
| **Phase 3: Raw Surge** | 30s | Click *Observe Raw Spike* | Auto-Remediation turns OFF. 45 Mbps surge flows unmitigated. Chart climbs to top with `SPIKE DETECTED`. | Demonstrates that the platform truly measures and plots live network bandwidth. |
| **Phase 4: SDN Defense**| 30s | Click *Test Auto-Defense* | Auto-Remediation turns ON. Attacker floods; in < 2s, SDN Controller installs FlowMod DROP; traffic drops to 0 Mbps. | OpenFlow 1.3 `OFPFlowMod` pushes `nw_src=10.0.1.11, action=DROP` to switch `s1`. |
| **Phase 5: Power OFF h6**| 30s | Click *Power OFF Server 2* | Server 2 powers down. Load Balancer detects outage and redistributes traffic: **50% Server 1, 0% Server 2, 50% Server 3**. | Reverse proxy detects offline state and re-weights upstream pool without dropping client sessions. |
| **Phase 6: Power ON h6** | 30s | Click *Power ON Server 2* | Server 2 powers back on. Load Balancer re-admits it; traffic shares return to **33.3% / 33.3% / 33.3%**. | Dynamic health checks verify server recovery and re-admit it to the healthy rotation. |
| **Phase 7: Link Loss** | 30s | Click *Test Link Loss* | 24% loss applied to Transit Link. Diagnostic banner turns warning: *"Packet Loss Detected on Router 1 &harr; Router 2 Transit Link"*. | Three-segment loss localization accurately isolates the impaired link. |
| **Phase 8: Switch Algo** | 20s | Click *Switch Algorithm* | Algorithm toggles from Round Robin to Least Connections. | Load Balancer switches request scheduling strategy dynamically without restarting proxy. |
| **Phase 9: Full Recovery**| 30s | Click *Full Recovery* | All impairments cleared, backends ON, SDN drop rules removed, baseline reconciled. | `services/recovery.py` deterministically audits and reverses all modifications. |

---

## 4. Automated Performance Benchmark Execution

To run the automated benchmark matrix:
```bash
python3 performance_eval.py
```
This tests all 9 phases programmatically, prints the performance matrix table, and outputs:
- `performance_results.json`
- `performance_results.csv`
