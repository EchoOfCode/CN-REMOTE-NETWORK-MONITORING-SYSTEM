# Remote System Health Monitoring & SDN Attack Mitigation System

A Computer Networks project combining socket-based host telemetry, OpenFlow Software-Defined Networking (SDN), and automated attack mitigation.

## Quick Start (3 Steps)

### Step 1: Start Ryu SDN Controller (Terminal 1)
```bash
ryu-manager ryu_sdn_controller.py --wsapi-port 8080
```

### Step 2: Start Mininet Network Topology (Terminal 2, with root)
```bash
sudo python3 topology.py
```
* Hosts `h1` (`10.0.0.1`), `h2` (`10.0.0.2`), and `h3` (`10.0.0.3`) run `agent.py`.
* Host `h4` (`10.0.0.4`) runs `server.py` and the Flask dashboard on port `5050`.

### Step 3: Run the Verification Test Suite (Terminal 3)
```bash
python3 demo_runner.py
```

### Web Dashboard
Open in your browser:
* Direct: `http://10.0.0.4:5050`
* Or via host port-forward: `http://localhost:5050`
