"""Regression tests for sanitized Central AI failure auditing."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from central_ai.task_queue import TaskQueue


class FailureAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.queue = TaskQueue(Path(self.tmp.name) / "tasks.db")
        self.queue.enqueue("task-1")

    def test_current_owner_can_audit_without_finishing_task(self):
        token = self.queue.acquire("task-1", "worker-a")
        self.assertTrue(
            self.queue.record_failure(
                "task-1", "worker-a", token, "FileNotFoundError"
            )
        )
        self.assertIn(
            "failed:FileNotFoundError",
            [entry["event"] for entry in self.queue.audit("task-1")],
        )
        self.assertEqual(self.queue.status("task-1")["status"], "leased")
        self.assertEqual(self.queue.status("task-1")["approved"], 0)
        self.assertEqual(self.queue.status("task-1")["deployment_allowed"], 0)

    def test_wrong_owner_or_token_cannot_write(self):
        token = self.queue.acquire("task-1", "worker-a")
        self.assertFalse(
            self.queue.record_failure(
                "task-1", "worker-b", token, "RuntimeError"
            )
        )
        self.assertFalse(
            self.queue.record_failure(
                "task-1", "worker-a", "incorrect-token", "RuntimeError"
            )
        )
        self.assertFalse(
            any(entry["event"].startswith("failed:")
                for entry in self.queue.audit("task-1"))
        )

    def test_error_messages_and_secrets_are_rejected(self):
        token = self.queue.acquire("task-1", "worker-a")
        with self.assertRaises(ValueError):
            self.queue.record_failure(
                "task-1", "worker-a", token,
                "FileNotFoundError: /secret/path"
            )
        self.assertFalse(
            any(entry["event"].startswith("failed:")
                for entry in self.queue.audit("task-1"))
        )

    def test_expired_lease_cannot_write_failure(self):
        token = self.queue.acquire("task-1", "worker-a")
        with self.queue._connect() as con:
            con.execute(
                "UPDATE task_queue SET lease_until=? WHERE task_id=?",
                ("2000-01-01T00:00:00+00:00", "task-1"),
            )
        self.assertFalse(
            self.queue.record_failure(
                "task-1", "worker-a", token, "FileNotFoundError"
            )
        )

    def test_invalid_error_code_is_rejected(self):
        token = self.queue.acquire("task-1", "worker-a")
        for code in ("", "RuntimeError: secret", "bad/path", "two words"):
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    self.queue.record_failure("task-1", "worker-a", token, code)

    def test_completed_task_cannot_receive_failure(self):
        token = self.queue.acquire("task-1", "worker-a")
        self.queue.complete("task-1", "worker-a", token)
        self.assertFalse(
            self.queue.record_failure(
                "task-1", "worker-a", token, "RuntimeError"
            )
        )


if __name__ == "__main__":
    unittest.main()
