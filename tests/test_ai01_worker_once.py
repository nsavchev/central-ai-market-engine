"""The worker may only run after explicit opt-in, once per invocation."""
import pytest
from central_ai.worker_once import main
from central_ai.persistent_bridge import PersistentTaskBridge


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CENTRAL_WORKER_ONCE_ENABLED", raising=False)
    monkeypatch.setenv("CENTRAL_TASK_DB", str(tmp_path / "tasks.sqlite"))
    with pytest.raises(SystemExit, match="WORKER_DISABLED"):
        main()


def test_one_shot_process_uses_existing_coordinator(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "example.py").write_text("def example():\n    return 1\n")
    db = tmp_path / "tasks.sqlite"
    bridge = PersistentTaskBridge(db)
    task = bridge.submit("Analyze example.py read-only")
    from central_ai.task_file_targets import TaskFileTargets
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(task["task_id"], str(workspace), "example.py")
    monkeypatch.setenv("CENTRAL_WORKER_ONCE_ENABLED", "YES")
    monkeypatch.setenv("CENTRAL_TASK_DB", str(db))
    monkeypatch.setenv("CENTRAL_WORKER_AGENT", "ci-audit-worker")
    main()
    assert "ANALYSIS_COMPLETED" in capsys.readouterr().out
    assert PersistentTaskBridge(db).status(task["task_id"])["status"] == "analyzed"
    main()
    assert "NO_ELIGIBLE_TASK" in capsys.readouterr().out
