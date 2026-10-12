#!/usr/bin/env bash
# ==============================================================================
# Network Health Monitoring & SDN Attack Simulation System Launcher (Linux/WSL)
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

# Check Python 3
if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PY_BIN="python"
else
    echo -e "${RED}[ERROR] Python 3 was not found on your system!${RESET}"
    exit 1
fi

# Ensure required packages exist
check_dependencies() {
    echo -e "[*] Checking Python dependencies (flask, psutil)..."
    if ! $PY_BIN -c "import flask, psutil" >/dev/null 2>&1; then
        echo -e "[*] Installing required packages from requirements.txt..."
        if [ -f "requirements.txt" ]; then
            $PY_BIN -m pip install -r requirements.txt || {
                echo -e "${YELLOW}[WARNING] pip install failed. If in managed environment, use: sudo apt install python3-flask python3-psutil${RESET}"
            }
        else
            $PY_BIN -m pip install flask psutil || true
        fi
    fi
}

# Stop all background components and clean Mininet
stop_all() {
    echo -e "\n[*] Terminating all system background processes..."
    pkill -f "ryu-manager" 2>/dev/null || true
    pkill -f "sdn_controller.py" 2>/dev/null || true
    pkill -f "server.py" 2>/dev/null || true
    pkill -f "agent.py" 2>/dev/null || true
    pkill -f "socat TCP-LISTEN:5050" 2>/dev/null || true

    if command -v mn >/dev/null 2>&1; then
        echo -e "[*] Running Mininet cleanup (sudo mn -c)..."
        sudo mn -c >/dev/null 2>&1 || true
    fi

    echo -e "${GREEN}[OK] All processes stopped and Mininet cleaned.${RESET}\n"
}

# Launch Mininet & Ryu full pipeline
start_mininet_pipeline() {
    check_dependencies
    stop_all

    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   LAUNCHING MININET + RYU OPENFLOW CONTROLLER PIPELINE${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    # 1. Start Ryu Controller
    if command -v ryu-manager >/dev/null 2>&1; then
        echo -e "[*] Starting Ryu OpenFlow Controller on port 6653 (REST API: 8080)..."
        ryu-manager ryu_sdn_controller.py --wsapi-port 8080 > /tmp/ryu_sdn.log 2>&1 &
        RYU_PID=$!
        sleep 2
        echo -e "    -> Ryu Controller running in background (PID: $RYU_PID, Log: /tmp/ryu_sdn.log)"
    else
        echo -e "${YELLOW}[WARNING] 'ryu-manager' not found in PATH! Falling back to standalone controller mock...${RESET}"
        $PY_BIN sdn_controller.py > /tmp/ryu_sdn.log 2>&1 &
        sleep 1
    fi

    # 2. Launch Mininet Topology
    echo -e "[*] Launching Mininet Topology (requires sudo privileges)..."
    echo -e "    -> Central Server will run on Host h4 (10.0.0.4:5050)"
    echo -e "    -> Agents will run on Hosts h1, h2, h3\n"
    sudo $PY_BIN topology.py
}

# Launch standalone local simulation (process mode without Mininet)
start_local_simulation() {
    check_dependencies
    stop_all

    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   LAUNCHING LOCAL MULTI-PROCESS SIMULATION${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    echo -e "[*] Starting SDN Controller on port 8080..."
    $PY_BIN sdn_controller.py > /tmp/sdn_controller.log 2>&1 &
    sleep 1

    echo -e "[*] Starting Central Server on port 5050..."
    $PY_BIN server.py > /tmp/server.log 2>&1 &
    sleep 2

    echo -e "[*] Launching Agents (Node-1, Node-2, Node-3)..."
    $PY_BIN agent.py --agent-id Node-1 --c2-port 5001 > /tmp/agent_node1.log 2>&1 &
    $PY_BIN agent.py --agent-id Node-2 --c2-port 5002 > /tmp/agent_node2.log 2>&1 &
    $PY_BIN agent.py --agent-id Node-3 --c2-port 5003 > /tmp/agent_node3.log 2>&1 &

    sleep 3
    echo -e "\n${GREEN}[OK] Local simulation running!${RESET}"
    echo -e "  - Dashboard:   ${BOLD}http://127.0.0.1:5050${RESET}"
    echo -e "  - SDN API:     ${BOLD}http://127.0.0.1:8080${RESET}"
    echo -e "  - Telemetry:   UDP 5000\n"

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://127.0.0.1:5050" 2>/dev/null || true
    fi

    echo -e "Options:"
    echo -e "  [T] Run Automated Test Suite (demo_runner.py)"
    echo -e "  [K] Stop all background processes"
    echo -e "  [Q] Exit to shell (processes remain active)"

    while true; do
        read -rp "Action [T/K/Q]: " action
        case "$action" in
            [tT]) run_tests ;;
            [kK]) stop_all; break ;;
            [qQ]) break ;;
            *) echo "Invalid choice." ;;
        esac
    done
}

