"""Persistent, bounded FIX incident deduplication for Central AI.

Only metadata is stored. This module never executes code, deploys or approves tasks.
"""
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def fingerprint(component, error_code, operation):
    """Stable fingerprint from safe, low-cardinality diagnostic identifiers."""
    for value in (component, error_code, operation):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_.-]{0,79}", value
        ):
            raise ValueError("INVALID_FINGERPRINT_FIELD")
    canonical = "\x1f".join((component, error_code, operation))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FixIncidentRegistry:
    """One incident per fingerprint; persistent across process restarts."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if self.db_path.is_symlink() or not self.db_path.parent.is_dir():
            raise ValueError("INVALID_DATABASE")
        with sqlite3.connect(self.db_path, timeout=10) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS fix_incidents (
                    fingerprint TEXT PRIMARY KEY,
                    source_task_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK(status IN ('OPEN','VERIFIED','ESCALATED','CANCELLED')),
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    occurrences INTEGER NOT NULL DEFAULT 1
                        CHECK(occurrences >= 1),
                    approved INTEGER NOT NULL DEFAULT 0 CHECK(approved=0),
                    deployment_allowed INTEGER NOT NULL DEFAULT 0
                        CHECK(deployment_allowed=0)
                )
            """)

    def register(self, source_task_id, component, error_code, operation):
        if not isinstance(source_task_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,128}", source_task_id
        ):
            raise ValueError("INVALID_SOURCE_TASK")
        key = fingerprint(component, error_code, operation)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as con:
            con.execute("BEGIN IMMEDIATE")
            cursor = con.execute("""
                INSERT OR IGNORE INTO fix_incidents
                    (fingerprint, source_task_id, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
            """, (key, source_task_id, now, now))
            created = cursor.rowcount == 1
            if not created:
                con.execute("""
                    UPDATE fix_incidents
                    SET occurrences=occurrences+1, last_seen_at=?
                    WHERE fingerprint=?
                """, (now, key))
            row = con.execute("""
                SELECT fingerprint, source_task_id, status, occurrences,
                       approved, deployment_allowed
                FROM fix_incidents WHERE fingerprint=?
            """, (key,)).fetchone()
        return {
            "fingerprint": row[0], "source_task_id": row[1],
            "status": row[2], "occurrences": row[3],
            "approved": bool(row[4]), "deployment_allowed": bool(row[5]),
            "created": created,
        }

    def transition(self, key, status):
        if status not in ("VERIFIED", "ESCALATED", "CANCELLED"):
            raise ValueError("INVALID_INCIDENT_TRANSITION")
        with sqlite3.connect(self.db_path, timeout=10) as con:
            cursor = con.execute("""
                UPDATE fix_incidents SET status=?
                WHERE fingerprint=? AND status='OPEN'
                  AND approved=0 AND deployment_allowed=0
            """, (status, key))
            return cursor.rowcount == 1
