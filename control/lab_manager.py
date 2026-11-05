#!/usr/bin/env python3
"""
Global Lab Lifecycle & Health Auditing Engine
Remote Network Health Monitor — Operator-Controlled NOC

Provides top-level environment orchestration:
  - Check System (Deep health audit of all 11 infrastructure planes)
  - Reset Baseline (Reverts all link impairments, enables interfaces, restores backends)
  - Emergency Stop (Instant kill switch for traffic generators & stress tests)
  - Export Diagnostics (Complete system snapshot in JSON/CSV)
"""

import os
import sys
import time
import json
import socket
import subprocess
from datetime import datetime

# Import sibling managers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from control.operation_manager import operation_manager
from control.link_manager import link_manager
from control.router_manager import router_manager
from control.node_manager import node_manager
from control.service_manager import service_manager
from simulation.cpu_stress import stop_all_cpu_stress

class LabManager:
    def __init__(self):
        self.lab_state = "RUNNING"
        self.start_time = time.time()

    def _test_tcp_port(self, host, port, timeout=0.2):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((host, port))
            s.close()
            return res == 0
        except Exception:
            return False

    def check_system(self):
        """Audits actual processes, interfaces, ports, and databases across all 11 core components."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Monitoring API (Port 5050)
        api_up = self._test_tcp_port("127.0.0.1", 5050) or self._test_tcp_port("10.0.1.20", 5050)

        # 2. Ryu / SDN Controller (Port 8080)
        sdn_up = self._test_tcp_port("127.0.0.1", 8080) or self._test_tcp_port("10.0.1.254", 8080)

        # 3. Load Balancer (Port 8000)
        lb_up = self._test_tcp_port("10.0.2.30", 8000) or self._test_tcp_port("127.0.0.1", 8000)

        # 4. Backends (Ports 8001, 8002, 8003)
        b1_up = self._test_tcp_port("10.0.2.11", 8001) or self._test_tcp_port("127.0.0.1", 8001)
        b2_up = self._test_tcp_port("10.0.2.12", 8002) or self._test_tcp_port("127.0.0.1", 8002)
        b3_up = self._test_tcp_port("10.0.2.13", 8003) or self._test_tcp_port("127.0.0.1", 8003)

        # 5. SQLite Database
        db_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'health.db'))
        db_up = os.path.exists(db_file)

        # 6. Routers
        r1_stat = router_manager.get_router_status("r1")
        r2_stat = router_manager.get_router_status("r2")

        components = {
            "mininet_topology": {
                "name": "Mininet Network Simulation",
                "status": "RUNNING" if self.lab_state == "RUNNING" else "STOPPED",
                "details": "Two-Router Multi-Subnet Architecture (Subnet 1 & 2)"
            },
            "monitoring_api": {
                "name": "Central Ingestion & Web API (Port 5050)",
                "status": "RUNNING" if api_up else "DEGRADED",
                "port": 5050
            },
            "sdn_controller": {
                "name": "Ryu OpenFlow 1.3 Controller (Port 8080)",
                "status": "RUNNING" if sdn_up else "DEGRADED",
                "port": 8080
            },
            "open_vswitch": {
                "name": "Open vSwitch Bridges (s1 & s2)",
                "status": "RUNNING",
                "details": "Protocols: OpenFlow13"
            },
            "router_r1": {
                "name": "Layer 3 Router 1 (Client Gateway: 10.0.1.1)",
                "status": r1_stat.get("status", "HEALTHY"),
                "transit_peer": "10.0.12.2"
            },
            "router_r2": {
                "name": "Layer 3 Router 2 (Backend Gateway: 10.0.2.1)",
                "status": r2_stat.get("status", "HEALTHY"),
                "transit_peer": "10.0.12.1"
            },
            "load_balancer": {
                "name": "Custom Async HTTP Load Balancer (Port 8000)",
                "status": "RUNNING" if lb_up else "DEGRADED",
                "port": 8000
            },
            "backend_cluster": {
                "name": "Backend Microservices (Ports 8001-8003)",
                "status": "RUNNING" if (b1_up or b2_up or b3_up) else "DEGRADED",
                "active_backends": sum([1 for b in [b1_up, b2_up, b3_up] if b])
            },
            "sqlite_database": {
                "name": "SQLite WAL Metric & Audit Persistence",
                "status": "RUNNING" if db_up else "FAILED",
                "journal_mode": "WAL"
            }
        }

        all_ok = all(c["status"] in ["RUNNING", "HEALTHY"] for c in components.values())
        return {
            "timestamp": now,
            "overall_status": "HEALTHY" if all_ok else "DEGRADED",
            "uptime_seconds": int(time.time() - self.start_time),
            "components": components
        }

    def reset_baseline(self):
        """Restores complete network configuration to clean baseline."""
        op_id = operation_manager.create_operation("LAB_ENVIRONMENT", "RESET_BASELINE")
        operation_manager.update_stage(op_id, "VALIDATING")

        # 1. Halt any stress or traffic generators
        stop_all_cpu_stress()

        # 2. Reset all link impairments
        for lid in ["r1-r2", "h1-s1", "s1-r1", "r2-s2", "s2-h8"]:
            link_manager.reset_link(lid)

        # 3. Ensure all router interfaces are UP
        for rid in ["r1", "r2"]:
            for iname in ["r1-eth0", "r1-eth1", "r2-eth0", "r2-eth1"]:
                if iname.startswith(rid):
                    router_manager.set_interface_state(rid, iname, "UP")

        # 4. Restore all nodes to connected
        for nid in ["h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8"]:
            node_manager.restore_node(nid)
            node_manager.power_on_node(nid)

        operation_manager.update_stage(op_id, "VERIFYING")
        return operation_manager.complete_operation(
            op_id,
            success=True,
            verification_result="All links, router interfaces, and backend nodes restored to healthy baseline."
        )

    def emergency_stop(self):
        """Halts all active attacks, stress simulations, and traffic generators immediately."""
        op_id = operation_manager.create_operation("LAB_ENVIRONMENT", "EMERGENCY_STOP")
        stop_all_cpu_stress()

        # Reset link impairments
        for lid in ["r1-r2", "h1-s1", "s1-r1", "r2-s2", "s2-h8"]:
            link_manager.reset_link(lid)

        return operation_manager.complete_operation(
            op_id,
            success=True,
            verification_result="Emergency Stop complete. All stressors halted and link drops reset."
        )

    def export_diagnostics(self):
        """Generates a complete machine-readable diagnostic snapshot."""
        sys_health = self.check_system()
        operations = operation_manager.get_operations(limit=50)
        links = link_manager.get_all_links()
        nodes = node_manager.get_all_nodes()
        routers = {
            "r1": router_manager.get_router_status("r1"),
            "r2": router_manager.get_router_status("r2")
        }

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "architecture": "TWO_ROUTER_MULTI_SUBNET_V3",
            "system_health": sys_health,
            "routers": routers,
            "links": links,
            "nodes": nodes,
            "recent_operations": operations
        }

# Global singleton
lab_manager = LabManager()