# Run automated evaluation runner
run_tests() {
    echo -e "\n${BOLD}${CYAN}========================================================================${RESET}"
    echo -e "${BOLD}${CYAN}   RUNNING 5-STAGE AUTOMATED EVALUATION SUITE${RESET}"
    echo -e "${BOLD}${CYAN}========================================================================${RESET}\n"

    # Check if a Central Server is already reachable
    local server_running=false
    if curl -s -m 2 http://10.0.0.4:5050/api/metrics >/dev/null 2>&1 || curl -s -m 2 http://127.0.0.1:5050/api/metrics >/dev/null 2>&1; then
        server_running=true
    fi

    local started_temp_cluster=false
    if [ "$server_running" = false ]; then
        echo -e "${YELLOW}[*] No active Central Server detected. Automatically launching test cluster...${RESET}"
        check_dependencies
        $PY_BIN sdn_controller.py > /tmp/sdn_controller.log 2>&1 &
        sleep 1
        $PY_BIN server.py > /tmp/server.log 2>&1 &
        sleep 2
        $PY_BIN agent.py --agent-id Node-1 --c2-port 5001 > /tmp/agent_node1.log 2>&1 &
        $PY_BIN agent.py --agent-id Node-2 --c2-port 5002 > /tmp/agent_node2.log 2>&1 &
        $PY_BIN agent.py --agent-id Node-3 --c2-port 5003 > /tmp/agent_node3.log 2>&1 &
        sleep 3
        started_temp_cluster=true
        echo -e "${GREEN}[*] Test cluster initialized successfully!${RESET}\n"
    fi

    $PY_BIN demo_runner.py

    if [ "$started_temp_cluster" = true ]; then
        echo ""
        read -rp "Keep test cluster running in background? [y/N]: " keep_running
        if [[ ! "$keep_running" =~ ^[yY]$ ]]; then
            stop_all
        else
            echo -e "${GREEN}[OK] Cluster running in background on http://127.0.0.1:5050${RESET}"
        fi
    fi
}

# Interactive CLI Menu
show_menu() {
    clear
    echo -e "========================================================================"
    echo -e "  ${BOLD}NETWORKING COURSE PROJECT: HEALTH MONITORING & SDN SYSTEM${RESET}"
    echo -e "========================================================================"
    echo ""
    echo -e "  [1] Launch Mininet + Ryu SDN Pipeline (sudo python3 topology.py)"
    echo -e "  [2] Start Local Simulation (Controller + Server + 3 Agents + UI)"
    echo -e "  [3] Run Automated Verification Suite (python3 demo_runner.py)"
    echo -e "  [4] Stop All Background Processes & Clean Mininet"
    echo -e "  [Q] Quit"
    echo ""
    echo -e "========================================================================"
    read -rp "Select an option [1-4, Q] (Default: 1): " choice
    choice="${choice:-1}"

    case "$choice" in
        1) start_mininet_pipeline ;;
        2) start_local_simulation ;;
        3) run_tests ;;
        4) stop_all ;;
        [qQ]) exit 0 ;;
        *) echo "Invalid option"; sleep 1; show_menu ;;
    esac
}

# Argument handling
case "$1" in
    mininet|prod) start_mininet_pipeline ;;
    local|sim)   start_local_simulation ;;
    test|eval)   run_tests ;;
    stop|clean)  stop_all ;;
    *)           show_menu ;;
esac
