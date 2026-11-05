# 📡 REST API SPECIFICATION
**Remote Network Health Monitor Platform**

---

## 1. General Telemetry & Monitoring APIs

### `GET /api/health`
Checks server health.
- **Response**: `200 OK`
```json
{
  "status": "HEALTHY",
  "service": "CENTRAL_MONITORING_PLANE",
  "timestamp": "2026-11-05 09:50:00"
}
```

### `GET /api/metrics`
Aggregated telemetry, router health, SDN rules, and load balancer state.
- **Response**: `200 OK`
```json
{
  "nodes": [...],
  "router": {...},
  "sdn": {...},
  "load_balancer": {...},
  "events": [...],
  "db_history": [...]
}
```

### `GET /api/nodes`
Returns list of all active registered nodes.

---

## 2. Router Health APIs

### `GET /api/router`
Returns Linux Layer 3 Router (`r1`) health report.
- **Response**: `200 OK`
```json
{
  "router_id": "r1",
  "status": "HEALTHY",
  "system": {
    "cpu_percent": 4.2,
    "memory_percent": 18.5,
    "uptime_seconds": 120
  },
  "throughput": {
    "upload_mbps": 0.45,
    "download_mbps": 0.38,
    "packet_drops": 0
  },
  "connectivity": {
    "target": "10.0.1.20",
    "latency_ms": 0.45,
    "packet_loss_percent": 0.0
  }
}
```

### `GET /api/router/interfaces`
Returns network interfaces (`r1-eth0`, `r1-eth1`) and operational states (`UP`/`DOWN`).

### `GET /api/router/routes`
Returns active kernel routing tables on router `r1`.

---

## 3. Custom Load Balancer APIs

### `GET /api/lb/status`
Returns reverse proxy configuration, healthy backends, and metrics.

### `POST /api/lb/algorithm`
Switches load balancing algorithm dynamically.
- **Request Body**:
```json
{ "algorithm": "least_connections" }
```
- **Algorithms**: `round_robin`, `least_connections`, `weighted_round_robin`.

### `POST /api/lb/backend/<id>/drain`
Places a backend in graceful draining mode.

### `POST /api/lb/backend/<id>/restore`
Restores a backend to healthy status.

---

## 4. Simulation Lab APIs

### `POST /api/simulation/cpu/start`
Launches bounded CPU stress on local host or selected node.
- **Request Body**:
```json
{ "duration": 10, "intensity": 0.95 }
```

### `POST /api/simulation/network/start`
Launches network throughput burst.
- **Request Body**:
```json
{ "target": "10.0.1.20", "mbps": 50, "duration": 8 }
```

### `POST /api/simulation/backend/fail`
Simulates backend service failure (e.g. `backend-2`).

### `POST /api/simulation/backend/restore`
Restores failed backend service.

### `POST /api/simulation/stop`
Emergency stop halting all active stressors.

---

## 5. SDN Controller APIs

### `GET /api/sdn/stats` or `GET /api/v1/sdn/stats` (Port 8080)
Returns active OpenFlow 1.3 flow rules and managed switches (`s1`, `s2`).

### `POST /api/sdn/mitigate` or `POST /api/v1/sdn/mitigate` (Port 8080)
Installs an OpenFlow 1.3 DROP flowmod into Open vSwitch hardware.
- **Request Body**:
```json
{
  "src_ip": "10.0.1.11",
  "agent_id": "Node-1"
}
```

### `POST /api/sdn/unblock` or `POST /api/v1/sdn/unblock` (Port 8080)
Deletes OpenFlow DROP flowmod, restoring normal traffic flow.
- **Request Body**:
```json
{
  "src_ip": "10.0.1.11"
}
```
