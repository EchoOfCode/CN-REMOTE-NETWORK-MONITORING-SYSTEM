#!/usr/bin/env python3
"""
Unit Tests for Anomaly Detection Engine
"""

import unittest
from monitoring.anomaly_detector import AnomalyDetector

class TestAnomalyDetector(unittest.TestCase):
    def setUp(self):
        self.detector = AnomalyDetector(
            cpu_crit=85.0,
            cpu_warn=70.0,
            cpu_recovery=75.0,
            upload_crit_mbps=20.0,
            upload_recovery_mbps=5.0,
            consecutive_required=3
        )

    def test_cpu_consecutive_sample_requirement(self):
        # 1st sample: High CPU, but not yet 3 consecutive samples -> No alert
        evts1 = self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 90.0})
        self.assertEqual(len(evts1), 0)

        # 2nd sample
        evts2 = self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 92.0})
        self.assertEqual(len(evts2), 0)

        # 3rd consecutive sample above 85% -> Critical Alert Triggered!
        evts3 = self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 88.0})
        self.assertEqual(len(evts3), 1)
        self.assertEqual(evts3[0]["event_type"], "CPU_UTILIZATION_CRITICAL")
        self.assertEqual(evts3[0]["severity"], "CRITICAL")

    def test_cpu_hysteresis_recovery(self):
        # Trigger critical alert first
        for _ in range(3):
            self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 90.0})

        # Drop to 80% (between recovery 75% and critical 85%) -> Alert remains active (no recovery yet)
        for _ in range(3):
            evts = self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 80.0})
            self.assertEqual(len(evts), 0)

        # Drop below 75% for 3 samples -> RECOVERED event fired!
        self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 60.0})
        self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 65.0})
        evts_rec = self.detector.evaluate_telemetry({"agent_id": "Node-1", "cpu_percent": 70.0})
        self.assertEqual(len(evts_rec), 1)
        self.assertEqual(evts_rec[0]["event_type"], "CPU_UTILIZATION_RECOVERED")
        self.assertEqual(evts_rec[0]["status"], "RECOVERED")

    def test_traffic_flood_detection(self):
        evts = self.detector.evaluate_telemetry({
            "agent_id": "Node-2",
            "ip_address": "10.0.1.12",
            "upload_mbps": 45.0
        })
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0]["event_type"], "NETWORK_TRAFFIC_FLOOD")
        self.assertEqual(evts[0]["action_taken"], "TRIGGER_SDN_MITIGATION")

if __name__ == '__main__':
    unittest.main()

