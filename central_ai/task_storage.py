"""Central AI Task Storage v0.2."""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class TaskStorage:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            str(self.db_path), timeout=10
        )

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def save(self, task, conn=None):
        if not isinstance(task, dict):
            raise ValueError("INVALID_TASK")

        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("INVALID_TASK_ID")

        if task.get("approved") is not False:
            raise ValueError("APPROVAL_BLOCKED")

        if task.get("deployment_allowed") is not False:
            raise ValueError("DEPLOYMENT_BLOCKED")

        nested = task.get("task")
        if not isinstance(nested, dict):
            raise ValueError("INVALID_TASK_PAYLOAD")

        if nested.get("approved") is not False:
            raise ValueError("APPROVAL_BLOCKED")

        if nested.get("deployment_allowed") is not False:
            raise ValueError("DEPLOYMENT_BLOCKED")

        if task.get("status") != "planned":
            raise ValueError("INVALID_INITIAL_STATUS")

        if nested.get("stage") != "plan":
            raise ValueError("INVALID_INITIAL_STAGE")

        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(task)

        if conn is None:
            with self._connect() as own_conn:
                return self.save(task, conn=own_conn)
        if not isinstance(conn, sqlite3.Connection):
            raise ValueError('INVALID_CONNECTION')
        conn.execute("""
            INSERT INTO tasks
            (task_id, status, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            task_id, "planned", payload, now, now
        ))

        return task_id

    def get(self, task_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM tasks WHERE task_id=?",
                (task_id,)
            ).fetchone()

        return json.loads(row[0]) if row else None

    def list_tasks(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM tasks ORDER BY created_at"
            ).fetchall()

        return [json.loads(row[0]) for row in rows]
