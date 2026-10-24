"""Persistent Workflow v0.4 - storage only."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from central_ai.workflow_controller_v03 import (
    WorkflowController,
    WorkflowState,
    STAGES,
)


class PersistentWorkflowController:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if self.db_path.is_symlink() or not self.db_path.is_file():
            raise ValueError("INVALID_DATABASE")
        self.controller = WorkflowController()

    def _connect(self):
        return sqlite3.connect(
            str(self.db_path),
            timeout=10
        )

    def register(self, task):
        result = self.controller.register(task)
        self._save(result)
        return result

    def _save(self, state):
        if state["stage"] not in STAGES:
            raise ValueError("INVALID_STAGE")

        if (state["approved"] is not False
                or state["deployment_allowed"] is not False):
            raise ValueError("SECURITY_BLOCK")

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as con:
            con.execute(
                """
                INSERT INTO workflow_states
                (task_id, stage, attempts, approved,
                 deployment_allowed, history, updated_at)
                VALUES (?, ?, ?, 0, 0, ?, ?)
                """,
                (
                    state["task_id"],
                    state["stage"],
                    state["attempts"],
                    json.dumps(state["history"]),
                    now,
                ),
            )

    def restore(self, task_id):
        with self._connect() as con:
            row = con.execute(
                """
                SELECT stage, attempts, approved,
                       deployment_allowed, history
                FROM workflow_states
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            raise ValueError("TASK_NOT_FOUND")

        stage, attempts, approved, deployment, history = row

        if stage not in STAGES:
            raise ValueError("INVALID_STORED_STAGE")

        if approved != 0 or deployment != 0:
            raise ValueError("STORED_SECURITY_VIOLATION")

        if not isinstance(attempts, int) or not 0 <= attempts <= 3:
            raise ValueError("INVALID_ATTEMPTS")

        history = json.loads(history)
        if not isinstance(history, list):
            raise ValueError("INVALID_HISTORY")

        state = WorkflowState(
            task_id=task_id,
            stage=stage,
            attempts=attempts,
            approved=False,
            deployment_allowed=False,
            history=history,
        )

        self.controller.tasks[task_id] = state
        return self.controller.status(task_id)

    def status(self, task_id):
        return self.controller.status(task_id)
