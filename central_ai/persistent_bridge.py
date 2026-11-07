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

    def submit_revision(self, parent_task_id, expected_parent_nonce):
        """Reserve a linked candidate slot atomically; never call a model or verify.

        Three candidates per explicitly submitted root, including the root.
        A reserved child is never refunded or replaced after a crash.
        """
        import json
        import re
        from datetime import datetime, timezone
        child_id = None
        try:
            with self.storage._connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                parent = self.storage._review_task(conn, parent_task_id)
                audit = parent.get('verification', {})
                outcome = audit.get('outcome', {})
                if (audit.get('phase') != 'completed' or audit.get('nonce') != expected_parent_nonce
                        or not isinstance(expected_parent_nonce, str)
                        or not re.fullmatch(r'[0-9a-f]{32}', expected_parent_nonce)
                        or outcome.get('test_status') != 'failed' or outcome.get('tests_passed') is not False
                        or outcome.get('completion_confirmed') is not False
                        or outcome.get('quarantine_required') is not False
                        or outcome.get('execution_policy') != 'bounded-arithmetic-v1'
                        or outcome.get('approved') is not False or outcome.get('deployment_allowed') is not False
                        or outcome.get('verification_binding') != audit.get('binding')):
                    raise ValueError('REVISION_PARENT_NOT_ELIGIBLE')
                # The same DB-wide unresolved verification barrier applies to reservation.
                for (encoded,) in conn.execute('SELECT payload FROM tasks'):
                    other = json.loads(encoded).get('verification')
                    if other is not None and (not isinstance(other, dict)
                            or other.get('phase') not in ('completed','blocked')
                            or other.get('approved') is not False or other.get('deployment_allowed') is not False):
                        raise ValueError('VERIFICATION_DATABASE_BLOCKED')
                lineage = parent.get('revision')
                root_id = lineage['root_task_id'] if isinstance(lineage, dict) else parent_task_id
                root = self.storage._review_task(conn, root_id)
                digest = root.get('analysis', {}).get('source_sha256')
                test_digest = audit.get('binding', {}).get('test_sha256')
                if (not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                        or parent.get('analysis', {}).get('source_sha256') != digest
                        or not isinstance(test_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', test_digest)):
                    raise ValueError('REVISION_SOURCE_NOT_BOUND')
                family = root.get('revision_family', {'schema':'revision-family-v1',
                    'members':[root_id], 'source_sha256':digest, 'test_sha256':test_digest})
                members = family.get('members')
                if (family.get('schema') != 'revision-family-v1' or not isinstance(members, list)
                        or not 1 <= len(members) <= 3 or members[0] != root_id
                        or len(set(members)) != len(members) or members[-1] != parent_task_id
                        or family.get('source_sha256') != digest or family.get('test_sha256') != test_digest
                        or (lineage is not None and (lineage.get('schema') != 'revision-v1'
                            or lineage.get('ordinal') != len(members)
                            or lineage.get('source_sha256') != digest or lineage.get('test_sha256') != test_digest))):
                    raise ValueError('REVISION_FAMILY_CONFLICT')
                if len(members) >= 3:
                    raise ValueError('REVISION_BUDGET_EXHAUSTED')
                child = self.bridge.submit(parent['task']['task'])
                child_id = child['task_id']
                child['revision'] = {'schema':'revision-v1', 'root_task_id':root_id,
                    'parent_task_id':parent_task_id, 'parent_verification_nonce':expected_parent_nonce,
                    'ordinal':len(members)+1, 'source_sha256':digest, 'test_sha256':test_digest}
                self.storage.save(child, conn=conn)
                self.workflow.insert_prepared(self.workflow.prepare_registration(child), conn)
                self.queue.enqueue(child_id, conn=conn)
                conn.execute('INSERT INTO task_file_targets (task_id,workspace,filename) '
                    'SELECT ?,workspace,filename FROM task_file_targets WHERE task_id=? '
                    'AND approved=0 AND deployment_allowed=0', (child_id, root_id))
                if conn.execute('SELECT changes()').fetchone()[0] != 1:
                    raise ValueError('REVISION_TARGET_MISSING')
                root['revision_family'] = dict(family, members=members+[child_id],
                    updated_at=datetime.now(timezone.utc).isoformat())
                self.storage._write_review_task(conn, root_id, root)
            return child

        except BaseException:
            if child_id is not None:
                self.bridge.registry.pop(child_id, None)
            raise
