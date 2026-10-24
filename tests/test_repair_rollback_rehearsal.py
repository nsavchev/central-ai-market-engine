import hashlib
import tempfile
import unittest
from pathlib import Path

from central_ai.repair_rollback_rehearsal import RepairRollbackRehearsal


class RepairRollbackRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.workspace = root / "source"
        self.staging = root / "staging"
        self.workspace.mkdir()
        self.staging.mkdir()
        self.source = self.workspace / "worker.py"
        self.source.write_text("VALUE = 1\n")
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.rehearsal = RepairRollbackRehearsal(self.workspace, self.staging)

    def test_rollback_rehearsed_in_temporary_copy(self):
        result = self.rehearsal.rehearse("worker.py", self.sha, "VALUE = 2\n")
        self.assertTrue(result["rollback_rehearsed"])
        self.assertFalse(result["applied"])
        self.assertFalse(result["deployment_allowed"])
        self.assertEqual(self.source.read_text(), "VALUE = 1\n")
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_stale_source_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
            self.rehearsal.rehearse("worker.py", "0" * 64, "VALUE = 2\n")

    def test_invalid_candidate_is_blocked(self):
        with self.assertRaises(SyntaxError):
            self.rehearsal.rehearse("worker.py", self.sha, "def invalid(:\n")

    def test_traversal_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "PATH_BLOCKED"):
            self.rehearsal.rehearse("../worker.py", self.sha, "VALUE = 2\n")


if __name__ == "__main__":
    unittest.main()
