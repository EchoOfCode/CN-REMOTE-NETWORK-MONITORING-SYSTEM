#!/usr/bin/env python3
"""
Controlled CPU Stress Simulation Engine
Simulates genuine CPU load surges for anomaly detection and alert verification.
Supports stress-ng (if available) or a safe, bounded multiprocessing Python worker.
Enforces strict duration limits (safety cap: 30s) and automatic cleanup.
"""

import os
import sys
import time
import psutil
import argparse
import subprocess
import multiprocessing
from threading import Thread

# Global active worker tracking
_active_workers = []
_stop_event = multiprocessing.Event()

def _cpu_burner(stop_event, intensity=0.9):
    """Burns CPU cycles in chunks with a duty cycle matching intensity."""
    chunk = 0.05
    work_time = chunk * intensity
    sleep_time = chunk * (1.0 - intensity)
    while not stop_event.is_set():
        start = time.time()
        while (time.time() - start) < work_time:
            _ = 123456.789 * 987654.321
        if sleep_time > 0:
            time.sleep(sleep_time)


def run_cpu_stress(duration=10, intensity=0.95, cores=None):
    """
    Executes controlled CPU stress on the local host/namespace.
    Safety limits: duration capped at 30 seconds.
    """
    duration = min(max(2, duration), 30)
    num_cores = cores or min(multiprocessing.cpu_count(), 4)

    print(f"[SIMULATION] 🔥 Starting CPU Stress for {duration}s on {num_cores} cores (Intensity: {int(intensity*100)}%)...")

    # Try stress-ng first if installed
    res = subprocess.run("which stress-ng", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        cmd = f"stress-ng --cpu {num_cores} --cpu-load {int(intensity*100)} --timeout {duration}s"
        p = subprocess.Popen(cmd, shell=True)
        try:
            p.wait(timeout=duration + 2)
            print("[SIMULATION] ✅ stress-ng completed.")
            return {"status": "SUCCESS", "engine": "stress-ng", "duration": duration, "cores": num_cores}
        except Exception:
            p.kill()

    # Bounded Python multiprocessing engine
    _stop_event.clear()
    processes = []
    for _ in range(num_cores):
        p = multiprocessing.Process(target=_cpu_burner, args=(_stop_event, intensity), daemon=True)
        p.start()
        processes.append(p)

    time.sleep(duration)
    _stop_event.set()

    for p in processes:
        p.join(timeout=1.0)
        if p.is_alive():
            p.terminate()

    print("[SIMULATION] 🛑 CPU Stress cycle ended. Load normalizing.")
    return {"status": "SUCCESS", "engine": "python_multiprocessing", "duration": duration, "cores": num_cores}


def stop_all_cpu_stress():
    _stop_event.set()
    subprocess.run("pkill -f stress-ng", shell=True)
    print("[SIMULATION] 🛑 Emergency STOP sent to all CPU stress tasks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CPU Stress Simulator")
    parser.add_argument("--duration", type=int, default=10, help="Duration in seconds (max 30)")
    parser.add_argument("--intensity", type=float, default=0.95, help="Intensity (0.1 to 1.0)")
    parser.add_argument("--cores", type=int, default=None, help="Number of CPU cores")
    args = parser.parse_args()

    run_cpu_stress(duration=args.duration, intensity=args.intensity, cores=args.cores)
