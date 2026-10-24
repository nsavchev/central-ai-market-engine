import sqlite3
from central_ai.task_queue import TaskQueue
from central_ai.persistent_workflow_v05 import PersistentWorkflowV05
"""Central AI Persistent Task Bridge v0.2."""

from central_ai.task_bridge import TaskBridge
from central_ai.task_storage import TaskStorage


class PersistentTaskBridge:
    def __init__(self, db_path):
        self.bridge = TaskBridge()
        self.storage = TaskStorage(db_path)
        self.queue = TaskQueue(db_path)
        self.workflow = PersistentWorkflowV05(db_path)

    def submit(self, description):
        task = self.bridge.submit(description)
        task_id = task["task_id"]
        try:
            if task["approved"] is not False:
                raise ValueError("APPROVAL_BLOCKED")
            if task["deployment_allowed"] is not False:
                raise ValueError("DEPLOYMENT_BLOCKED")

            state = self.workflow.prepare_registration(task)

            with sqlite3.connect(
                str(self.storage.db_path), timeout=10
            ) as conn:
                conn.execute("BEGIN IMMEDIATE")
                self.storage.save(task, conn=conn)
                self.workflow.insert_prepared(state, conn)
                self.queue.enqueue(task_id, conn=conn)
                conn.commit()

            return task
        except Exception:
            self.bridge.registry.pop(task_id, None)
            raise

    def status(self, task_id):
        return self.storage.get(task_id)

    def list_tasks(self):
        return self.storage.list_tasks()


    def complete_analysis(self, task_id, agent, token, analysis):
        import json
        from datetime import datetime, timezone

        if not isinstance(analysis, dict):
            raise ValueError("INVALID_ANALYSIS")

        if not isinstance(task_id, str) or not task_id:
            raise ValueError("INVALID_TASK_ID")

        if not isinstance(agent, str) or not agent:
            raise ValueError("INVALID_AGENT")

        if not isinstance(token, str) or not token:
            raise ValueError("INVALID_TOKEN")

        analysis_json = json.dumps(analysis, allow_nan=False)

        with sqlite3.connect(
            str(self.storage.db_path),
            timeout=10
        ) as conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT payload, status FROM tasks WHERE task_id=?",
                (task_id,)
            ).fetchone()

            if row is None:
                raise ValueError("TASK_NOT_FOUND")

            payload = json.loads(row[0])

            if row[1] != "planned":
                raise ValueError("INVALID_TASK_STATUS")

            if (
                payload.get("approved") is not False
                or payload.get("deployment_allowed") is not False
            ):
                raise ValueError("SECURITY_FLAGS_INVALID")

            nested = payload.get("task")

            if not isinstance(nested, dict):
                raise ValueError("INVALID_TASK_PAYLOAD")

            if (
                nested.get("approved") is not False
                or nested.get("deployment_allowed") is not False
            ):
                raise ValueError("NESTED_SECURITY_FLAGS_INVALID")

            self.queue.complete(
                task_id,
                agent,
                token,
                conn=conn
            )

            payload["status"] = "analyzed"
            payload["analysis"] = json.loads(analysis_json)

            now = datetime.now(timezone.utc).isoformat()

            cursor = conn.execute(
                """
                UPDATE tasks
                SET status=?, payload=?, updated_at=?
                WHERE task_id=? AND status='planned'
                """,
                (
                    "analyzed",
                    json.dumps(payload, allow_nan=False),
                    now,
                    task_id
                )
            )

            if cursor.rowcount != 1:
                raise RuntimeError("TASK_UPDATE_FAILED")

            conn.commit()

        return self.storage.get(task_id)


    def task_overview(self, task_id):
        storage = self.storage.get(task_id)
        if storage is None:
            raise ValueError("TASK_NOT_FOUND")

        workflow = self.workflow.restore(task_id)[0]
        queue = self.queue.status(task_id)

        if (
            storage.get("approved") is not False
            or storage.get("deployment_allowed") is not False
            or workflow.get("approved") is not False
            or workflow.get("deployment_allowed") is not False
            or queue.get("approved") != 0
            or queue.get("deployment_allowed") != 0
        ):
            raise ValueError("SECURITY_FLAGS_INVALID")

        effective = queue["effective_status"]

        return {
            "task_id": task_id,
            "storage_status": storage["status"],
            "workflow_stage": workflow["stage"],
            "queue_status": queue["status"],
            "effective_status": effective,
            "attempt_count": queue["attempt_count"],
            "retry_exhausted": bool(queue["retry_exhausted"]),
            "requires_attention": effective == "failed",
            "approved": False,
            "deployment_allowed": False,
        }
