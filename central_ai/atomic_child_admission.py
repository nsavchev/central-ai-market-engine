"""A11.15.11: atomic metadata-only FIX child registration and budget reservation.

Never executes, authorizes, or deploys a repair. Caller must independently
authorize the parent task; this method only enforces persisted lineage/budget.
"""
import re
import sqlite3
import time
from pathlib import Path

_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class AtomicChildAdmission:
    def __init__(self, db_path, *, window_seconds=900):
        if type(window_seconds) is not int or not 1 <= window_seconds <= 900:
            raise ValueError("INVALID_WINDOW")
        self.db_path = Path(db_path)
        self.window_seconds = window_seconds

    def register_and_reserve(self, task_id, parent_task_id, *,
                             estimated_cost_units, max_cost_units=100):
        """All-or-nothing metadata registration; caller cannot choose root/depth."""
        for value, label in ((task_id, "INVALID_TASK"),
                             (parent_task_id, "INVALID_PARENT")):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(label)
        if task_id == parent_task_id:
            raise ValueError("SELF_PARENT")
        for value, label in ((estimated_cost_units, "INVALID_COST"),
                             (max_cost_units, "INVALID_MAX_COST")):
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError(label)

        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            parent = db.execute(
                "SELECT root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (parent_task_id,)
            ).fetchone()
            if parent is None:
                return {"reserved": False, "reason": "UNKNOWN_PARENT"}
            root, parent_depth = parent
            depth = parent_depth + 1
            if depth > 2:
                return {"reserved": False, "reason": "DEPTH_EXCEEDED"}
            if db.execute(
                "SELECT 1 FROM repair_lineage WHERE task_id=?", (task_id,)
            ).fetchone():
                return {"reserved": False, "reason": "ALREADY_REGISTERED"}
            budget = db.execute(
                """SELECT status, attempts, started_at, reserved_cost_units, reservations
                   FROM repair_budgets WHERE fingerprint=?""", (root,)
            ).fetchone()
            if budget is None:
                return {"reserved": False, "reason": "UNKNOWN_BUDGET"}
            status, attempts, started_at, spent, reservations = budget
            if status != "OPEN" or int(time.time()) - started_at >= self.window_seconds:
                return {"reserved": False, "reason": "BUDGET_CLOSED"}
            if attempts <= reservations:
                return {"reserved": False, "reason": "NO_UNRESERVED_ATTEMPT"}
            if spent + estimated_cost_units > max_cost_units:
                return {"reserved": False, "reason": "COST_EXCEEDED"}

            db.execute(
                """INSERT INTO repair_lineage
                   (task_id,parent_task_id,root_fingerprint,depth)
                   VALUES (?,?,?,?)""",
                (task_id, parent_task_id, root, depth)
            )
            db.execute(
                """INSERT INTO repair_task_reservations
                   (task_id,root_fingerprint,cost_units) VALUES (?,?,?)""",
                (task_id, root, estimated_cost_units)
            )
            updated = db.execute(
                """UPDATE repair_budgets
                   SET reserved_cost_units=reserved_cost_units+?,
                       reservations=reservations+1
                   WHERE fingerprint=? AND status='OPEN'""",
                (estimated_cost_units, root)
            )
            if updated.rowcount != 1:
                raise RuntimeError("BUDGET_UPDATE_FAILED")
            return {"reserved": True, "root_fingerprint": root,
                    "depth": depth, "reserved_cost_units": spent + estimated_cost_units}
