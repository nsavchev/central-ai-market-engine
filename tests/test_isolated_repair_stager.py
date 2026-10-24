import hashlib
import tempfile
import unittest
from pathlib import Path

from central_ai.isolated_repair_stager import IsolatedRepairStager


class IsolatedRepairStagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.staging = root / "staging"
        self.workspace.mkdir()
        self.staging.mkdir()
        self.source = self.workspace / "worker.py"
        self.source.write_text("VALUE = 1\n", encoding="utf-8")
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.stager = IsolatedRepairStager(self.workspace, self.staging)

    def test_valid_candidate_does_not_change_original(self):
        result = self.stager.stage("worker.py", self.sha, "VALUE = 2\n")
        self.assertTrue(result["syntax_valid"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.source.read_text(), "VALUE = 1\n")
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_rejects_stale_source_hash(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED"):
            self.stager.stage("worker.py", "0" * 64, "VALUE = 2\n")

    def test_rejects_syntax_error(self):
        with self.assertRaises(SyntaxError):
            self.stager.stage("worker.py", self.sha, "def broken(:\n")

    def test_rejects_traversal(self):
        with self.assertRaisesRegex(ValueError, "PATH_BLOCKED"):
            self.stager.stage("../worker.py", self.sha, "VALUE = 2\n")

    def test_rejects_symlink_target(self):
        (self.workspace / "linked.py").symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "UNSAFE_TARGET"):
            self.stager.stage("linked.py", self.sha, "VALUE = 2\n")

    def test_rejects_overlapping_workspace_and_staging(self):
        with self.assertRaisesRegex(ValueError, "STAGING_NOT_ISOLATED"):
            IsolatedRepairStager(self.workspace, self.workspace)


if __name__ == "__main__":
    unittest.main()
