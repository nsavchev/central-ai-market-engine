import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from central_ai.repair_budget import RepairBudget
from central_ai.repair_lineage import RepairLineage


ROOT = hashlib.sha256(b"shared-root").hexdigest()


class AtomicLineageBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "shared.sqlite"
        self.lineage = RepairLineage(self.path)
        self.lineage.register_root("root-task", ROOT)
        self.lineage.register_child("fix-1", "root-task", ROOT)
        self.lineage.register_child("fix-2", "root-task", ROOT)
        self.budget = RepairBudget(self.path)

    def test_reservation_requires_admitted_attempt(self):
        denied = self.budget.reserve_lineage_task("fix-1", estimated_cost_units=10)
        self.assertEqual(denied["reason"], "UNKNOWN_BUDGET")
        self.budget.admit(ROOT, "First")
        self.assertTrue(self.budget.reserve_lineage_task(
            "fix-1", estimated_cost_units=10
        )["reserved"])

    def test_same_child_cannot_reserve_twice_after_restart(self):
        self.budget.admit(ROOT, "First")
        self.budget.reserve_lineage_task("fix-1", estimated_cost_units=10)
        restarted = RepairBudget(self.path)
        self.assertEqual(restarted.reserve_lineage_task(
            "fix-1", estimated_cost_units=10
        )["reason"], "ALREADY_RESERVED")

    def test_siblings_share_one_root_attempt_budget(self):
        self.budget.admit(ROOT, "First")
        self.assertTrue(self.budget.reserve_lineage_task(
            "fix-1", estimated_cost_units=10
        )["reserved"])
        self.assertEqual(self.budget.reserve_lineage_task(
            "fix-2", estimated_cost_units=10
        )["reason"], "NO_UNRESERVED_ATTEMPT")
        self.budget.admit(ROOT, "Second")
        self.assertTrue(self.budget.reserve_lineage_task(
            "fix-2", estimated_cost_units=10
        )["reserved"])

    def test_concurrent_duplicate_child_only_reserves_once(self):
        self.budget.admit(ROOT, "First")

        def reserve(_):
            return RepairBudget(self.path).reserve_lineage_task(
                "fix-1", estimated_cost_units=10
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(reserve, range(12)))
        self.assertEqual(sum(r["reserved"] for r in results), 1)

    def test_unknown_child_denied(self):
        self.budget.admit(ROOT, "First")
        self.assertEqual(self.budget.reserve_lineage_task(
            "unknown", estimated_cost_units=10
        )["reason"], "UNKNOWN_CHILD")

    def test_terminal_budget_denied(self):
        self.budget.admit(ROOT, "First")
        self.budget.close(ROOT, "CANCELLED")
        self.assertEqual(self.budget.reserve_lineage_task(
            "fix-1", estimated_cost_units=10
        )["reason"], "BUDGET_CLOSED")


if __name__ == "__main__":
    unittest.main()
