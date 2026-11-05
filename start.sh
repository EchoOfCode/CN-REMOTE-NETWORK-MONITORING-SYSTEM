#!/usr/bin/env bash
# ==============================================================================
# Remote Network Health Monitor — Unified Startup & Lab Management Script
# Industry-Grade Two-Router Multi-Subnet SDN Platform
# ==============================================================================

set -e

# Change directory to the repository directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ANSI Colors
GREEN="\033[92m"
RED="\033[91m"
YELLOW="\033[93m"
CYAN="\033[96m"
BOLD="\033[1m"
RESET="\033[0m"

# Detect Python 3 binary
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    echo -e "${RED}[ERROR] Python 3 was not found on your system!${RESET}"
    exit 1
fi

# Ensure required Python dependencies exist
check_dependencies() {
    echo -e "[*] Checking Python dependencies (flask, psutil, aiohttp)..."
    if ! $PY_BIN -c "import flask, psutil" >/dev/null 2>&1; then
        echo -e "[*] Installing required packages from requirements.txt..."
        if [ -f "requirements.txt" ]; then
            $PY_BIN -m pip install -r requirements.txt || {
                echo -e "${YELLOW}[WARNING] pip install failed. If in Debian/Ubuntu, run: sudo apt install python3-flask python3-psutil python3-aiohttp${RESET}"
            }
        else
            $PY_BIN -m pip install flask psutil aiohttp || true
        fi
    fi
}

# Stop all background components and clean Mininet & ports
stop_all() {
    echo -e "\n[*] Terminating all running background processes and cleaning ports..."
    sudo pkill -9 -f "ryu-manager" 2>/dev/null || true
    sudo pkill -9 -f "sdn_controller.py" 2>/dev/null || true
    sudo pkill -9 -f "server.py" 2>/dev/null || true
    sudo pkill -9 -f "agent.py" 2>/dev/null || true
    sudo pkill -9 -f "backend/app.py" 2>/dev/null || true
    sudo pkill -9 -f "load_balancer/proxy.py" 2>/dev/null || true
    sudo pkill -9 -f "router_monitor.py" 2>/dev/null || true
    sudo pkill -9 -f "socat TCP-LISTEN:5050" 2>/dev/null || true
    
    # Release network ports if held
    sudo fuser -k 5000/udp 2>/dev/null || true
    sudo fuser -k 5050/tcp 2>/dev/null || true
    sudo fuser -k 8080/tcp 2>/dev/null || true
    sudo fuser -k 8000/tcp 2>/dev/null || true
    sudo fuser -k 8001/tcp 2>/dev/null || true
    sudo fuser -k 8002/tcp 2>/dev/null || true
    sudo fuser -k 8003/tcp 2>/dev/null || true
    sudo fuser -k 6653/tcp 2>/dev/null || true

    if command -v mn >/dev/null 2>&1; then
        echo -e "[*] Running Mininet cleanup (sudo mn -c)..."
        sudo mn -c >/dev/null 2>&1 || true
    fi

    echo -e "${GREEN}[OK] Cleaned all ports and terminated background processes.${RESET}\n"
}

