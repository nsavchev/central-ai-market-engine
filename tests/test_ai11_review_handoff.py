import json
import os
import pytest

from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
from central_ai.review_handoff import create_review_handoff


def test_readonly_handoff_after_analyzed_task(tmp_path):
    db = tmp_path / "tasks.sqlite"
    workspace = tmp_path / "source"
    workspace.mkdir()
    target = workspace / "module.py"
    target.write_text("def stable():\n    return 7\n")
    before = target.read_bytes()
    bridge = PersistentTaskBridge(db)
    task_id = bridge.submit("Analyze module only")["task_id"]
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(task_id, str(workspace), "module.py")
    assert DeveloperWorkerCoordinator(db, "ai11-review").run_once()["status"] == "analyzed"

    review = tmp_path / "review"
    review.mkdir(mode=0o700)
    outcome = create_review_handoff(
        enabled="YES", database=str(db), task_id=task_id,
        output_directory=str(review),
    )
    manifest = json.loads((review / ("handoff_" + task_id + ".json")).read_text())
    assert outcome["status"] == "review_required"
    assert manifest["patch"] is None
    assert manifest["approved"] is False
    assert manifest["deployment_allowed"] is False
    assert manifest["production_modified"] is False
    assert "stable" in manifest["analysis"]["functions"]
    assert target.read_bytes() == before
    assert (review / ("handoff_" + task_id + ".json")).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        create_review_handoff(enabled="YES", database=str(db), task_id=task_id, output_directory=str(review))


def test_disabled_handoff_denied(tmp_path):
    with pytest.raises(ValueError, match="HANDOFF_DISABLED"):
        create_review_handoff(enabled="", database=str(tmp_path / "missing.db"), task_id="bad", output_directory=str(tmp_path))


def test_pending_task_cannot_create_handoff(tmp_path):
    db = tmp_path / "tasks.sqlite"
    task_id = PersistentTaskBridge(db).submit("Pending task")["task_id"]
    review = tmp_path / "review"
    review.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="TASK_NOT_ANALYZED"):
        create_review_handoff(enabled="YES", database=str(db), task_id=task_id, output_directory=str(review))
    assert list(review.iterdir()) == []
