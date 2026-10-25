import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from central_ai.atomic_child_admission import AtomicChildAdmission
from central_ai.repair_budget import RepairBudget
from central_ai.repair_lineage import RepairLineage

ROOT = hashlib.sha256(b"a11.15.11-root").hexdigest()


class AtomicChildAdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "shared.sqlite"
        self.lineage = RepairLineage(self.path)
        self.lineage.register_root("root", ROOT)
        self.budget = RepairBudget(self.path)
        self.service = AtomicChildAdmission(self.path)

    def test_success_consistent_metadata(self):
        self.budget.admit(ROOT, "First")
        result = self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)
        self.assertTrue(result["reserved"])
        self.assertEqual(self.lineage.lookup("fix1")["depth"], 1)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT reservations,reserved_cost_units FROM repair_budgets").fetchone(), (1, 8))
            self.assertEqual(db.execute("SELECT cost_units FROM repair_task_reservations WHERE task_id='fix1'").fetchone(), (8,))

    def test_no_attempt_leaves_no_child(self):
        result = self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)
        self.assertEqual(result["reason"], "UNKNOWN_BUDGET")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_duplicate_is_idempotently_denied(self):
        self.budget.admit(ROOT, "First")
        self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)
        self.assertEqual(self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)["reason"], "ALREADY_REGISTERED")

    def test_cost_limit_no_partial_writes(self):
        self.budget.admit(ROOT, "First")
        self.assertEqual(self.service.register_and_reserve("fix1", "root", estimated_cost_units=90, max_cost_units=20)["reason"], "COST_EXCEEDED")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_terminal_budget_no_child(self):
        self.budget.admit(ROOT, "First")
        self.budget.close(ROOT, "CANCELLED")
        self.assertEqual(self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)["reason"], "BUDGET_CLOSED")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_concurrent_children_share_attempt(self):
        self.budget.admit(ROOT, "First")
        def reserve(i):
            return AtomicChildAdmission(self.path).register_and_reserve("fix" + str(i), "root", estimated_cost_units=8)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(r["reserved"] for r in results), 1)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM repair_lineage WHERE parent_task_id='root'").fetchone()[0], 1)

    def test_depth_limit_prevents_grandchild_child(self):
        self.budget.admit(ROOT, "First")
        self.service.register_and_reserve("fix1", "root", estimated_cost_units=8)
        self.budget.admit(ROOT, "Second")
        self.service.register_and_reserve("fix2", "fix1", estimated_cost_units=8)
        self.budget.admit(ROOT, "Third")
        self.assertEqual(self.service.register_and_reserve("fix3", "fix2", estimated_cost_units=8)["reason"], "DEPTH_EXCEEDED")
        self.assertIsNone(self.lineage.lookup("fix3"))

    def test_invalid_cost_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_COST"):
            self.service.register_and_reserve("fix1", "root", estimated_cost_units=True)


if __name__ == "__main__":
    unittest.main()
