"""AI-20: exercise existing SQLite queue bounded retries across process recreation."""
from datetime import datetime, timedelta, timezone
import sqlite3

from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.task_queue import TaskQueue


def test_expired_lease_cannot_retry_more_than_three_times(tmp_path):
    db = tmp_path / "tasks.sqlite"
    source = tmp_path / "workspace"
    source.mkdir()
    (source / "module.py").write_text("def source():\n    return 1\n")
    task = PersistentTaskBridge(db).submit("Inspect module.py")
    target = TaskFileTargets(db)
    target.initialize()
    target.register(task["task_id"], str(source), "module.py")
    task_id = task["task_id"]
    for attempt in range(1, 4):
        # Each acquisition reopens the queue, simulating a restarted worker.
        queue = TaskQueue(db)
        lease = queue.acquire_next("bounded-test-agent", seconds=30, require_target=True)
        assert lease is not None
        assert lease["task_id"] == task_id
        assert queue.status(task_id)["attempt_count"] == attempt
        # Simulate lease timeout without running any code.
        with sqlite3.connect(db) as con:
            con.execute("UPDATE task_queue SET lease_until=? WHERE task_id=?",
                        ((datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(), task_id))
    reopened = TaskQueue(db)
    assert reopened.acquire_next("bounded-test-agent", seconds=30, require_target=True) is None
    status = reopened.status(task_id)
    assert status["attempt_count"] == 3
    assert status["retry_exhausted"] == 1
    assert status["effective_status"] == "failed"
    assert status["deployment_allowed"] == 0
    assert status["approved"] == 0
