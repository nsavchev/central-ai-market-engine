"""Central AI Persistent Workflow v0.5.

Planning and workflow tracking only.
No deployment or external execution.
"""

import json
import sqlite3
from datetime import datetime, timezone

from central_ai.workflow_controller_v03 import (
    WorkflowController,
    STAGES,
)


class PersistentWorkflowV05:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.controller = WorkflowController()
        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            self.db_path,
            timeout=10,
        )


    def _persist(
        self, state, *, create=False,
        expected_version=None
    ):
        if state["stage"] not in STAGES:
            raise ValueError("INVALID_STAGE")

        if (
            state["approved"] is not False
            or state["deployment_allowed"] is not False
        ):
            raise ValueError("SECURITY_BLOCK")

        attempts = state["attempts"]

        if type(attempts) is not int or not 0 <= attempts <= 3:
            raise ValueError("INVALID_ATTEMPTS")

        if not isinstance(state["history"], list):
            raise ValueError("INVALID_HISTORY")

        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as con:
            if create:
                con.execute(
                    """
                    INSERT INTO workflow_states
                    (task_id, stage, attempts, approved,
                     deployment_allowed, history, updated_at,
                     version)
                    VALUES (?, ?, ?, 0, 0, ?, ?, 0)
                    """,
                    (
                        state["task_id"],
                        state["stage"],
                        attempts,
                        json.dumps(state["history"]),
                        now,
                    ),
                )
                return 0

            if (
                type(expected_version) is not int
                or expected_version < 0
            ):
                raise ValueError("EXPECTED_VERSION_REQUIRED")

            cursor = con.execute(
                """
                UPDATE workflow_states
                SET stage=?,
                    attempts=?,
                    history=?,
                    updated_at=?,
                    version=version+1
                WHERE task_id=?
                  AND version=?
                  AND approved=0
                  AND deployment_allowed=0
                """,
                (
                    state["stage"],
                    attempts,
                    json.dumps(state["history"]),
                    now,
                    state["task_id"],
                    expected_version,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError("VERSION_CONFLICT")

            return expected_version + 1

    def register(self, task):
        task_id = task["task_id"]

        if task_id in self.controller.tasks:
            raise ValueError("DUPLICATE_TASK")

        with self._connect() as con:
            exists = con.execute(
                "SELECT 1 FROM workflow_states WHERE task_id=?",
                (task_id,),
            ).fetchone()

        if exists:
            raise ValueError("DUPLICATE_TASK")

        state = self.controller.register(task)

        try:
            self._persist(state, create=True)
        except Exception:
            self.controller.tasks.pop(task_id, None)
            raise

        return state


    def restore(self, task_id):
        from central_ai.workflow_controller_v03 import (
            WorkflowState,
        )

        with self._connect() as con:
            row = con.execute(
                """
                SELECT stage, attempts, approved,
                       deployment_allowed, history, version
                FROM workflow_states
                WHERE task_id=?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            raise ValueError("TASK_NOT_FOUND")

        stage, attempts, approved, deployment, history, version = row

        if stage not in STAGES:
            raise ValueError("INVALID_STORED_STAGE")

        if approved != 0 or deployment != 0:
            raise ValueError("STORED_SECURITY_VIOLATION")

        if type(attempts) is not int or not 0 <= attempts <= 3:
            raise ValueError("INVALID_ATTEMPTS")

        if type(version) is not int or version < 0:
            raise ValueError("INVALID_VERSION")

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
        return self.controller.status(task_id), version

    def status(self, task_id):
        state, _version = self.restore(task_id)
        return state


    def _read_version(self, task_id):
        with self._connect() as con:
            row = con.execute(
                """
                SELECT version
                FROM workflow_states
                WHERE task_id=?
                  AND approved=0
                  AND deployment_allowed=0
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            raise ValueError("TASK_NOT_FOUND")

        return row[0]

    def advance(self, task_id, checks_passed=False):
        if checks_passed is not True:
            raise ValueError("CHECKS_REQUIRED")

        _, version = self.restore(task_id)

        import copy
        snapshot = copy.deepcopy(
            self.controller.tasks[task_id]
        )

        try:
            state = self.controller.advance(
                task_id,
                checks_passed=True,
            )

            self._persist(
                state,
                expected_version=version,
            )

            return state

        except Exception:
            self.controller.tasks[task_id] = snapshot
            raise

    def retry(self, task_id):
        _, version = self.restore(task_id)

        import copy
        snapshot = copy.deepcopy(
            self.controller.tasks[task_id]
        )

        try:
            state = self.controller.retry(task_id)

            self._persist(
                state,
                expected_version=version,
            )

            return state

        except Exception:
            self.controller.tasks[task_id] = snapshot
            raise

    def prepare_registration(self, task):
        from central_ai.workflow_controller_v03 import WorkflowController
        temporary = WorkflowController()
        return temporary.register(task)

    def insert_prepared(self, state, conn):
        if not isinstance(conn, sqlite3.Connection):
            raise ValueError("INVALID_CONNECTION")
        if not isinstance(state, dict):
            raise ValueError("INVALID_STATE")
        if state.get("stage") not in STAGES:
            raise ValueError("INVALID_STAGE")
        if state.get("approved") is not False:
            raise ValueError("SECURITY_BLOCK")
        if state.get("deployment_allowed") is not False:
            raise ValueError("SECURITY_BLOCK")
        task_id = state.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("INVALID_TASK_ID")
        attempts = state.get("attempts")
        if type(attempts) is not int or not 0 <= attempts <= 3:
            raise ValueError("INVALID_ATTEMPTS")
        history = state.get("history")
        if not isinstance(history, list):
            raise ValueError("INVALID_HISTORY")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO workflow_states "
            "(task_id,stage,attempts,approved,"
            "deployment_allowed,history,updated_at,version) "
            "VALUES (?,?,?,0,0,?,?,0)",
            (task_id, state["stage"], attempts,
             json.dumps(history), now)
        )
        return task_id


    def _initialize(self):
        with self._connect() as conn:
            # Adopt only the known legacy v0.4 shape. Keep old persisted
            # tasks; never relax approval/deployment security constraints.
            existing = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_states'"
            ).fetchone()
            if existing:
                columns = {row[1] for row in conn.execute(
                    "PRAGMA table_info(workflow_states)").fetchall()}
                required = {"task_id", "stage", "attempts", "approved",
                            "deployment_allowed", "history", "updated_at"}
                if not required.issubset(columns):
                    raise ValueError("UNKNOWN_WORKFLOW_SCHEMA")
                if conn.execute(
                    "SELECT 1 FROM workflow_states WHERE approved IS NOT 0 "
                    "OR deployment_allowed IS NOT 0 LIMIT 1"
                ).fetchone():
                    raise ValueError("STORED_SECURITY_VIOLATION")
                if "version" not in columns:
                    conn.execute(
                        "ALTER TABLE workflow_states ADD COLUMN version INTEGER "
                        "NOT NULL DEFAULT 0 CHECK(version >= 0)"
                    )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS workflow_states (
                    task_id TEXT PRIMARY KEY,
                    stage TEXT NOT NULL DEFAULT 'plan',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    approved INTEGER NOT NULL DEFAULT 0
                        CHECK (approved = 0),
                    deployment_allowed INTEGER NOT NULL DEFAULT 0
                        CHECK (deployment_allowed = 0),
                    history TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0
                        CHECK (version >= 0)
                )
                '''
            )
