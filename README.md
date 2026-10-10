# Remote System Health Monitoring & SDN Attack Mitigation System

A Computer Networks project combining socket-based host telemetry, OpenFlow Software-Defined Networking (SDN), and automated attack mitigation.

## Windows Quick Start (1-Click)
Simply double-click or run:
```cmd
start.bat
```
This automatically verifies Python dependencies, launches the Controller, Central Server, and 3 Agent nodes in separate windows, and opens the live dashboard at `http://127.0.0.1:5050`.

## Linux / WSL Quick Start (1-Click)
Run:
```bash
chmod +x start.sh
./start.sh
```
This gives an interactive menu to launch either the full **Mininet + Ryu Pipeline** or a **Local Simulation**, and can also clean up background processes.

## Mininet Manual Launch (3 Steps)

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
