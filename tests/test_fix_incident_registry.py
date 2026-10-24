"""A11.15.6 persistent FIX incident deduplication tests."""
import tempfile
import unittest
from pathlib import Path

from central_ai.fix_incident_registry import FixIncidentRegistry, fingerprint


class FixIncidentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "incidents.sqlite3"
        self.registry = FixIncidentRegistry(self.path)

    def test_duplicate_reuses_original_incident(self):
        first = self.registry.register(
            "task-1", "DeveloperWorker", "FileNotFoundError", "analyze"
        )
        second = self.registry.register(
            "task-2", "DeveloperWorker", "FileNotFoundError", "analyze"
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(second["source_task_id"], "task-1")
        self.assertEqual(second["occurrences"], 2)

    def test_persists_after_restart(self):
        self.registry.register("task-1", "Worker", "OSError", "analyze")
        restarted = FixIncidentRegistry(self.path)
        item = restarted.register("task-2", "Worker", "OSError", "analyze")
        self.assertFalse(item["created"])
        self.assertEqual(item["occurrences"], 2)

    def test_different_operation_is_separate(self):
        first = self.registry.register("task-1", "Worker", "OSError", "analyze")
        second = self.registry.register("task-2", "Worker", "OSError", "validate")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_terminal_incident_cannot_reopen(self):
        item = self.registry.register("task-1", "Worker", "OSError", "analyze")
        self.assertTrue(self.registry.transition(item["fingerprint"], "ESCALATED"))
        self.assertFalse(self.registry.transition(item["fingerprint"], "VERIFIED"))
        again = self.registry.register("task-2", "Worker", "OSError", "analyze")
        self.assertEqual(again["status"], "ESCALATED")
        self.assertFalse(again["created"])

    def test_rejects_untrusted_identifiers(self):
        with self.assertRaises(ValueError):
            fingerprint("Worker", "FileNotFoundError: /private/path", "analyze")
        with self.assertRaises(ValueError):
            self.registry.register("../task", "Worker", "OSError", "analyze")

    def test_never_grants_approval_or_deployment(self):
        item = self.registry.register("task-1", "Worker", "OSError", "analyze")
        self.assertFalse(item["approved"])
        self.assertFalse(item["deployment_allowed"])


if __name__ == "__main__":
    unittest.main()
