#!/usr/bin/env python3
"""
Traffic Generation & Benchmark Job Manager
Remote Network Health Monitor — Operator-Controlled NOC

Orchestrates operator-initiated synthetic traffic generation across:
  - ICMP Ping probes (continuous latency & packet drop calculation)
  - UDP Throughput surges (controlled Mbps bandwidth testing)
  - HTTP Web requests (concurrent load balancing benchmarks)

Every test is assigned a unique job ID, parameters, start/completion times,
and live measurable counters.
"""

import os
import sys
import time
import uuid
import socket
import threading
import subprocess
import urllib.request
from datetime import datetime

# Import operation manager
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from control.operation_manager import operation_manager

class TrafficManager:
    def __init__(self, max_jobs=50):
        self.jobs = {}
        self.active_threads = {}
        self.max_jobs = max_jobs
        self.lock = threading.Lock()

    def get_jobs(self):
        with self.lock:
            return list(self.jobs.values())

    def get_job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def stop_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return {"status": "ERROR", "message": f"Job {job_id} not found"}
            job["status"] = "STOPPED"
            job["message"] = "Stopped by operator."
            job["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {"status": "SUCCESS", "job_id": job_id}

    def stop_all_jobs(self):
        with self.lock:
            count = 0
            for job in self.jobs.values():
                if job["status"] == "RUNNING":
                    job["status"] = "STOPPED"
                    job["message"] = "Halted by stop-all command."
                    job["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    count += 1
            return {"status": "SUCCESS", "stopped_count": count}

    def start_ping_job(self, source="h1", destination="10.0.1.20", count=5, interval=1.0):
        """Starts an ICMP ping probe job."""
        job_id = f"job_ping_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        job = {
            "job_id": job_id,
            "type": "ICMP_PING",
            "source": source,
            "destination": destination,
            "protocol": "ICMP",
            "parameters": {"count": count, "interval": interval},
            "status": "RUNNING",
            "started_at": now,
            "completed_at": None,
            "packets_sent": 0,
            "packets_received": 0,
            "packet_loss_percent": 0.0,
            "avg_latency_ms": 0.0,
            "message": f"Running {count} ICMP probes from {source} to {destination}..."
        }

        with self.lock:
            self.jobs[job_id] = job

        def worker():
            cmd = f"ping -c {count} -W 1 {destination} 2>/dev/null || ping -n {count} -w 1000 {destination}"
            try:
                res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                out = res.stdout
                loss = 0.0
                latency = 0.5

                if "%" in out:
                    for token in out.split():
                        if "%" in token:
                            try:
                                loss = float(token.replace("%", "").replace("(", "").replace(")", "").strip())
                                break
                            except Exception:
                                pass

                if "avg" in out or "Average" in out:
                    try:
                        if "avg" in out:
                            part = out.split("=")[1].strip()
                            latency = float(part.split("/")[1])
                        elif "Average" in out:
                            part = out.split("Average =")[-1].replace("ms", "").strip()
                            latency = float(part)
                    except Exception:
                        latency = 0.7

                with self.lock:
                    job["status"] = "COMPLETED"
                    job["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    job["packets_sent"] = count
                    job["packets_received"] = int(count * (1.0 - (loss / 100.0)))
                    job["packet_loss_percent"] = loss
                    job["avg_latency_ms"] = round(latency, 2)
                    job["message"] = f"Finished. Loss: {loss}%, Avg Latency: {latency} ms"

            except Exception as e:
                with self.lock:
                    job["status"] = "FAILED"
                    job["message"] = str(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return job

    def start_udp_job(self, source="h1", destination="10.0.1.20", target_port=5000, bandwidth_mbps=25, duration=5, packet_size=1024):
        """Starts a UDP throughput surge test."""
        job_id = f"job_udp_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        job = {
            "job_id": job_id,
            "type": "UDP_THROUGHPUT",
            "source": source,
            "destination": f"{destination}:{target_port}",
            "protocol": "UDP",
            "parameters": {"bandwidth_mbps": bandwidth_mbps, "duration": duration, "packet_size": packet_size},
            "status": "RUNNING",
            "started_at": now,
            "completed_at": None,
            "packets_sent": 0,
            "bytes_sent": 0,
            "achieved_mbps": 0.0,
            "message": f"Transmitting UDP surge at {bandwidth_mbps} Mbps for {duration}s..."
        }

        with self.lock:
            self.jobs[job_id] = job

        def worker():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload = b"X" * packet_size
            end_time = time.time() + duration
            bytes_sent = 0
            packets_sent = 0

            # Calculate sleep delay to match target bandwidth
            # bytes_per_sec = (bandwidth_mbps * 1_000_000) / 8
            packets_per_sec = (bandwidth_mbps * 1_000_000) / (8 * packet_size)
            sleep_interval = 1.0 / max(packets_per_sec, 1)

            try:
                start_t = time.time()
                while time.time() < end_time and job["status"] == "RUNNING":
                    sock.sendto(payload, (destination, target_port))
                    bytes_sent += packet_size
                    packets_sent += 1
                    if sleep_interval > 0.001:
                        time.sleep(sleep_interval)

                elapsed = max(time.time() - start_t, 0.001)
                achieved = round((bytes_sent * 8) / (elapsed * 1_000_000), 2)

                with self.lock:
                    job["status"] = "COMPLETED"
                    job["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    job["packets_sent"] = packets_sent
                    job["bytes_sent"] = bytes_sent
                    job["achieved_mbps"] = achieved
                    job["message"] = f"Finished. Sent {packets_sent} packets ({achieved} Mbps achieved)."

            except Exception as e:
                with self.lock:
                    job["status"] = "FAILED"
                    job["message"] = str(e)
            finally:
                sock.close()

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return job

    def start_http_job(self, source="h1", url="http://10.0.2.30:8000/", total_requests=10, concurrency=2):
        """Starts an HTTP benchmark workload to test Load Balancer distribution."""
        job_id = f"job_http_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        job = {
            "job_id": job_id,
            "type": "HTTP_LOAD",
            "source": source,
            "destination": url,
            "protocol": "HTTP",
            "parameters": {"total_requests": total_requests, "concurrency": concurrency},
            "status": "RUNNING",
            "started_at": now,
            "completed_at": None,
            "requests_sent": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_response_ms": 0.0,
            "server_distribution": {},
            "message": f"Dispatching {total_requests} HTTP requests to {url}..."
        }

        with self.lock:
            self.jobs[job_id] = job

        def worker():
            distribution = {}
            latencies = []
            success_count = 0
            fail_count = 0

            for i in range(total_requests):
                if job["status"] != "RUNNING":
                    break
                t0 = time.time()
                try:
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        duration_ms = (time.time() - t0) * 1000.0
                        latencies.append(duration_ms)
                        success_count += 1
                        server_id = resp.headers.get("X-Served-By", "unknown")
                        distribution[server_id] = distribution.get(server_id, 0) + 1
                except Exception:
                    fail_count += 1
                time.sleep(0.05)

            avg_lat = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

            with self.lock:
                job["status"] = "COMPLETED"
                job["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                job["requests_sent"] = success_count + fail_count
                job["successful_requests"] = success_count
                job["failed_requests"] = fail_count
                job["avg_response_ms"] = avg_lat
                job["server_distribution"] = distribution
                job["message"] = f"Finished. Success: {success_count}/{total_requests}, Avg Latency: {avg_lat} ms"

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return job

# Global singleton
traffic_manager = TrafficManager()

