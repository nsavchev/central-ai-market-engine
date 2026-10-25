"""A11.15.13 security/transaction integration tests; no execution or deployment."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from central_ai.task_queue import TaskQueue
from central_ai.repair_lineage import RepairLineage
from central_ai.repair_budget import RepairBudget
from central_ai.fix_staging import FixStaging

ROOT = hashlib.sha256(b"a11-15-13").hexdigest()


class FixStagingIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.sqlite"
        self.queue = TaskQueue(self.path)
        self.lineage = RepairLineage(self.path)
        self.budget = RepairBudget(self.path)
        self.stage = FixStaging(self.path)
        self.queue.enqueue("root")
        self.lineage.register_root("root", ROOT)
        self.token = self.queue.acquire("root", "worker")
        self.budget.admit(ROOT, "First")

    def stage_child(self, child="fix1", token=None):
        return self.stage.stage(child, "root", agent="worker",
                                lease_token=self.token if token is None else token,
                                estimated_cost_units=10)

    def counts(self):
        with sqlite3.connect(self.path) as db:
            return (db.execute("SELECT COUNT(*) FROM repair_lineage WHERE parent_task_id='root'").fetchone()[0],
                    db.execute("SELECT COUNT(*) FROM repair_task_reservations").fetchone()[0],
                    db.execute("SELECT COUNT(*) FROM fix_staging").fetchone()[0],
                    db.execute("SELECT reserved_cost_units,reservations FROM repair_budgets WHERE fingerprint=?", (ROOT,)).fetchone())

    def test_atomic_rollback_on_audit_insert_failure(self):
        before = self.counts()
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TRIGGER block_fix_audit BEFORE INSERT ON task_queue_audit
                          WHEN NEW.event='fix_child_staged'
                          BEGIN SELECT RAISE(ABORT, 'audit denied'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.stage_child()
        self.assertEqual(self.counts(), before)
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_restart_does_not_duplicate_reservations(self):
        self.assertTrue(self.stage_child()["staged"])
        again = FixStaging(self.path).stage("fix1", "root", agent="worker",
                     lease_token=self.token, estimated_cost_units=10)
        self.assertEqual(again["reason"], "CHILD_ALREADY_EXISTS")
        self.assertEqual(self.counts(), (1, 1, 1, (10, 1)))

    def test_expired_lease_denied(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE task_queue SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id='root'")
        self.assertEqual(self.stage_child()["reason"], "PARENT_LEASE_INVALID")
        self.assertEqual(self.counts(), (0, 0, 0, (0, 0)))

    def test_retry_exhausted_parent_denied(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE task_queue SET retry_exhausted=1 WHERE task_id='root'")
        self.assertTrue(self.stage_child()["staged"])

    def test_old_token_rejected_after_reacquisition(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE task_queue SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id='root'")
        next_token = self.queue.acquire("root", "other")
        self.assertIsNotNone(next_token)
        self.assertEqual(self.stage_child()["reason"], "PARENT_LEASE_INVALID")

    def test_no_executable_child_even_after_restart(self):
        self.assertTrue(self.stage_child()["staged"])
        restarted_queue = TaskQueue(self.path)
        with self.assertRaisesRegex(ValueError, "TASK_NOT_FOUND"):
            restarted_queue.status("fix1")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM fix_staging WHERE child_task_id='fix1'").fetchone(), ("STAGED",))


if __name__ == "__main__":
    unittest.main()
