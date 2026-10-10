#!/usr/bin/env python3
"""
Mininet Custom SDN Topology Script
Network Health Monitoring System with SDN Integration

Topology Layout:
     [ Host h1: 10.0.0.1 (Agent 1) ] ---\
     [ Host h2: 10.0.0.2 (Agent 2) ] ----+--- [ OpenFlow Switch s1 ] === [ Ryu SDN Controller c0: 6653 ]
     [ Host h3: 10.0.0.3 (Agent 3) ] ---/             |
     [ Host h4: 10.0.0.4 (Server/Target) ] -----------/

Usage:
    sudo python3 topology.py
"""

import os
import sys
import time

try:
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController
    from mininet.cli import CLI
    from mininet.log import setLogLevel, info
except ImportError:
    print("Notice: Mininet library not installed on standard Python host.")
    print("To run in Mininet environment: execute inside WSL/Linux with root privileges: 'sudo python3 topology.py'")
    Mininet = None


def build_sdn_topology():
    if not Mininet:
        sys.exit(1)

    setLogLevel('info')
    info('*** Creating Mininet Network Topology with SDN Integration ***\n')

    net = Mininet(controller=RemoteController, switch=OVSSwitch)

    info('*** Adding Remote SDN Controller (c0) on 127.0.0.1:6653 ***\n')
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info('*** Adding OpenFlow Switch (s1) with OpenFlow 1.3 ***\n')
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    info('*** Adding Hosts & Assigning IP Addresses ***\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    info('*** Linking Hosts to OpenFlow Switch s1 ***\n')
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)

    info('*** Starting Network & Connecting to Ryu Controller ***\n')
    net.build()
    c0.start()
    s1.start([c0])

    # Allow controller handshake & switch flow table setup
    time.sleep(2)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(base_dir, 'server.py')
    agent_script = os.path.join(base_dir, 'agent.py')

    # 1. Launch Central Monitoring & C2 Server inside Host h4's namespace
    info('*** Launching Central Server & Flask Dashboard on Host h4 (10.0.0.4:5050) ***\n')
    if os.path.exists(server_script):
        h4.cmd(f'python3 {server_script} > /tmp/server_h4.log 2>&1 &')
        info('    -> Server launched on h4 (Logs: /tmp/server_h4.log)\n')
        time.sleep(2)  # Give Flask and UDP listener time to bind to 0.0.0.0
    else:
        info(f'    -> Warning: server.py not found at {server_script}\n')

    # 2. Launch Health Monitoring Agents inside Hosts h1, h2, h3
    info('*** Launching Health Monitoring Agents on Hosts h1, h2, h3 ***\n')
    if os.path.exists(agent_script):
        h1.cmd(f'python3 {agent_script} --agent-id Node-1 --server-ip 10.0.0.4 --c2-port 5001 > /tmp/agent_h1.log 2>&1 &')
        h2.cmd(f'python3 {agent_script} --agent-id Node-2 --server-ip 10.0.0.4 --c2-port 5002 > /tmp/agent_h2.log 2>&1 &')
        h3.cmd(f'python3 {agent_script} --agent-id Node-3 --server-ip 10.0.0.4 --c2-port 5003 > /tmp/agent_h3.log 2>&1 &')
        info('    -> Agent Node-1 running on h1 (UDP Telemetry -> 10.0.0.4:5000, C2: 5001)\n')
        info('    -> Agent Node-2 running on h2 (UDP Telemetry -> 10.0.0.4:5000, C2: 5002)\n')
        info('    -> Agent Node-3 running on h3 (UDP Telemetry -> 10.0.0.4:5000, C2: 5003)\n')
    else:
        info(f'    -> Warning: agent.py not found at {agent_script}\n')

    # 3. Configure Host-side Dashboard Accessibility
    # Assigning an IP to switch interface s1 in root namespace allows the host OS to route directly to 10.0.0.4
    os.system('ip addr add 10.0.0.254/24 dev s1 2>/dev/null || true')
    os.system('ip link set s1 up 2>/dev/null || true')

    # Optional port-forwarding helper using socat if available on host
    os.system('which socat >/dev/null 2>&1 && (socat TCP-LISTEN:5050,fork,reuseaddr TCP:10.0.0.4:5050 &)')

    print("\n" + "=" * 75)
    print(" 🌐 MININET SDN TOPOLOGY IS LIVE & READY FOR EVALUATION")
    print("=" * 75)
    print("  Host Nodes:")
    print("    - h1: 10.0.0.1 (Agent Node-1, C2 Port 5001)")
    print("    - h2: 10.0.0.2 (Agent Node-2, C2 Port 5002)")
    print("    - h3: 10.0.0.3 (Agent Node-3, C2 Port 5003)")
    print("    - h4: 10.0.0.4 (Central C2 Server & Flask Dashboard, Port 5050)")
    print("\n  Web Dashboard Access:")
    print("    - Direct from host browser:  http://10.0.0.4:5050  (via s1 bridge interface)")
    print("    - Or if socat active on host: http://localhost:5050")
    print("    - Mininet Xterm browser:     mininet> h4 xterm &")
    print("    - SSH port forwarding:       ssh -L 5050:10.0.0.4:5050 <user>@<host>")
    print("\n  Validation Commands:")
    print("    - Check switch flow table:   sudo ovs-ofctl -O OpenFlow13 dump-flows s1")
    print("    - Run E2E evaluation test:   python3 demo_runner.py")
    print("=" * 75 + "\n")

    info('*** Network Ready. Entering Mininet CLI ***\n')
    CLI(net)

    info('*** Stopping Network & Cleaning Up Background Processes ***\n')
    h1.cmd('pkill -f agent.py')
    h2.cmd('pkill -f agent.py')
    h3.cmd('pkill -f agent.py')
    h4.cmd('pkill -f server.py')
    os.system('pkill -f "socat TCP-LISTEN:5050"')
    net.stop()


if __name__ == '__main__':
    build_sdn_topology()
