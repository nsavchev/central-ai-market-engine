import unittest

from developer_agent.v3.workflow import Workflow, Stage
from developer_agent.v3.orchestrator import DeveloperOrchestrator


class WorkflowTests(unittest.TestCase):

    def test_initial_state(self):
        w = Workflow()
        self.assertEqual(w.stage, Stage.PLAN)
        self.assertFalse(w.approved)
        self.assertFalse(w.deployment_allowed)

    def test_requires_checks(self):
        w = Workflow()
        with self.assertRaises(ValueError):
            w.advance(False)
        self.assertEqual(w.stage, Stage.PLAN)

    def test_stage_transitions(self):
        w = Workflow()
        for expected in (
            Stage.DEVELOP,
            Stage.TEST,
            Stage.REVIEW,
            Stage.APPROVAL,
        ):
            self.assertEqual(w.advance(True), expected)

        with self.assertRaises(ValueError):
            w.advance(True)

        self.assertFalse(w.deployment_allowed)

    def test_retry_limit(self):
        w = Workflow()
        for attempt in range(1, 4):
            w.advance(True)
            w.advance(True)
            self.assertEqual(w.retry(), attempt)

        with self.assertRaises(ValueError):
            w.retry()

        self.assertFalse(w.deployment_allowed)

    def test_task_validation(self):
        manager = DeveloperOrchestrator()

        for invalid in ("", " ", "x" * 4001, None):
            with self.assertRaises(ValueError):
                manager.create_task(invalid)

        task = manager.create_task("SEC EDGAR import")
        status = manager.status(task)

        self.assertEqual(status["stage"], Stage.PLAN)
        self.assertFalse(status["approved"])
        self.assertFalse(status["deployment_allowed"])


if __name__ == "__main__":
    unittest.main()
