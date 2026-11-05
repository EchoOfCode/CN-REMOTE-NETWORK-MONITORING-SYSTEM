#!/usr/bin/env python3
"""
Network Metrics & Real-Time Throughput Rate Calculator
Computes true instantaneous bandwidth (Mbps), packet rates, and drop/error counters.
Handles counter resets, negative differences, and zero time intervals.
"""

import time
import psutil

class NetworkMetricsCalculator:
    def __init__(self):
        self.prev_time = None
        self.prev_bytes_sent = None
        self.prev_bytes_recv = None
        self.prev_packets_sent = None
        self.prev_packets_recv = None
        self.prev_dropin = None
        self.prev_dropout = None
        self.prev_errin = None
        self.prev_errout = None

    def sample(self, current_bytes_sent=None, current_bytes_recv=None):
        """
        Samples network counters and returns throughput in Mbps and raw metrics.
        If current_bytes_* are passed, uses them; otherwise queries psutil.
        """
        now = time.time()

        if current_bytes_sent is None or current_bytes_recv is None:
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            packets_sent = net_io.packets_sent
            packets_recv = net_io.packets_recv
            dropin = net_io.dropin
            dropout = net_io.dropout
            errin = net_io.errin
            errout = net_io.errout
        else:
            bytes_sent = current_bytes_sent
            bytes_recv = current_bytes_recv
            try:
                net_io = psutil.net_io_counters()
                packets_sent = net_io.packets_sent
                packets_recv = net_io.packets_recv
                dropin = net_io.dropin
                dropout = net_io.dropout
                errin = net_io.errin
                errout = net_io.errout
            except Exception:
                packets_sent = packets_recv = dropin = dropout = errin = errout = 0

        # Initial sample baseline
        if self.prev_time is None:
            self.prev_time = now
            self.prev_bytes_sent = bytes_sent
            self.prev_bytes_recv = bytes_recv
            self.prev_packets_sent = packets_sent
            self.prev_packets_recv = packets_recv
            self.prev_dropin = dropin
            self.prev_dropout = dropout
            self.prev_errin = errin
            self.prev_errout = errout
            return {
                "upload_mbps": 0.0,
                "download_mbps": 0.0,
                "upload_pps": 0.0,
                "download_pps": 0.0,
                "bytes_sent": bytes_sent,
                "bytes_recv": bytes_recv,
                "packets_sent": packets_sent,
                "packets_recv": packets_recv,
                "packet_drops": 0,
                "packet_errors": 0,
                "sample_interval": 0.0
            }

        elapsed = now - self.prev_time

        # Guard against zero or negative elapsed time
        if elapsed <= 0.001:
            elapsed = 0.001

        # Calculate byte deltas, handling counter resets or negative wraps
        delta_sent = bytes_sent - self.prev_bytes_sent
        if delta_sent < 0:
            delta_sent = bytes_sent  # Reset detected

        delta_recv = bytes_recv - self.prev_bytes_recv
        if delta_recv < 0:
            delta_recv = bytes_recv

        delta_pkts_sent = packets_sent - self.prev_packets_sent
        if delta_pkts_sent < 0:
            delta_pkts_sent = packets_sent

        delta_pkts_recv = packets_recv - self.prev_packets_recv
        if delta_pkts_recv < 0:
            delta_pkts_recv = packets_recv

        # True instantaneous throughput: (bytes * 8) / seconds / 1,000,000
        upload_mbps = (delta_sent * 8.0) / elapsed / 1_000_000.0
        download_mbps = (delta_recv * 8.0) / elapsed / 1_000_000.0
        upload_pps = delta_pkts_sent / elapsed
        download_pps = delta_pkts_recv / elapsed

        packet_drops = max(0, (dropin - self.prev_dropin) + (dropout - self.prev_dropout))
        packet_errors = max(0, (errin - self.prev_errin) + (errout - self.prev_errout))

        # Update historical state
        self.prev_time = now
        self.prev_bytes_sent = bytes_sent
        self.prev_bytes_recv = bytes_recv
        self.prev_packets_sent = packets_sent
        self.prev_packets_recv = packets_recv
        self.prev_dropin = dropin
        self.prev_dropout = dropout
        self.prev_errin = errin
        self.prev_errout = errout

        return {
            "upload_mbps": round(upload_mbps, 3),
            "download_mbps": round(download_mbps, 3),
            "upload_pps": round(upload_pps, 1),
            "download_pps": round(download_pps, 1),
            "bytes_sent": bytes_sent,
            "bytes_recv": bytes_recv,
            "packets_sent": packets_sent,
            "packets_recv": packets_recv,
            "packet_drops": packet_drops,
            "packet_errors": packet_errors,
            "sample_interval": round(elapsed, 3)
        }


def get_interface_statistics():
    """Returns per-interface network status and counters."""
    stats = {}
    try:
        io_counters = psutil.net_io_counters(pernic=True)
        if_addrs = psutil.net_if_addrs()
        if_stats = psutil.net_if_stats()

        for iface, addrs in if_addrs.items():
            if iface.startswith("lo"):
                continue
            ip = None
            for addr in addrs:
                if addr.family.name == "AF_INET":
                    ip = addr.address
                    break
            
            io = io_counters.get(iface)
            is_up = if_stats.get(iface).isup if iface in if_stats else True

            stats[iface] = {
                "name": iface,
                "ip": ip,
                "state": "UP" if is_up else "DOWN",
                "bytes_sent": io.bytes_sent if io else 0,
                "bytes_recv": io.bytes_recv if io else 0,
                "packets_sent": io.packets_sent if io else 0,
                "packets_recv": io.packets_recv if io else 0,
                "dropin": io.dropin if io else 0,
                "dropout": io.dropout if io else 0,
                "errin": io.errin if io else 0,
                "errout": io.errout if io else 0
            }
    except Exception as e:
        stats["error"] = str(e)
    return stats
