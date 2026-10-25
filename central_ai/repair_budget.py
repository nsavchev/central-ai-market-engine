"""A11.15.9 durable, fail-closed repair attempt budgets.

Records attempt admission only. Never performs a repair or deploys.
"""
import re
import sqlite3
import time
from pathlib import Path


class RepairBudget:
    def __init__(self, db_path, max_attempts=3, window_seconds=900):
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 3:
            raise ValueError("INVALID_MAX_ATTEMPTS")
        if not isinstance(window_seconds, int) or isinstance(window_seconds, bool) or not 1 <= window_seconds <= 900:
            raise ValueError("INVALID_WINDOW")
        self.db_path = Path(db_path)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        with sqlite3.connect(self.db_path, timeout=10) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS repair_budgets (
                    fingerprint TEXT PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    started_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK(status IN ('OPEN','VERIFIED','ESCALATED','CANCELLED')),
                    last_failure_code TEXT,
                    approved INTEGER NOT NULL DEFAULT 0 CHECK(approved=0),
                    deployment_allowed INTEGER NOT NULL DEFAULT 0
                        CHECK(deployment_allowed=0)
                )
            """)

    def admit(self, fingerprint, failure_code=None):
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("INVALID_FINGERPRINT")
        if failure_code is not None and (
            not isinstance(failure_code, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", failure_code)
        ):
            raise ValueError("INVALID_FAILURE_CODE")
        now = int(time.time())
        with sqlite3.connect(self.db_path, timeout=10) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("""
                INSERT OR IGNORE INTO repair_budgets
                    (fingerprint, started_at) VALUES (?, ?)
            """, (fingerprint, now))
            row = con.execute("""
                SELECT attempts, started_at, status, last_failure_code
                FROM repair_budgets WHERE fingerprint=?
            """, (fingerprint,)).fetchone()
            attempts, started, status, previous_code = row
            if status != "OPEN":
                return {"admitted": False, "status": status, "attempts": attempts}
            if now - started >= self.window_seconds or attempts >= self.max_attempts:
                con.execute("""
                    UPDATE repair_budgets SET status='ESCALATED'
                    WHERE fingerprint=? AND status='OPEN'
                """, (fingerprint,))
                return {"admitted": False, "status": "ESCALATED", "attempts": attempts}
            # The same error on consecutive repair attempts indicates no progress.
            if attempts > 0 and failure_code is not None and failure_code == previous_code:
                con.execute("""
                    UPDATE repair_budgets SET status='ESCALATED'
                    WHERE fingerprint=? AND status='OPEN'
                """, (fingerprint,))
                return {"admitted": False, "status": "ESCALATED", "attempts": attempts}
            con.execute("""
                UPDATE repair_budgets SET attempts=attempts+1,
                    last_failure_code=? WHERE fingerprint=? AND status='OPEN'
            """, (failure_code, fingerprint))
            return {"admitted": True, "status": "OPEN", "attempts": attempts + 1}

    def close(self, fingerprint, status):
        if status not in ("VERIFIED", "ESCALATED", "CANCELLED"):
            raise ValueError("INVALID_STATUS")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("INVALID_FINGERPRINT")
        with sqlite3.connect(self.db_path, timeout=10) as con:
            cursor = con.execute("""
                UPDATE repair_budgets SET status=?
                WHERE fingerprint=? AND status='OPEN'
            """, (status, fingerprint))
            return cursor.rowcount == 1
