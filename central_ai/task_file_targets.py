import sqlite3
from pathlib import Path, PurePosixPath


class TaskFileTargets:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def initialize(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_file_targets (
                    task_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0
                        CHECK(approved = 0),
                    deployment_allowed INTEGER NOT NULL DEFAULT 0
                        CHECK(deployment_allowed = 0)
                )
            """)

    def register(self, task_id, workspace, filename):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("INVALID_TASK_ID")

        if not isinstance(workspace, str) or not workspace.strip():
            raise ValueError("INVALID_WORKSPACE")

        if not isinstance(filename, str) or not filename:
            raise ValueError("INVALID_FILENAME")

        path = PurePosixPath(filename)

        if (
            path.is_absolute()
            or path.suffix != ".py"
            or any(part in ("", ".", "..") for part in filename.split("/"))
            or "\\" in filename
        ):
            raise ValueError("PATH_BLOCKED")

        root = Path(workspace).resolve(strict=True)

        if not root.is_dir():
            raise ValueError("INVALID_WORKSPACE")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT status, payload FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is None:
                raise ValueError("TASK_NOT_FOUND")

            import json
            payload = json.loads(existing[1])
            if existing[0] != "planned":
                raise ValueError("INVALID_TASK_STATUS")
            if (
                payload.get("approved") is not False
                or payload.get("deployment_allowed") is not False
            ):
                raise ValueError("SECURITY_FLAGS_INVALID")

            nested = payload.get("task")
            if not isinstance(nested, dict) or (
                nested.get("approved") is not False
                or nested.get("deployment_allowed") is not False
            ):
                raise ValueError("NESTED_SECURITY_FLAGS_INVALID")

            conn.execute(
                """
                INSERT INTO task_file_targets
                    (task_id, workspace, filename)
                VALUES (?, ?, ?)
                """,
                (task_id, str(root), filename),
            )

        return task_id

    def get(self, task_id):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT task_id, workspace, filename,
                       approved, deployment_allowed
                FROM task_file_targets
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        return dict(zip(
            (
                "task_id",
                "workspace",
                "filename",
                "approved",
                "deployment_allowed",
            ),
            row,
        ))
