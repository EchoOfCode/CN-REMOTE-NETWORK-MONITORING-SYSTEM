#!/usr/bin/env python3
"""
Event Management & Lifecycle Service
Maintains the centralized system event registry and state transitions:
  DETECTED -> ACKNOWLEDGED -> MITIGATING -> RECOVERED
Persists all events and audit logs into SQLite.
"""

import os
import sys
import time
import threading
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db

class EventManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_events = {}

    def publish_event(self, event_dict):
        """Publishes and persists an event."""
        with self.lock:
            eid = event_dict.get("event_id") or f"evt_{int(time.time()*1000)}"
            event_dict["event_id"] = eid
            self.active_events[eid] = event_dict

            # Persist to DB
            db.log_system_event(
                event_type=event_dict.get("event_type", "GENERIC_EVENT"),
                component=event_dict.get("component", "SYSTEM"),
                severity=event_dict.get("severity", "INFO"),
                description=event_dict.get("description", ""),
                observed_metric=event_dict.get("observed_metric"),
                threshold=event_dict.get("threshold"),
                action_taken=event_dict.get("action_taken"),
                status=event_dict.get("status", "DETECTED")
            )
            return event_dict

    def acknowledge_event(self, event_id, actor="OPERATOR"):
        with self.lock:
            if event_id in self.active_events:
                self.active_events[event_id]["status"] = "ACKNOWLEDGED"
                self.active_events[event_id]["acknowledged_by"] = actor
                self.active_events[event_id]["acknowledged_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.log_audit("ACKNOWLEDGE_EVENT", event_id, "SUCCESS", actor)
                return True
            return False

    def mark_mitigating(self, event_id, mitigation_action):
        with self.lock:
            if event_id in self.active_events:
                self.active_events[event_id]["status"] = "MITIGATING"
                self.active_events[event_id]["action_taken"] = mitigation_action
                return True
            return False

    def resolve_event(self, event_id, recovery_description=None):
        with self.lock:
            if event_id in self.active_events:
                evt = self.active_events.pop(event_id)
                evt["status"] = "RECOVERED"
                evt["recovery_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if recovery_description:
                    evt["description"] += f" [Recovery: {recovery_description}]"
                return evt
            return None

    def get_recent_events(self, limit=30):
        return db.get_system_events(limit=limit)

    def get_audit_trail(self, limit=30):
        return db.get_audit_logs(limit=limit)

# Global singleton
event_manager = EventManager()

