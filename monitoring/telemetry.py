#!/usr/bin/env python3
"""
Telemetry Packet Schema & Validation
Encapsulates structured telemetry datagrams transmitted over UDP.
"""

import json
from datetime import datetime

class TelemetryPacket:
    def __init__(self, agent_id, ip_address, c2_port=5001, sequence_number=0,
                 cpu_percent=0.0, memory_percent=0.0, processes=0,
                 upload_mbps=0.0, download_mbps=0.0, bytes_sent=0, bytes_recv=0,
                 packets_sent=0, packets_recv=0, packet_drops=0, packet_errors=0,
                 status="HEALTHY", active_attack=False, interface_id=None):
        self.agent_id = agent_id
        self.ip_address = ip_address
        self.c2_port = c2_port
        self.sequence_number = sequence_number
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cpu_percent = round(cpu_percent, 1)
        self.memory_percent = round(memory_percent, 1)
        self.processes = processes
        self.upload_mbps = round(upload_mbps, 3)
        self.download_mbps = round(download_mbps, 3)
        self.bytes_sent = bytes_sent
        self.bytes_recv = bytes_recv
        self.packets_sent = packets_sent
        self.packets_recv = packets_recv
        self.packet_drops = packet_drops
        self.packet_errors = packet_errors
        self.status = status
        self.active_attack = active_attack
        self.interface_id = interface_id

    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "ip_address": self.ip_address,
            "c2_port": self.c2_port,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "processes": self.processes,
            "upload_mbps": self.upload_mbps,
            "download_mbps": self.download_mbps,
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "packets_sent": self.packets_sent,
            "packets_recv": self.packets_recv,
            "packet_drops": self.packet_drops,
            "packet_errors": self.packet_errors,
            "status": self.status,
            "active_attack": self.active_attack,
            "interface_id": self.interface_id
        }

    def to_bytes(self):
        return json.dumps(self.to_dict()).encode('utf-8')

    @classmethod
    def from_dict(cls, data):
        return cls(
            agent_id=data.get("agent_id", "Unknown"),
            ip_address=data.get("ip_address", "127.0.0.1"),
            c2_port=data.get("c2_port", 5001),
            sequence_number=data.get("sequence_number", 0),
            cpu_percent=data.get("cpu_percent", 0.0),
            memory_percent=data.get("memory_percent", 0.0),
            processes=data.get("processes", 0),
            upload_mbps=data.get("upload_mbps", 0.0),
            download_mbps=data.get("download_mbps", 0.0),
            bytes_sent=data.get("bytes_sent", 0),
            bytes_recv=data.get("bytes_recv", 0),
            packets_sent=data.get("packets_sent", 0),
            packets_recv=data.get("packets_recv", 0),
            packet_drops=data.get("packet_drops", 0),
            packet_errors=data.get("packet_errors", 0),
            status=data.get("status", "HEALTHY"),
            active_attack=data.get("active_attack", False),
            interface_id=data.get("interface_id")
        )

    @classmethod
    def from_bytes(cls, raw_bytes):
        data = json.loads(raw_bytes.decode('utf-8'))
        return cls.from_dict(data)
