import hashlib
import tempfile
import unittest
from pathlib import Path

from central_ai.repair_lineage import RepairLineage


ROOT = hashlib.sha256(b"root").hexdigest()
OTHER = hashlib.sha256(b"other").hexdigest()


class RepairLineageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "lineage.sqlite"
        self.ledger = RepairLineage(self.db)
        self.assertTrue(self.ledger.register_root("root-task", ROOT))

    def test_child_inherits_root(self):
        item = self.ledger.register_child("fix-1", "root-task", ROOT)
        self.assertEqual(item["depth"], 1)
        self.assertEqual(item["root_fingerprint"], ROOT)

    def test_grandchild_inherits_root(self):
        self.ledger.register_child("fix-1", "root-task", ROOT)
        item = self.ledger.register_child("fix-2", "fix-1", ROOT)
        self.assertEqual(item["depth"], 2)

    def test_third_level_denied(self):
        self.ledger.register_child("fix-1", "root-task", ROOT)
        self.ledger.register_child("fix-2", "fix-1", ROOT)
        with self.assertRaisesRegex(ValueError, "DEPTH_EXCEEDED"):
            self.ledger.register_child("fix-3", "fix-2", ROOT)

    def test_root_mismatch_denied(self):
        with self.assertRaisesRegex(ValueError, "ROOT_MISMATCH"):
            self.ledger.register_child("fix-1", "root-task", OTHER)

    def test_reparent_denied(self):
        self.ledger.register_child("fix-1", "root-task", ROOT)
        self.ledger.register_child("fix-2", "root-task", ROOT)
        with self.assertRaisesRegex(ValueError, "LINEAGE_CONFLICT"):
            self.ledger.register_child("fix-2", "fix-1", ROOT)

    def test_idempotent_and_persistent(self):
        self.ledger.register_child("fix-1", "root-task", ROOT)
        restarted = RepairLineage(self.db)
        self.assertFalse(restarted.register_child("fix-1", "root-task", ROOT)["created"])
        self.assertEqual(restarted.lookup("fix-1")["root_fingerprint"], ROOT)

    def test_unknown_parent_denied(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_PARENT"):
            self.ledger.register_child("fix-1", "missing", ROOT)

    def test_root_identity_cannot_change(self):
        with self.assertRaisesRegex(ValueError, "LINEAGE_CONFLICT"):
            self.ledger.register_root("root-task", OTHER)


if __name__ == "__main__":
    unittest.main()
