import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from central_ai.task_queue import TaskQueue
from central_ai.repair_lineage import RepairLineage
from central_ai.repair_budget import RepairBudget
from central_ai.fix_staging import FixStaging
from central_ai.fix_incident_registry import FixIncidentRegistry, fingerprint

ROOT=fingerprint("DeveloperWorkerCoordinator", "RuntimeError", "run_once")

class FixStagingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"shared.sqlite"
        self.queue=TaskQueue(self.db)
        self.lineage=RepairLineage(self.db)
        self.budget=RepairBudget(self.db)
        self.stage=FixStaging(self.db)
        self.queue.enqueue("parent")
        self.lineage.register_root("parent", ROOT)
        FixIncidentRegistry(self.db).register("parent", "DeveloperWorkerCoordinator", "RuntimeError", "run_once")
        self.token=self.queue.acquire("parent","agent")
        self.budget.admit(ROOT,"First")

    def call(self,child="fix1",**kwargs):
        return self.stage.stage(child,"parent",agent=kwargs.get("agent","agent"),
            lease_token=kwargs.get("token",self.token),estimated_cost_units=10)

    def test_valid_staging_is_not_executable(self):
        result=self.call()
        self.assertTrue(result["staged"])
        self.assertFalse(result["executable"])
        with sqlite3.connect(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM task_queue WHERE task_id='fix1'").fetchone())
            self.assertEqual(conn.execute("SELECT state,approved,deployment_allowed FROM fix_staging").fetchone(),("STAGED",0,0))

    def test_wrong_token_leaves_no_child(self):
        self.assertEqual(self.call(token="wrong")["reason"],"PARENT_LEASE_INVALID")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_wrong_owner_denied(self):
        self.assertEqual(self.call(agent="another")["reason"],"PARENT_LEASE_INVALID")

    def test_completed_parent_denied(self):
        self.queue.complete("parent","agent",self.token)
        self.assertEqual(self.call()["reason"],"PARENT_LEASE_INVALID")

    def test_duplicate_denied(self):
        self.assertTrue(self.call()["staged"])
        self.assertEqual(self.call()["reason"],"CHILD_ALREADY_EXISTS")

    def test_budget_terminal_denied(self):
        self.budget.close(ROOT,"CANCELLED")
        self.assertEqual(self.call()["reason"],"BUDGET_CLOSED")
        self.assertIsNone(self.lineage.lookup("fix1"))

    def test_concurrent_calls_only_one_succeeds(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda i:self.call("fix"+str(i)),range(8)))
        self.assertEqual(sum(r["staged"] for r in results),1)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fix_staging").fetchone()[0],1)

if __name__=="__main__":
    unittest.main()
