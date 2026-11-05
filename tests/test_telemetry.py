#!/usr/bin/env python3
"""
Unit Tests for Telemetry & Network Metrics Calculation
"""

import time
import unittest
from monitoring.network_metrics import NetworkMetricsCalculator
from monitoring.telemetry import TelemetryPacket

class TestTelemetry(unittest.TestCase):
    def test_network_metrics_rate_calculation(self):
        calc = NetworkMetricsCalculator()
        
        # Initial sample (baseline)
        first = calc.sample(current_bytes_sent=1000000, current_bytes_recv=500000)
        self.assertEqual(first["upload_mbps"], 0.0)
        self.assertEqual(first["download_mbps"], 0.0)

        # Force elapsed time and second sample
        time.sleep(0.1)
        # Send 1,250,000 bytes over ~0.1s -> ~100 Mbps
        second = calc.sample(current_bytes_sent=2250000, current_bytes_recv=600000)
        self.assertGreater(second["upload_mbps"], 0.0)
        self.assertGreater(second["sample_interval"], 0.0)

    def test_counter_reset_handling(self):
        calc = NetworkMetricsCalculator()
        calc.sample(current_bytes_sent=5000000, current_bytes_recv=5000000)
        time.sleep(0.05)
        # Reset: current bytes sent < previous bytes sent
        res = calc.sample(current_bytes_sent=1000, current_bytes_recv=1000)
        # Must not crash and must not produce negative Mbps
        self.assertGreaterEqual(res["upload_mbps"], 0.0)
        self.assertGreaterEqual(res["download_mbps"], 0.0)

    def test_telemetry_packet_roundtrip(self):
        packet = TelemetryPacket(
            agent_id="Node-1",
            ip_address="10.0.1.11",
            c2_port=5001,
            sequence_number=42,
            cpu_percent=15.2,
            memory_percent=45.0,
            processes=110,
            upload_mbps=12.5,
            download_mbps=4.2,
            bytes_sent=1234567,
            bytes_recv=7654321,
            status="HEALTHY"
        )
        raw_bytes = packet.to_bytes()
        reconstructed = TelemetryPacket.from_bytes(raw_bytes)
        
        self.assertEqual(reconstructed.agent_id, "Node-1")
        self.assertEqual(reconstructed.sequence_number, 42)
        self.assertEqual(reconstructed.cpu_percent, 15.2)
        self.assertEqual(reconstructed.upload_mbps, 12.5)
        self.assertEqual(reconstructed.status, "HEALTHY")

if __name__ == '__main__':
    unittest.main()
