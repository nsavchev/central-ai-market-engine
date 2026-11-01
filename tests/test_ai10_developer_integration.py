"""AI-10: persistent bridge -> existing target registry -> bounded Developer Agent.

No LLM calls, code writes, deployment, broker access or second task queue.
"""
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch


def test_registered_tasks_complete_after_process_boundary(tmp_path):
    db = tmp_path / "tasks.sqlite"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for i in range(2):
        (workspace / f"sample{i}.py").write_text(
            f"def sample_{i}():\n    return {i}\n"
        )
    bridge = PersistentTaskBridge(db)
    registry = TaskFileTargets(db)
    registry.initialize()
    ids = []
    for i in range(2):
        task = bridge.submit(f"Read only sample{i}.py")
        ids.append(task["task_id"])
        registry.register(task["task_id"], str(workspace), f"sample{i}.py")
    # A submitted task without a registered source target must not execute.
    unregistered = bridge.submit("Unregistered task must remain unprocessed")
    original = [(workspace / f"sample{i}.py").read_bytes() for i in range(2)]

    result = run_batch(
        enabled="YES",
        database=str(db),
        agent="ai10-test-agent",
        max_tasks=2,
        idle_checks=1,
        sleep=lambda _: None,
    )
    assert result["processed"] == 2
    reopened = PersistentTaskBridge(db)
    for i, task_id in enumerate(ids):
        task = reopened.status(task_id)
        assert task["status"] == "analyzed"
        assert f"sample_{i}" in task["analysis"]["functions"]
        overview = reopened.task_overview(task_id)
        assert overview["approved"] is False
        assert overview["deployment_allowed"] is False
        assert overview["requires_attention"] is False
        assert (workspace / f"sample{i}.py").read_bytes() == original[i]

    assert reopened.status(unregistered["task_id"])["status"] == "planned"
    assert reopened.task_overview(unregistered["task_id"])["approved"] is False
    assert run_batch(
        enabled="YES", database=str(db), agent="ai10-test-agent",
        max_tasks=2, idle_checks=1, sleep=lambda _: None,
    )["processed"] == 0


def test_batch_is_denied_without_opt_in(tmp_path):
    try:
        run_batch(
            enabled="", database=str(tmp_path / "missing.sqlite"),
            agent="ai10-test-agent", sleep=lambda _: None,
        )
    except ValueError as exc:
        assert str(exc) == "WORKER_DISABLED"
    else:
        raise AssertionError("worker must deny unapproved execution")
