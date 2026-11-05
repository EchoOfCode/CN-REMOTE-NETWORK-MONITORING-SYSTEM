# 📋 TWO-ROUTER ARCHITECTURE AUDIT & IMPLEMENTATION PLAN
**Project**: Remote Network Health Monitor — Two-Router Multi-Subnet Architecture  
**Audit Date**: November 5, 2026  
**Auditor**: Senior Network Engineer & SDN Architecture Team  

---

## 1. Architectural Baseline & Delta Analysis

| Component | Existing Implementation (v2.0) | Upgraded Target Architecture (Two-Router v3.0) |
|---|---|---|
| **Routers** | Single Layer 3 Router (`r1`) connecting both subnets | **Two Layer 3 Routers**: `r1` (Client gateway) and `r2` (Backend gateway) |
| **Transit Network** | None (Single router bridged subnets) | **Routed Transit Network**: `10.0.12.0/30` (`r1-eth1: 10.0.12.1/30` <-> `r2-eth0: 10.0.12.2/30`) |
| **Client Network** | `10.0.1.0/24` on switch `s1` (gateway: `10.0.1.1` on `r1-eth0`) | `10.0.1.0/24` on switch `s1` (gateway: `10.0.1.1` on `r1-eth0`) |
| **Backend Network** | `10.0.2.0/24` on switch `s2` (gateway was `r1-eth1`) | `10.0.2.0/24` on switch `s2` (gateway: `10.0.2.1` on `r2-eth1`) |
| **Load Balancer** | `h8` was on `10.0.1.30` (Client subnet) | `h8` on `10.0.2.30` (Backend subnet) with default gateway `10.0.2.1` (`r2`) |
| **Traffic Path** | `Client -> s1 -> r1 -> s2 -> Backends` | **`Client -> s1 -> r1 -> (Transit Link) -> r2 -> s2 -> Load Balancer (h8) -> Backends`** |
| **Packet Loss Tracking** | Aggregate host ping loss | **Localized Segment-Level Loss**: Tracks drops on Client-R1, R1-R2 transit, and R2-Backend |
| **Packet Animation** | Static colored lines on links | **Dynamic Particle Packet Flow**: Animated moving packets (Green=OK, Red=Dropped, Yellow=Delayed) |
| **Backend Power Controls**| API-based status drain | **Physical Power OFF / Power ON** controls per backend with live redistribution (e.g. 50%/0%/50%) |
| **Terminology** | Technical network terms (Throughput, Latency, etc.) | **Plain English NOC**: Network Speed, Response Time, Lost Data, Traffic Manager, Servers |

---

## 2. IP Addressing & Subnet Routing Plan

### 2.1 Subnet Allocations
1. **Client Subnet (`10.0.1.0/24`)**:
   - `r1-eth0`: `10.0.1.1/24` (Default gateway for client devices)
   - `h1`: `10.0.1.11/24`, gw: `10.0.1.1`
   - `h2`: `10.0.1.12/24`, gw: `10.0.1.1`
   - `h3`: `10.0.1.13/24`, gw: `10.0.1.1`
   - `h4`: `10.0.1.20/24`, gw: `10.0.1.1` (Central Monitor & Flask Dashboard)
   - Host OS bridge: `10.0.1.254/24` on `dev s1`

2. **Router Transit Link (`10.0.12.0/30`)**:
   - `r1-eth1`: `10.0.12.1/30`
   - `r2-eth0`: `10.0.12.2/30`
   - Broadcast: `10.0.12.3`, Netmask: `255.255.255.252`

3. **Backend Subnet (`10.0.2.0/24`)**:
   - `r2-eth1`: `10.0.2.1/24` (Default gateway for backend servers and load balancer)
   - `h5`: `10.0.2.11/24`, gw: `10.0.2.1` (Backend Server 1, Port 8001)
   - `h6`: `10.0.2.12/24`, gw: `10.0.2.1` (Backend Server 2, Port 8002)
   - `h7`: `10.0.2.13/24`, gw: `10.0.2.1` (Backend Server 3, Port 8003)
   - `h8`: `10.0.2.30/24`, gw: `10.0.2.1` (Custom Async Load Balancer, Port 8000)

### 2.2 Static Routing Configuration
- On **Router 1 (`r1`)**:
  - `sysctl -w net.ipv4.ip_forward=1`
  - `ip route add 10.0.2.0/24 via 10.0.12.2 dev r1-eth1`
- On **Router 2 (`r2`)**:
  - `sysctl -w net.ipv4.ip_forward=1`
  - `ip route add 10.0.1.0/24 via 10.0.12.1 dev r2-eth0`
- On **Host Root Namespace**:
  - `ip addr add 10.0.1.254/24 dev s1`
  - `ip route add 10.0.12.0/30 via 10.0.1.1 dev s1`
  - `ip route add 10.0.2.0/24 via 10.0.1.1 dev s1`

---

## 3. Implementation Modules & Phasing

1. **`monitoring/packet_loss.py`**: Localizes packet loss and provides plain-English diagnostics.
2. **`monitoring/router_monitor.py`**: Monitors `r1`, `r2`, and the transit link independently.
3. **`topology.py`**: Implements the Two-Router Mininet topology with point-to-point transit link.
4. **`load_balancer/proxy.py`**: Configured for backend network `10.0.2.30:8000`, supporting dynamic power control failover.
5. **`server.py`**: APIs for R1, R2, transit link, packet loss statistics, and backend power controls.
6. **`templates/index.html`**: Plain-English NOC dashboard with live particle animations, Power ON/OFF controls, 4 live graphs, and 9 demonstration scenarios.

