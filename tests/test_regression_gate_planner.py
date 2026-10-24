import unittest
from central_ai.regression_gate_planner import RegressionGatePlanner


class RegressionGatePlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = RegressionGatePlanner()

    def test_targeted_and_full_suite_planned(self):
        plan = self.planner.plan(["incident_registry", "failure_audit"])
        self.assertEqual(len(plan["targeted_commands"]), 2)
        self.assertEqual(plan["regression_command"][:4],
                         ["python", "-m", "unittest", "discover"])
        self.assertFalse(plan["execute"])
        self.assertFalse(plan["deployment_allowed"])
        self.assertTrue(plan["requires_review"])

    def test_rejects_arbitrary_test_name(self):
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_TEST_MODULE"):
            self.planner.plan(["../../outside.py"])

    def test_rejects_empty_modules(self):
        with self.assertRaisesRegex(ValueError, "INVALID_MODULES"):
            self.planner.plan([])

    def test_rejects_invalid_flag(self):
        with self.assertRaisesRegex(ValueError, "INVALID_REGRESSION_FLAG"):
            self.planner.plan(["failure_audit"], include_regression="yes")

    def test_optional_full_regression(self):
        plan = self.planner.plan(["rollback_rehearsal"], include_regression=False)
        self.assertIsNone(plan["regression_command"])

    def test_rejects_duplicate_budget_excess(self):
        with self.assertRaisesRegex(ValueError, "TOO_MANY_MODULES"):
            self.planner.plan(["failure_audit"] * 5)


if __name__ == "__main__":
    unittest.main()
