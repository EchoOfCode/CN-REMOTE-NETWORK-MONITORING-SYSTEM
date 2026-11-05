#!/usr/bin/env python3
"""
Central Operation Manager & Audit Lifecycle Engine
Remote Network Health Monitor — Operator-Controlled NOC

Enforces strict operation lifecycle:
  REQUESTED -> VALIDATING -> EXECUTING -> VERIFYING -> SUCCESS / FAILED

Every privileged control operation receives a unique operation ID, validated parameters,
atomic execution, post-execution verification against real operating system / network state,
and persistent SQLite auditing.
"""

import os
import sys
import time
import uuid
import threading
from datetime import datetime

# Import database module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db
from services.event_manager import event_manager

class OperationManager:
    VALID_STAGES = ["REQUESTED", "VALIDATING", "EXECUTING", "VERIFYING", "SUCCESS", "FAILED"]

    def __init__(self, max_history=100):
        self.operations = {}
        self.history = []
        self.max_history = max_history
        self.lock = threading.Lock()

    def create_operation(self, component, action, parameters=None, operator="OPERATOR"):
        """Initiates a new privileged operation with unique ID and initial lifecycle state."""
        op_id = f"op_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        op = {
            "op_id": op_id,
            "component": component,
            "action": action,
            "parameters": parameters or {},
            "operator": operator,
            "stage": "REQUESTED",
            "status": "RUNNING",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "verification_result": None,
            "message": f"Operation '{action}' requested on '{component}'.",
            "error": None
        }

        with self.lock:
            self.operations[op_id] = op
            self.history.insert(0, op_id)
            if len(self.history) > self.max_history:
                old_id = self.history.pop()
                self.operations.pop(old_id, None)

        event_manager.publish_event({
            "event_id": f"evt_{op_id}",
            "component": component,
            "event_type": "OPERATION_REQUESTED",
            "severity": "NORMAL",
            "description": f"Operator requested action: {action} on {component}",
            "status": "REQUESTED"
        })

        return op_id

    def update_stage(self, op_id, stage, message=None, details=None):
        """Transitions an operation to a new lifecycle stage."""
        if stage not in self.VALID_STAGES:
            raise ValueError(f"Invalid stage '{stage}'. Must be one of {self.VALID_STAGES}")

        with self.lock:
            op = self.operations.get(op_id)
            if not op:
                return None
            op["stage"] = stage
            op["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if message:
                op["message"] = message
            if details:
                op.setdefault("details", {}).update(details)
            return dict(op)

    def complete_operation(self, op_id, success=True, verification_result=None, error=None):
        """Concludes an operation with final verified status and audit logging."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            op = self.operations.get(op_id)
            if not op:
                return None

            op["stage"] = "SUCCESS" if success else "FAILED"
            op["status"] = "SUCCESS" if success else "FAILED"
            op["completed_at"] = now
            op["updated_at"] = now
            op["verification_result"] = verification_result or ("Verified OK" if success else "Verification Failed")
            op["error"] = error
            if error:
                op["message"] = f"Failed: {error}"
            elif not op.get("message") or op.get("stage") == "SUCCESS":
                op["message"] = f"Operation '{op['action']}' on '{op['component']}' completed and verified successfully."

            # Persist to SQLite audit logs
            db.log_audit(
                action=f"{op['component']}:{op['action']}",
                target=str(op.get("parameters")),
                result="SUCCESS" if success else "FAILED",
                actor=op.get("operator", "OPERATOR"),
                details=str(verification_result or error or "")
            )

            # Publish event
            event_manager.publish_event({
                "event_id": f"evt_{op_id}_done",
                "component": op["component"],
                "event_type": "OPERATION_COMPLETED",
                "severity": "NORMAL" if success else "CRITICAL",
                "description": op["message"],
                "status": "COMPLETED" if success else "FAILED"
            })

            return dict(op)

    def get_operation(self, op_id):
        with self.lock:
            op = self.operations.get(op_id)
            return dict(op) if op else None

    def get_operations(self, limit=50):
        with self.lock:
            result = []
            for op_id in self.history[:limit]:
                op = self.operations.get(op_id)
                if op:
                    result.append(dict(op))
            return result

# Global singleton
operation_manager = OperationManager()

