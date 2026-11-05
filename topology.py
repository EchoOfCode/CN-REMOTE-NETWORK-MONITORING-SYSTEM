#!/usr/bin/env python3
"""
Remote Network Health Monitor — Mininet Multi-Subnet SDN Topology
Industry-Grade Network Operations, Traffic Management & SDN Platform

Topology Layout:
  Subnet 1: 10.0.1.0/24 (Clients, Monitor & Load Balancer)
    - h1 (10.0.1.11, Agent 1, C2: 5001)
    - h2 (10.0.1.12, Agent 2, C2: 5002)
    - h3 (10.0.1.13, Agent 3, C2: 5003)
    - h4 (10.0.1.20, Central Monitor & Web Dashboard, Port 5050)
    - h8 (10.0.1.30, Custom Load Balancer, Ingress Port 8000, C2: 5008)
    - s1 (Client OpenFlow 1.3 Switch)

  Router:
    - r1 (Linux Layer 3 Router: r1-eth0: 10.0.1.1/24, r1-eth1: 10.0.2.1/24, net.ipv4.ip_forward=1)

  Subnet 2: 10.0.2.0/24 (Backend Server Cluster)
    - h5 (10.0.2.11, Backend 1, Port 8001, C2: 5005)
    - h6 (10.0.2.12, Backend 2, Port 8002, C2: 5006)
    - h7 (10.0.2.13, Backend 3, Port 8003, C2: 5007)
    - s2 (Backend OpenFlow 1.3 Switch)

  SDN Controller:
    - c0 (OpenFlow 1.3 Controller on 127.0.0.1:6653 / REST on 8080)

Usage:
  sudo python3 topology.py [--legacy]
"""

import os
import sys
import time
import argparse
import subprocess

try:
    from mininet.net import Mininet
    from mininet.node import Node, OVSSwitch, RemoteController
    from mininet.cli import CLI
    from mininet.log import setLogLevel, info
except ImportError:
    print("Notice: Mininet library not installed in standard Python host environment.")
    print("To run in Mininet: execute inside WSL/Linux as root: 'sudo python3 topology.py'")
    Mininet = None
    Node = object


class LinuxRouter(Node):
    """A Node with IP forwarding enabled, acting as an enterprise Layer 3 Linux Router."""
    def config(self, **params):
        super().config(**params)
        info('*** Enabling IPv4 Packet Forwarding on Router r1 ***\n')
        self.cmd('sysctl -w net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl -w net.ipv4.ip_forward=0')
        super().terminate()


def cleanup_stale_processes():
    """Deterministic cleanup of background agents, servers, and controllers."""
    print("[INIT] Cleaning up stale background processes & ports...")
    cleanup_cmds = [
        "pkill -f agent.py",
        "pkill -f server.py",
        "pkill -f 'backend.app'",
        "pkill -f 'load_balancer.proxy'",
        "pkill -f router_monitor.py",
        "pkill -f 'socat TCP-LISTEN:5050'",
        "fuser -k 5000/udp 2>/dev/null || true",
        "fuser -k 5050/tcp 2>/dev/null || true",
        "fuser -k 8000/tcp 2>/dev/null || true",
        "fuser -k 8001/tcp 2>/dev/null || true",
        "fuser -k 8002/tcp 2>/dev/null || true",
        "fuser -k 8003/tcp 2>/dev/null || true",
        "fuser -k 8080/tcp 2>/dev/null || true"
    ]
    for cmd in cleanup_cmds:
        os.system(f"{cmd} >/dev/null 2>&1")


