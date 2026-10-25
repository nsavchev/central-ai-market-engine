"""A11.15.10 persistent parent-child lineage ledger (metadata only).

Every child belongs to exactly one canonical root fingerprint. The ledger does
not authorize, create, execute or deploy repair tasks.
"""
import re
import sqlite3
from pathlib import Path

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class RepairLineage:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS repair_lineage (
                    task_id TEXT PRIMARY KEY,
                    parent_task_id TEXT,
                    root_fingerprint TEXT NOT NULL,
                    depth INTEGER NOT NULL CHECK(depth BETWEEN 0 AND 2),
                    FOREIGN KEY(parent_task_id) REFERENCES repair_lineage(task_id)
                )
            """)

    def register_root(self, task_id, fingerprint):
        self._validate(task_id, fingerprint)
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT parent_task_id,root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (task_id,)
            ).fetchone()
            if row is not None:
                if row != (None, fingerprint, 0):
                    raise ValueError("LINEAGE_CONFLICT")
                return False
            db.execute(
                "INSERT INTO repair_lineage(task_id,parent_task_id,root_fingerprint,depth) VALUES(?,NULL,?,0)",
                (task_id, fingerprint)
            )
            return True

    def register_child(self, task_id, parent_task_id, expected_root):
        self._validate(task_id, expected_root)
        if not isinstance(parent_task_id, str) or not _ID.fullmatch(parent_task_id):
            raise ValueError("INVALID_PARENT")
        if task_id == parent_task_id:
            raise ValueError("SELF_PARENT")
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            parent = db.execute(
                "SELECT root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (parent_task_id,)
            ).fetchone()
            if parent is None:
                raise ValueError("UNKNOWN_PARENT")
            root, depth = parent
            if root != expected_root:
                raise ValueError("ROOT_MISMATCH")
            if depth >= 2:
                raise ValueError("DEPTH_EXCEEDED")
            child = db.execute(
                "SELECT parent_task_id,root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (task_id,)
            ).fetchone()
            intended = (parent_task_id, root, depth + 1)
            if child is not None:
                if child != intended:
                    raise ValueError("LINEAGE_CONFLICT")
                return {"created": False, "root_fingerprint": root, "depth": depth + 1}
            db.execute(
                "INSERT INTO repair_lineage(task_id,parent_task_id,root_fingerprint,depth) VALUES(?,?,?,?)",
                (task_id, parent_task_id, root, depth + 1)
            )
            return {"created": True, "root_fingerprint": root, "depth": depth + 1}

    def lookup(self, task_id):
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise ValueError("INVALID_TASK")
        with sqlite3.connect(self.db_path, timeout=10) as db:
            row = db.execute(
                "SELECT parent_task_id,root_fingerprint,depth FROM repair_lineage WHERE task_id=?",
                (task_id,)
            ).fetchone()
        if row is None:
            return None
        return {"parent_task_id": row[0], "root_fingerprint": row[1], "depth": row[2]}

    @staticmethod
    def _validate(task_id, fingerprint):
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise ValueError("INVALID_TASK")
        if not isinstance(fingerprint, str) or not _HASH.fullmatch(fingerprint):
            raise ValueError("INVALID_FINGERPRINT")