# Launch full Mininet Two-Router SDN network
start_mininet_pipeline() {
    check_dependencies
    stop_all

    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   LAUNCHING TWO-ROUTER MININET + SDN CONTROLLER PIPELINE${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    # 1. Start SDN Controller in background
    echo -e "[*] Starting Standalone SDN OpenFlow Controller on port 8080..."
    sudo $PY_BIN sdn_controller.py > /tmp/sdn_controller.log 2>&1 &
    SDN_PID=$!
    sleep 2
    echo -e "    -> SDN Controller running in background (PID: $SDN_PID, Log: /tmp/sdn_controller.log)"

    # Verify controller is listening
    if curl -s -m 2 http://127.0.0.1:8080/health >/dev/null 2>&1; then
        echo -e "    ${GREEN}✔ SDN Controller verified healthy on port 8080${RESET}"
    fi

    # 2. Launch Mininet Topology
    echo -e "\n[*] Launching Mininet Two-Router Multi-Subnet Topology (requires sudo privileges)..."
    echo -e "    -> Subnet 1 (10.0.1.0/24): Clients h1-h3, Monitor h4 (:5050), Switch s1"
    echo -e "    -> Transit Network (10.0.12.0/30): Point-to-Point Router r1 <===> Router r2"
    echo -e "    -> Subnet 2 (10.0.2.0/24): Switch s2, Load Balancer h8 (:8000), Backends h5-h7"
    echo -e "    -> Web Dashboard will be available at: ${BOLD}http://localhost:5050${RESET}\n"

    sudo $PY_BIN topology.py

    # When Mininet exits (Ctrl+D or exit)
    echo -e "\n[*] Mininet session closed. Cleaning up background services..."
    stop_all
}

# Launch standalone local multi-process simulation (when Mininet is not available)
start_local_simulation() {
    check_dependencies
    stop_all

    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   LAUNCHING LOCAL MULTI-PROCESS TWO-ROUTER SIMULATION (NO MININET)${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    echo -e "[*] Starting SDN Controller on port 8080..."
    sudo $PY_BIN sdn_controller.py > /tmp/sdn_controller.log 2>&1 &
    sleep 1

    echo -e "[*] Starting Central Monitoring Server on port 5050..."
    $PY_BIN server.py > /tmp/server.log 2>&1 &
    sleep 2

    # Launch Backends if present
    if [ -f "backend/app.py" ]; then
        echo -e "[*] Launching Backend Microservices (h5: 8001, h6: 8002, h7: 8003)..."
        $PY_BIN backend/app.py --id backend-1 --port 8001 > /tmp/backend_h5.log 2>&1 &
        $PY_BIN backend/app.py --id backend-2 --port 8002 > /tmp/backend_h6.log 2>&1 &
        $PY_BIN backend/app.py --id backend-3 --port 8003 > /tmp/backend_h7.log 2>&1 &
        sleep 1
    fi

    # Launch Load Balancer if present
    if [ -f "load_balancer/proxy.py" ]; then
        echo -e "[*] Launching Load Balancer (h8: 8000)..."
        $PY_BIN load_balancer/proxy.py --host 0.0.0.0 --port 8000 > /tmp/lb_h8.log 2>&1 &
        sleep 1
    fi

    echo -e "[*] Launching Telemetry & C2 Agents (Clients & Backends)..."
    $PY_BIN agent.py --agent-id Node-1 --c2-port 5001 > /tmp/agent_node1.log 2>&1 &
    $PY_BIN agent.py --agent-id Node-2 --c2-port 5002 > /tmp/agent_node2.log 2>&1 &
    $PY_BIN agent.py --agent-id Node-3 --c2-port 5003 > /tmp/agent_node3.log 2>&1 &
    $PY_BIN agent.py --agent-id Backend-1 --c2-port 5005 > /tmp/agent_backend1.log 2>&1 &
    $PY_BIN agent.py --agent-id Backend-2 --c2-port 5006 > /tmp/agent_backend2.log 2>&1 &
    $PY_BIN agent.py --agent-id Backend-3 --c2-port 5007 > /tmp/agent_backend3.log 2>&1 &
    $PY_BIN agent.py --agent-id LoadBalancer --c2-port 5008 > /tmp/agent_lb.log 2>&1 &

    sleep 2
    echo -e "\n${GREEN}[OK] All 7 nodes, Load Balancer, Controller & Central Server are active!${RESET}"
    echo -e "  - Dashboard:   ${BOLD}http://127.0.0.1:5050${RESET}"
    echo -e "  - SDN API:     ${BOLD}http://127.0.0.1:8080${RESET}"
    echo -e "  - Load Balancer: http://127.0.0.1:8000${RESET}"
    echo -e "  - Telemetry:   UDP port 5000\n"

    echo -e "Interactive Options:"
    echo -e "  [T] Run Automated Test Suite (demo_runner.py)"
    echo -e "  [P] Run Performance Benchmarks (performance_eval.py)"
    echo -e "  [K] Stop all background processes"
    echo -e "  [Q] Exit to shell (processes remain active)"

    while true; do
        read -rp "Action [T/P/K/Q]: " action
        case "$action" in
            [tT]) run_tests ;;
            [pP]) run_perf ;;
            [kK]) stop_all; break ;;
            [qQ]) break ;;
            *) echo "Invalid choice." ;;
        esac
    done
}

# Run automated evaluation suite
run_tests() {
    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   RUNNING 9-PHASE AUTOMATED EVALUATION SUITE (demo_runner.py)${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    $PY_BIN demo_runner.py
}

# Run performance benchmark suite
run_perf() {
    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   RUNNING 9-PHASE PERFORMANCE BENCHMARK MATRIX (performance_eval.py)${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    $PY_BIN performance_eval.py
    echo ""
    read -rp "Press Enter to return to menu..."
}

# Interactive Menu
show_menu() {
    clear
    echo -e "========================================================================"
    echo -e "  ${BOLD}REMOTE NETWORK HEALTH MONITOR — OPERATOR NOC LAUNCHER${RESET}"
    echo -e "========================================================================"
    echo ""
    echo -e "  ${GREEN}[1] Launch Full Mininet Two-Router Network (Recommended for Lab)${RESET}"
    echo -e "      -> Starts SDN Controller + Two-Router Mininet Topology + All Nodes"
    echo ""
    echo -e "  [2] Launch Local Simulation (No Mininet / Process Mode)"
    echo -e "      -> Starts Controller + Server + LB + Backends + Agents on Host"
    echo ""
    echo -e "  [3] Run 9-Phase Automated Demo Runner (demo_runner.py)"
    echo -e "  [4] Run Performance Benchmarks (performance_eval.py)"
    echo -e "  [5] Stop All Processes & Clean Mininet Ports"
    echo -e "  [Q] Quit"
    echo ""
    echo -e "========================================================================"
    read -rp "Select an option [1-5, Q] (Default: 1): " choice
    choice="${choice:-1}"

    case "$choice" in
        1) start_mininet_pipeline ;;
        2) start_local_simulation ;;
        3) run_tests ;;
        4) run_perf ;;
        5) stop_all ;;
        [qQ]) exit 0 ;;
        *) echo "Invalid option"; sleep 1; show_menu ;;
    esac
}

# CLI Argument dispatcher
case "$1" in
    mininet|prod|all) start_mininet_pipeline ;;
    local|sim)        start_local_simulation ;;
    test|eval|demo)   run_tests ;;
    perf|bench)       run_perf ;;
    stop|clean|kill)  stop_all ;;
    *)                show_menu ;;
esac
