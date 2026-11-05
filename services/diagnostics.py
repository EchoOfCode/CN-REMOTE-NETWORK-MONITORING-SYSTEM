#!/usr/bin/env python3
"""
System Diagnostics & Forensic Report Generator
Remote Network Health Monitor — Operator-Controlled NOC
"""

import os
import sys
import json
import csv
import io
from datetime import datetime

# Import siblings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from control.lab_manager import lab_manager
from control.operation_manager import operation_manager
from monitoring.packet_monitor import packet_monitor
from monitoring.packet_loss import packet_loss_detector
from services.event_manager import event_manager

class DiagnosticsService:
    def get_full_diagnostics(self):
        """Gathers full comprehensive system snapshot."""
        return {
            "report_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "architecture": "TWO_ROUTER_MULTI_SUBNET_V3",
            "system_health": lab_manager.check_system(),
            "packet_loss_diagnosis": packet_loss_detector.segments,
            "packet_summary": packet_monitor.get_summary(),
            "operations_audit": operation_manager.get_operations(limit=25),
            "events_stream": event_manager.get_recent_events(limit=25)
        }

    def export_csv(self):
        """Exports key diagnostic and performance events as CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Component", "Event / Operation", "Status", "Details"])

        # Write operations
        for op in operation_manager.get_operations(limit=50):
            writer.writerow([
                op.get("created_at"),
                op.get("component"),
                op.get("action"),
                op.get("status"),
                op.get("message")
            ])

        # Write events
        for evt in event_manager.get_recent_events(limit=50):
            writer.writerow([
                evt.get("timestamp"),
                evt.get("component"),
                evt.get("event_type"),
                evt.get("status"),
                evt.get("description")
            ])

        return output.getvalue()

# Global singleton
diagnostics_service = DiagnosticsService()