def build_expanded_topology():
    if not Mininet:
        print("[ERROR] Mininet library is required to build this topology.")
        sys.exit(1)

    setLogLevel('info')
    cleanup_stale_processes()

    info('\n=======================================================================\n')
    info(' 🚀 CREATING ENTERPRISE DUAL-SUBNET ROUTED SDN TOPOLOGY (Mininet)\n')
    info('=======================================================================\n\n')

    net = Mininet(controller=RemoteController, switch=OVSSwitch)

    # 1. Controller
    info('*** 1. Adding Remote SDN Controller (c0) on 127.0.0.1:6653 ***\n')
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    # 2. Switches
    info('*** 2. Adding OpenFlow 1.3 Switches: s1 (Clients) & s2 (Backends) ***\n')
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')

    # 3. Layer 3 Linux Router
    info('*** 3. Adding Linux Layer 3 Router (r1) ***\n')
    r1 = net.addHost('r1', cls=LinuxRouter, ip='10.0.1.1/24')

    # 4. Client Subnet Hosts (10.0.1.0/24)
    info('*** 4. Adding Client Subnet Hosts (h1-h4, h8) on Subnet 10.0.1.0/24 ***\n')
    h1 = net.addHost('h1', ip='10.0.1.11/24', defaultRoute='via 10.0.1.1', mac='00:00:00:00:01:11')
    h2 = net.addHost('h2', ip='10.0.1.12/24', defaultRoute='via 10.0.1.1', mac='00:00:00:00:01:12')
    h3 = net.addHost('h3', ip='10.0.1.13/24', defaultRoute='via 10.0.1.1', mac='00:00:00:00:01:13')
    h4 = net.addHost('h4', ip='10.0.1.20/24', defaultRoute='via 10.0.1.1', mac='00:00:00:00:01:20')
    h8 = net.addHost('h8', ip='10.0.1.30/24', defaultRoute='via 10.0.1.1', mac='00:00:00:00:01:30')

    # 5. Backend Subnet Hosts (10.0.2.0/24)
    info('*** 5. Adding Backend Subnet Hosts (h5-h7) on Subnet 10.0.2.0/24 ***\n')
    h5 = net.addHost('h5', ip='10.0.2.11/24', defaultRoute='via 10.0.2.1', mac='00:00:00:00:02:11')
    h6 = net.addHost('h6', ip='10.0.2.12/24', defaultRoute='via 10.0.2.1', mac='00:00:00:00:02:12')
    h7 = net.addHost('h7', ip='10.0.2.13/24', defaultRoute='via 10.0.2.1', mac='00:00:00:00:02:13')

    # 6. Links & Interconnects
    info('*** 6. Linking Hosts to Switches & Router to Switches ***\n')
    # Connect Subnet 1 to Switch s1
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)
    net.addLink(h8, s1)

    # Connect Router r1 interfaces
    # r1-eth0: 10.0.1.1/24 -> s1
    net.addLink(r1, s1, intfName1='r1-eth0', params1={'ip': '10.0.1.1/24'})
    # r1-eth1: 10.0.2.1/24 -> s2
    net.addLink(r1, s2, intfName1='r1-eth1', params1={'ip': '10.0.2.1/24'})

    # Connect Subnet 2 to Switch s2
    net.addLink(h5, s2)
    net.addLink(h6, s2)
    net.addLink(h7, s2)

    # 7. Build and Start Network
    info('*** 7. Starting Network & Programming Switches ***\n')
    net.build()
    c0.start()
    s1.start([c0])
    s2.start([c0])

    # Configure router second interface explicitly inside r1 namespace
    r1.cmd('ip addr add 10.0.2.1/24 dev r1-eth1 2>/dev/null || true')
    r1.cmd('ip link set r1-eth0 up')
    r1.cmd('ip link set r1-eth1 up')
    r1.cmd('sysctl -w net.ipv4.ip_forward=1')

    # Ensure baseline forwarding on both switches (enables standard L2 flow)
    os.system('ovs-ofctl add-flow s1 "priority=0,actions=NORMAL" 2>/dev/null || ovs-ofctl -O OpenFlow13 add-flow s1 "priority=0,actions=NORMAL" 2>/dev/null || true')
    os.system('ovs-ofctl add-flow s2 "priority=0,actions=NORMAL" 2>/dev/null || ovs-ofctl -O OpenFlow13 add-flow s2 "priority=0,actions=NORMAL" 2>/dev/null || true')
    os.system('ovs-vsctl set-fail-mode s1 standalone 2>/dev/null || true')
    os.system('ovs-vsctl set-fail-mode s2 standalone 2>/dev/null || true')

    # Host root namespace bridge configuration
    # Allows host OS to route directly into 10.0.1.0/24 and 10.0.2.0/24
    os.system('ip addr add 10.0.1.254/24 dev s1 2>/dev/null || true')
    os.system('ip link set s1 up 2>/dev/null || true')
    os.system('ip route add 10.0.2.0/24 via 10.0.1.1 dev s1 2>/dev/null || true')

    # Optional port forwarding from host 5050 to Mininet h4 10.0.1.20:5050
    os.system('which socat >/dev/null 2>&1 && (socat TCP-LISTEN:5050,fork,reuseaddr TCP:10.0.1.20:5050 &)')

    time.sleep(1)

    # 8. Automated Connectivity Verification
    info('\n*** 8. Verifying Multi-Subnet Routing via Router r1 ***\n')
    ping_res = net.ping([h1, h5])
    if ping_res == 0.0:
        info('    ✔ [PASS] Cross-subnet routing verified (Client h1 <-> Backend h5 via r1: 0% loss)\n')
    else:
        info(f'    ⚠ [NOTE] Cross-subnet ping had {ping_res}% loss during initial ARP; retrying...\n')
        net.ping([h1, h5])

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 9. Launch Services in Respective Namespaces
    info('\n*** 9. Launching Distributed Services ***\n')

    # A. Central Monitoring Server on h4 (10.0.1.20)
    server_script = os.path.join(base_dir, 'server.py')
    if os.path.exists(server_script):
        info('    -> Launching Central Ingestion & C2 Server on h4 (10.0.1.20:5050)...\n')
        h4.cmd(f'SDN_CONTROLLER_URL=http://10.0.1.254:8080 python3 {server_script} > /tmp/server_h4.log 2>&1 &')
        time.sleep(1.5)

    # B. Telemetry Agents on Client Nodes (h1, h2, h3)
    agent_script = os.path.join(base_dir, 'agent.py')
    if os.path.exists(agent_script):
        info('    -> Launching Telemetry Agents on Client Nodes (h1, h2, h3)...\n')
        h1.cmd(f'python3 {agent_script} --agent-id Node-1 --server-ip 10.0.1.20 --c2-port 5001 > /tmp/agent_h1.log 2>&1 &')
        h2.cmd(f'python3 {agent_script} --agent-id Node-2 --server-ip 10.0.1.20 --c2-port 5002 > /tmp/agent_h2.log 2>&1 &')
        h3.cmd(f'python3 {agent_script} --agent-id Node-3 --server-ip 10.0.1.20 --c2-port 5003 > /tmp/agent_h3.log 2>&1 &')

    # C. Backend Microservices on h5, h6, h7 (Subnet 2: 10.0.2.0/24)
    backend_script = os.path.join(base_dir, 'backend', 'app.py')
    if os.path.exists(backend_script):
        info('    -> Launching Backend Services on h5, h6, h7 (Ports 8001, 8002, 8003)...\n')
        h5.cmd(f'python3 {backend_script} --id backend-1 --port 8001 > /tmp/backend_h5.log 2>&1 &')
        h6.cmd(f'python3 {backend_script} --id backend-2 --port 8002 > /tmp/backend_h6.log 2>&1 &')
        h7.cmd(f'python3 {backend_script} --id backend-3 --port 8003 > /tmp/backend_h7.log 2>&1 &')
        # Also launch telemetry agents on backend hosts
        h5.cmd(f'python3 {agent_script} --agent-id Backend-1 --server-ip 10.0.1.20 --c2-port 5005 > /tmp/agent_h5.log 2>&1 &')
        h6.cmd(f'python3 {agent_script} --agent-id Backend-2 --server-ip 10.0.1.20 --c2-port 5006 > /tmp/agent_h6.log 2>&1 &')
        h7.cmd(f'python3 {agent_script} --agent-id Backend-3 --server-ip 10.0.1.20 --c2-port 5007 > /tmp/agent_h7.log 2>&1 &')

    # D. Custom HTTP Load Balancer on h8 (10.0.1.30:8000)
    lb_script = os.path.join(base_dir, 'load_balancer', 'proxy.py')
    if os.path.exists(lb_script):
        info('    -> Launching Custom Load Balancer on h8 (10.0.1.30:8000)...\n')
        h8.cmd(f'python3 {lb_script} --host 0.0.0.0 --port 8000 > /tmp/lb_h8.log 2>&1 &')
        h8.cmd(f'python3 {agent_script} --agent-id LoadBalancer --server-ip 10.0.1.20 --c2-port 5008 > /tmp/agent_h8.log 2>&1 &')

    # E. Router Monitor on r1
    router_script = os.path.join(base_dir, 'monitoring', 'router_monitor.py')
    if os.path.exists(router_script):
        info('    -> Launching Router Health Monitor on r1 (10.0.1.1)...\n')
        r1.cmd(f'python3 {router_script} --router-id r1 --server-ip 10.0.1.20 > /tmp/router_r1.log 2>&1 &')

    print("\n" + "=" * 80)
    print(" 🌐 ENTERPRISE ROUTED SDN TOPOLOGY IS LIVE & READY")
    print("=" * 80)
    print("  Subnet 1 (10.0.1.0/24 - Clients & Monitoring):")
    print("    - h1: 10.0.1.11 (Client 1, C2: 5001)")
    print("    - h2: 10.0.1.12 (Client 2, C2: 5002)")
    print("    - h3: 10.0.1.13 (Client 3, C2: 5003)")
    print("    - h4: 10.0.1.20 (Central C2 Server & Dashboard, Port 5050)")
    print("    - h8: 10.0.1.30 (Custom Load Balancer, Ingress Port 8000)")
    print("\n  Layer 3 Router (r1):")
    print("    - r1-eth0: 10.0.1.1 (Gateway for Subnet 1)")
    print("    - r1-eth1: 10.0.2.1 (Gateway for Subnet 2)")
    print("\n  Subnet 2 (10.0.2.0/24 - Backend Microservices):")
    print("    - h5: 10.0.2.11 (Backend 1, HTTP: 8001, C2: 5005)")
    print("    - h6: 10.0.2.12 (Backend 2, HTTP: 8002, C2: 5006)")
    print("    - h7: 10.0.2.13 (Backend 3, HTTP: 8003, C2: 5007)")
    print("\n  Web Dashboard Access:")
    print("    - Direct from host browser:  http://10.0.1.20:5050 (via s1 bridge)")
    print("    - Or if socat active on host: http://localhost:5050")
    print("    - Load Balancer URL:         http://10.0.1.30:8000")
    print("\n  Testing Commands:")
    print("    - Cross-subnet ping:         mininet> h1 ping -c 3 h5")
    print("    - Query Load Balancer:       mininet> h1 curl -s http://10.0.1.30:8000")
    print("    - Check Switch Flows:        sudo ovs-ofctl -O OpenFlow13 dump-flows s1")
    print("=" * 80 + "\n")

    info('*** Entering Mininet CLI ***\n')
    CLI(net)

    info('\n*** Stopping Network & Performing Clean Teardown ***\n')
    cleanup_stale_processes()
    net.stop()
    info('*** Teardown complete. ***\n')


