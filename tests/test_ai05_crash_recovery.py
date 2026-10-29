"""AI-05: simulate a crashed worker lease and prove bounded recovery."""
import sqlite3
from datetime import datetime, timedelta, timezone

from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets


def test_expired_lease_recovers_once_and_keeps_readonly_flags(tmp_path):
    db = tmp_path / "tasks.sqlite"
    workspace = tmp_path / "source"
    workspace.mkdir()
    (workspace / "sample.py").write_text("def recovered():\n    return 1\n")
    bridge = PersistentTaskBridge(db)
    task = bridge.submit("Inspect sample.py only")
    task_id = task["task_id"]
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(task_id, str(workspace), "sample.py")

    # Simulate a worker crash: the first lease is never completed.
    original = bridge.queue.acquire_next("crashed-worker", require_target=True)
    assert original["task_id"] == task_id
    with sqlite3.connect(db) as con:
        con.execute("UPDATE task_queue SET lease_until=? WHERE task_id=?",
                    ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), task_id))

    recovered = DeveloperWorkerCoordinator(db, "recovery-worker").run_once()
    assert recovered["status"] == "analyzed"
    assert recovered["approved"] is False
    assert recovered["deployment_allowed"] is False
    state = PersistentTaskBridge(db).task_overview(task_id)
    assert state["queue_status"] == "done"
    assert state["attempt_count"] == 2
    assert DeveloperWorkerCoordinator(db, "recovery-worker").run_once() is None


def test_three_expired_leases_exhaust_retries(tmp_path):
    db = tmp_path / "tasks.sqlite"
    workspace = tmp_path / "source"
    workspace.mkdir()
    (workspace / "sample.py").write_text("pass\n")
    bridge = PersistentTaskBridge(db)
    task = bridge.submit("Inspect sample.py only")
    task_id = task["task_id"]
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(task_id, str(workspace), "sample.py")

    for attempt in range(3):
        lease = bridge.queue.acquire_next("crashed-worker", require_target=True)
        assert lease["task_id"] == task_id
        with sqlite3.connect(db) as con:
            con.execute("UPDATE task_queue SET lease_until=? WHERE task_id=?",
                        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), task_id))
    assert bridge.queue.acquire_next("recovery-worker", require_target=True) is None
    state = bridge.task_overview(task_id)
    assert state["retry_exhausted"] is True
    assert state["requires_attention"] is True
    assert state["approved"] is False
    assert state["deployment_allowed"] is False
