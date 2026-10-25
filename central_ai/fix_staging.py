"""A11.15.12: lease-gated, non-executable FIX staging.

Atomic metadata admission only. Never inserts an executable task_queue row,
never runs a patch, and never grants approval or deployment rights.
"""
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class FixStaging:
    def __init__(self, db_path, *, window_seconds=900):
        if type(window_seconds) is not int or not 1 <= window_seconds <= 900:
            raise ValueError("INVALID_WINDOW")
        self.db_path = Path(db_path)
        self.window_seconds = window_seconds
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS fix_staging (
                child_task_id TEXT PRIMARY KEY,
                parent_task_id TEXT NOT NULL,
                root_fingerprint TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'STAGED' CHECK(state='STAGED'),
                approved INTEGER NOT NULL DEFAULT 0 CHECK(approved=0),
                deployment_allowed INTEGER NOT NULL DEFAULT 0 CHECK(deployment_allowed=0),
                created_at TEXT NOT NULL
            )""")

    def stage(self, child_task_id, parent_task_id, *, agent, lease_token,
              estimated_cost_units, max_cost_units=100):
        for value, label in ((child_task_id, "INVALID_CHILD"),
                             (parent_task_id, "INVALID_PARENT")):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(label)
        if child_task_id == parent_task_id:
            raise ValueError("SELF_PARENT")
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError("INVALID_AGENT")
        if not isinstance(lease_token, str) or not lease_token:
            raise ValueError("INVALID_TOKEN")
        for value, label in ((estimated_cost_units, "INVALID_COST"),
                             (max_cost_units, "INVALID_MAX_COST")):
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError(label)

        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            owned = db.execute("""SELECT 1 FROM task_queue
                WHERE task_id=? AND owner=? AND lease_token=?
                AND status='leased' AND lease_until > ?
                AND approved=0 AND deployment_allowed=0
                AND retry_exhausted=0 AND attempt_count < 3""",
                (parent_task_id, agent, lease_token, now)).fetchone()
            if owned is None:
                return {"staged": False, "reason": "PARENT_LEASE_INVALID"}
            parent = db.execute(
                "SELECT root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (parent_task_id,)).fetchone()
            if parent is None:
                return {"staged": False, "reason": "UNKNOWN_LINEAGE"}
            root, parent_depth = parent
            depth = parent_depth + 1
            if depth > 2:
                return {"staged": False, "reason": "DEPTH_EXCEEDED"}
            if db.execute("SELECT 1 FROM repair_lineage WHERE task_id=?",
                          (child_task_id,)).fetchone() or db.execute(
                "SELECT 1 FROM task_queue WHERE task_id=?", (child_task_id,)
            ).fetchone():
                return {"staged": False, "reason": "CHILD_ALREADY_EXISTS"}
            incident = db.execute("""SELECT source_task_id,status,approved,deployment_allowed
                FROM fix_incidents WHERE fingerprint=?""", (root,)).fetchone()
            root_task = db.execute("""SELECT task_id FROM repair_lineage
                WHERE root_fingerprint=? AND parent_task_id IS NULL AND depth=0""",
                (root,)).fetchall()
            if (incident is None or incident[1:] != ("OPEN", 0, 0)
                    or len(root_task) != 1 or incident[0] != root_task[0][0]):
                return {"staged": False, "reason": "INCIDENT_NOT_AUTHORIZED"}
            budget = db.execute("""SELECT status,attempts,started_at,
                reserved_cost_units,reservations
                FROM repair_budgets WHERE fingerprint=?""", (root,)).fetchone()
            if budget is None:
                return {"staged": False, "reason": "UNKNOWN_BUDGET"}
            status, attempts, started_at, spent, reservations = budget
            if status != "OPEN" or int(time.time()) - started_at >= self.window_seconds:
                return {"staged": False, "reason": "BUDGET_CLOSED"}
            if attempts <= reservations:
                return {"staged": False, "reason": "NO_UNRESERVED_ATTEMPT"}
            if spent + estimated_cost_units > max_cost_units:
                return {"staged": False, "reason": "COST_EXCEEDED"}
            db.execute("""INSERT INTO repair_lineage
                (task_id,parent_task_id,root_fingerprint,depth)
                VALUES (?,?,?,?)""", (child_task_id, parent_task_id, root, depth))
            db.execute("""INSERT INTO repair_task_reservations
                (task_id,root_fingerprint,cost_units) VALUES (?,?,?)""",
                (child_task_id, root, estimated_cost_units))
            db.execute("""UPDATE repair_budgets
                SET reserved_cost_units=reserved_cost_units+?,
                    reservations=reservations+1
                WHERE fingerprint=? AND status='OPEN'""",
                (estimated_cost_units, root))
            db.execute("""INSERT INTO fix_staging
                (child_task_id,parent_task_id,root_fingerprint,created_at)
                VALUES (?,?,?,?)""", (child_task_id, parent_task_id, root, now))
            db.execute("""INSERT INTO task_queue_audit
                (task_id,event,agent,timestamp) VALUES (?,?,?,?)""",
                (parent_task_id, "fix_child_staged", agent, now))
            return {"staged": True, "child_task_id": child_task_id,
                    "root_fingerprint": root, "depth": depth,
                    "executable": False}
