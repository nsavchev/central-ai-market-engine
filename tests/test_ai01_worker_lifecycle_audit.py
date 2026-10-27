"""AI-01: exercise the existing task queue/coordinator without HTTP or deployment.

Uses a temporary SQLite database and a temporary Python source file.
"""
from pathlib import Path

from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator


def test_existing_worker_lifecycle_survives_reopen(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.py").write_text("def inspected():\n    return 1\n")

    bridge = PersistentTaskBridge(db_path)
    task = bridge.submit("Analyze sample.py without modifying files")
    task_id = task["task_id"]
    assert task["approved"] is False
    assert task["deployment_allowed"] is False

    targets = TaskFileTargets(db_path)
    targets.initialize()
    targets.register(task_id, str(workspace), "sample.py")

    # Reinitialize all coordinator objects, mirroring a process restart.
    worker = DeveloperWorkerCoordinator(db_path, "isolated-test-agent")
    outcome = worker.run_once()
    assert outcome is not None
    assert outcome["status"] == "analyzed"
    assert outcome["approved"] is False
    assert outcome["deployment_allowed"] is False

    reopened = PersistentTaskBridge(db_path)
    assert reopened.status(task_id)["status"] == "analyzed"
    overview = reopened.task_overview(task_id)
    assert overview["approved"] is False
    assert overview["deployment_allowed"] is False
    assert worker.run_once() is None