def build_legacy_topology():
    """Fallback single-subnet 4-host topology for legacy compatibility."""
    setLogLevel('info')
    cleanup_stale_processes()
    info('*** Creating Legacy Flat Mininet Topology (10.0.0.0/24) ***\n')

    net = Mininet(controller=RemoteController, switch=OVSSwitch)
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)

    net.build()
    c0.start()
    s1.start([c0])

    os.system('ovs-ofctl add-flow s1 "priority=0,actions=NORMAL" 2>/dev/null || true')
    os.system('ip addr add 10.0.0.254/24 dev s1 2>/dev/null || true')
    os.system('ip link set s1 up 2>/dev/null || true')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    h4.cmd(f'SDN_CONTROLLER_URL=http://10.0.0.254:8080 python3 {os.path.join(base_dir, "server.py")} > /tmp/server_h4.log 2>&1 &')
    h1.cmd(f'python3 {os.path.join(base_dir, "agent.py")} --agent-id Node-1 --server-ip 10.0.0.4 --c2-port 5001 > /tmp/agent_h1.log 2>&1 &')
    h2.cmd(f'python3 {os.path.join(base_dir, "agent.py")} --agent-id Node-2 --server-ip 10.0.0.4 --c2-port 5002 > /tmp/agent_h2.log 2>&1 &')
    h3.cmd(f'python3 {os.path.join(base_dir, "agent.py")} --agent-id Node-3 --server-ip 10.0.0.4 --c2-port 5003 > /tmp/agent_h3.log 2>&1 &')

    CLI(net)
    cleanup_stale_processes()
    net.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="SDN Multi-Subnet Mininet Topology")
    parser.add_argument('--legacy', action='store_true', help="Run legacy flat 4-host topology (10.0.0.0/24)")
    args = parser.parse_args()

    if args.legacy:
        build_legacy_topology()
    else:
        build_expanded_topology()
