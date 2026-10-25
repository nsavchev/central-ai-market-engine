"""End-to-end metadata integration: failure -> incident -> budget -> staging -> audit.

This exercises explicit integration steps, not autonomous coordinator wiring.
No patch execution, approvals, deployment, or brokerage calls.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from central_ai.task_queue import TaskQueue
from central_ai.fix_incident_registry import FixIncidentRegistry
from central_ai.repair_budget import RepairBudget
from central_ai.repair_lineage import RepairLineage
from central_ai.fix_staging import FixStaging


class FailureChainTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "chain.sqlite"
        self.queue = TaskQueue(self.path)
        self.incidents = FixIncidentRegistry(self.path)
        self.budget = RepairBudget(self.path)
        self.lineage = RepairLineage(self.path)
        self.staging = FixStaging(self.path)
        self.queue.enqueue("source")
        self.token = self.queue.acquire("source", "worker")

    def record_and_prepare(self):
        recorded = self.queue.record_failure("source", "worker", self.token, "RuntimeError")
        self.assertTrue(recorded)
        incident = self.incidents.register(
            "source", "DeveloperWorkerCoordinator", "RuntimeError", "run_once"
        )
        root = incident["fingerprint"]
        self.lineage.register_root("source", root)
        self.assertTrue(self.budget.admit(root, "RuntimeError")["admitted"])
        return root

    def stage(self, child="fix1", token=None):
        return self.staging.stage(
            child, "source", agent="worker",
            lease_token=self.token if token is None else token,
            estimated_cost_units=10
        )

    def test_complete_chain_is_staged_and_audited_not_executable(self):
        root = self.record_and_prepare()
        result = self.stage()
        self.assertTrue(result["staged"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["root_fingerprint"], root)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT status,approved,deployment_allowed FROM task_queue WHERE task_id='source'"
            ).fetchone()[1:], (0, 0))
            self.assertIsNone(db.execute(
                "SELECT 1 FROM task_queue WHERE task_id='fix1'"
            ).fetchone())
            self.assertEqual(db.execute(
                "SELECT state,approved,deployment_allowed FROM fix_staging WHERE child_task_id='fix1'"
            ).fetchone(), ("STAGED", 0, 0))
            self.assertEqual(db.execute(
                "SELECT reservations,reserved_cost_units FROM repair_budgets WHERE fingerprint=?", (root,)
            ).fetchone(), (1, 10))
        audit = self.queue.audit("source")
        self.assertEqual(sum(x["event"] == "failed:RuntimeError" for x in audit), 1)
        self.assertEqual(sum(x["event"] == "fix_child_staged" for x in audit), 1)

    def test_restart_deduplicates_and_preserves_audit(self):
        self.record_and_prepare()
        self.assertTrue(self.stage()["staged"])
        restarted = FixStaging(self.path)
        result = restarted.stage("fix1", "source", agent="worker",
                                 lease_token=self.token, estimated_cost_units=10)
        self.assertEqual(result["reason"], "CHILD_ALREADY_EXISTS")
        self.assertEqual(sum(x["event"] == "fix_child_staged"
                             for x in TaskQueue(self.path).audit("source")), 1)

    def test_closed_incident_blocks_child_after_valid_failure(self):
        root = self.record_and_prepare()
        self.assertTrue(self.incidents.transition(root, "ESCALATED"))
        result = self.stage()
        self.assertEqual(result["reason"], "INCIDENT_NOT_AUTHORIZED")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_stale_lease_blocks_chain(self):
        self.record_and_prepare()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE task_queue SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id='source'")
        self.assertEqual(self.stage()["reason"], "PARENT_LEASE_INVALID")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_sanitized_failure_does_not_log_exception_message(self):
        self.record_and_prepare()
        self.stage()
        combined = str(self.queue.audit("source"))
        self.assertNotIn("TOP_SECRET_DO_NOT_LOG", combined)


if __name__ == "__main__":
    unittest.main()
