import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from central_ai.repair_budget import RepairBudget


KEY = hashlib.sha256(b"test-incident").hexdigest()


class RepairBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "budget.sqlite3"
        self.budget = RepairBudget(self.path)

    def test_at_most_three_attempts(self):
        for i in range(3):
            self.assertTrue(self.budget.admit(KEY, f"Failure{i}")["admitted"])
        denied = self.budget.admit(KEY, "Failure3")
        self.assertFalse(denied["admitted"])
        self.assertEqual(denied["status"], "ESCALATED")

    def test_budget_survives_restart(self):
        self.budget.admit(KEY, "First")
        restarted = RepairBudget(self.path)
        self.assertEqual(restarted.admit(KEY, "Second")["attempts"], 2)

    def test_repeated_same_failure_escalates(self):
        self.budget.admit(KEY, "Same")
        denied = self.budget.admit(KEY, "Same")
        self.assertFalse(denied["admitted"])
        self.assertEqual(denied["attempts"], 1)
        self.assertEqual(denied["status"], "ESCALATED")

    def test_time_window_exhaustion(self):
        with patch("central_ai.repair_budget.time.time", return_value=1000):
            self.budget.admit(KEY, "First")
        with patch("central_ai.repair_budget.time.time", return_value=1900):
            denied = self.budget.admit(KEY, "Second")
        self.assertEqual(denied["status"], "ESCALATED")

    def test_terminal_state_cannot_reopen(self):
        self.budget.admit(KEY, "First")
        self.assertTrue(self.budget.close(KEY, "CANCELLED"))
        self.assertFalse(self.budget.admit(KEY, "Second")["admitted"])

    def test_invalid_fingerprint_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_FINGERPRINT"):
            self.budget.admit("not-a-hash")

    def test_cost_reservation_is_durable(self):
        self.budget.admit(KEY, "First")
        first = self.budget.reserve_subtask(
            KEY, depth=1, estimated_cost_units=60
        )
        self.assertTrue(first["reserved"])
        restarted = RepairBudget(self.path)
        denied = restarted.reserve_subtask(
            KEY, depth=1, estimated_cost_units=50
        )
        self.assertEqual(denied["reason"], "COST_EXCEEDED")

    def test_depth_limit_denies_subtask(self):
        self.budget.admit(KEY, "First")
        denied = self.budget.reserve_subtask(
            KEY, depth=3, estimated_cost_units=10
        )
        self.assertFalse(denied["reserved"])

    def test_terminal_budget_denies_reservation(self):
        self.budget.admit(KEY, "First")
        self.budget.close(KEY, "ESCALATED")
        denied = self.budget.reserve_subtask(
            KEY, depth=1, estimated_cost_units=10
        )
        self.assertEqual(denied["reason"], "BUDGET_CLOSED")

    def test_unknown_incident_denies_reservation(self):
        denied = self.budget.reserve_subtask(
            KEY, depth=1, estimated_cost_units=10
        )
        self.assertEqual(denied["reason"], "UNKNOWN_INCIDENT")

    def test_strict_limits(self):
        with self.assertRaisesRegex(ValueError, "INVALID_MAX_ATTEMPTS"):
            RepairBudget(self.path, max_attempts=100)
        with self.assertRaisesRegex(ValueError, "INVALID_WINDOW"):
            RepairBudget(self.path, window_seconds=3600)


if __name__ == "__main__":
    unittest.main()
