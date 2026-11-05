#!/usr/bin/env python3
"""
Deterministic Anomaly Detection Engine
Evaluates streaming node, router, and network telemetry.
Applies rolling windows, hysteresis, consecutive-sample persistence, and recovery detection.
"""

import time
from collections import deque
from datetime import datetime

class AnomalyDetector:
    def __init__(self, cpu_crit=85.0, cpu_warn=70.0, cpu_recovery=75.0,
                 upload_crit_mbps=20.0, upload_recovery_mbps=5.0,
                 consecutive_required=3):
        self.cpu_crit = cpu_crit
        self.cpu_warn = cpu_warn
        self.cpu_recovery = cpu_recovery
        self.upload_crit_mbps = upload_crit_mbps
        self.upload_recovery_mbps = upload_recovery_mbps
        self.consecutive_required = consecutive_required

        # Node tracking state: {node_id: {metric: deque(maxlen=5)}}
        self.node_history = {}
        # Active alerts: {alert_key: alert_dict}
        self.active_alerts = {}

    def _get_history(self, node_id, metric):
        if node_id not in self.node_history:
            self.node_history[node_id] = {}
        if metric not in self.node_history[node_id]:
            self.node_history[node_id][metric] = deque(maxlen=10)
        return self.node_history[node_id][metric]

    def evaluate_telemetry(self, telemetry_data):
        """
        Evaluates a telemetry sample. Returns a list of generated event/alert dicts.
        Handles both new anomalies and recovery transitions.
        """
        events = []
        node_id = telemetry_data.get("agent_id", "Unknown")
        cpu = telemetry_data.get("cpu_percent", 0.0)
        upload_mbps = telemetry_data.get("upload_mbps", 0.0)
        active_attack = telemetry_data.get("active_attack", False)
        status = telemetry_data.get("status", "NORMAL")
        ip = telemetry_data.get("ip_address", "127.0.0.1")

        # 1. Evaluate CPU Utilization
        cpu_hist = self._get_history(node_id, "cpu")
        cpu_hist.append(cpu)
        cpu_alert_key = f"{node_id}_cpu_high"

        if len(cpu_hist) >= self.consecutive_required:
            recent_samples = list(cpu_hist)[-self.consecutive_required:]

            # Trigger Critical Alert
            if all(s >= self.cpu_crit for s in recent_samples):
                if cpu_alert_key not in self.active_alerts:
                    alert = {
                        "event_id": f"evt_cpu_{int(time.time()*1000)}",
                        "component": node_id,
                        "event_type": "CPU_UTILIZATION_CRITICAL",
                        "severity": "CRITICAL",
                        "observed_metric": f"{cpu}%",
                        "threshold": f">= {self.cpu_crit}% for {self.consecutive_required} samples",
                        "description": f"CPU on {node_id} sustained at {cpu}% crossing critical threshold",
                        "detection_method": "CONSECUTIVE_SAMPLE_THRESHOLD",
                        "action_taken": "NOTIFY_OPERATOR",
                        "status": "DETECTED",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    self.active_alerts[cpu_alert_key] = alert
                    events.append(alert)

            # Recovery with Hysteresis (must drop below cpu_recovery)
            elif cpu_alert_key in self.active_alerts and all(s < self.cpu_recovery for s in recent_samples):
                prior_alert = self.active_alerts.pop(cpu_alert_key)
                recovery_event = {
                    "event_id": f"rec_{prior_alert['event_id']}",
                    "component": node_id,
                    "event_type": "CPU_UTILIZATION_RECOVERED",
                    "severity": "INFO",
                    "observed_metric": f"{cpu}%",
                    "threshold": f"< {self.cpu_recovery}%",
                    "description": f"CPU on {node_id} normalized to {cpu}%. Anomaly resolved.",
                    "detection_method": "HYSTERESIS_RECOVERY",
                    "action_taken": "AUTO_RESOLVED",
                    "status": "RECOVERED",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                events.append(recovery_event)

        # 2. Evaluate Network Throughput Surge / Traffic Flood
        flood_alert_key = f"{node_id}_traffic_flood"
        if (upload_mbps >= self.upload_crit_mbps or active_attack or status == "ATTACKING"):
            if flood_alert_key not in self.active_alerts:
                alert = {
                    "event_id": f"evt_flood_{int(time.time()*1000)}",
                    "component": node_id,
                    "event_type": "NETWORK_TRAFFIC_FLOOD",
                    "severity": "CRITICAL",
                    "observed_metric": f"{upload_mbps} Mbps",
                    "threshold": f">= {self.upload_crit_mbps} Mbps",
                    "description": f"Abnormal outbound traffic surge from {node_id} ({ip}) at {upload_mbps} Mbps",
                    "detection_method": "RATE_SPIKE_DETECTOR",
                    "action_taken": "TRIGGER_SDN_MITIGATION",
                    "status": "MITIGATING",
                    "target_ip": ip,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self.active_alerts[flood_alert_key] = alert
                events.append(alert)
        elif flood_alert_key in self.active_alerts and upload_mbps < self.upload_recovery_mbps and not active_attack:
            prior_alert = self.active_alerts.pop(flood_alert_key)
            recovery_event = {
                "event_id": f"rec_{prior_alert['event_id']}",
                "component": node_id,
                "event_type": "TRAFFIC_FLOOD_NORMALIZED",
                "severity": "INFO",
                "observed_metric": f"{upload_mbps} Mbps",
                "threshold": f"< {self.upload_recovery_mbps} Mbps",
                "description": f"Traffic from {node_id} normalized to {upload_mbps} Mbps. Data plane restored.",
                "detection_method": "RATE_SPIKE_DETECTOR",
                "action_taken": "SDN_RULE_ELIGIBLE_FOR_REMOVAL",
                "status": "RECOVERED",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            events.append(recovery_event)

        return events

