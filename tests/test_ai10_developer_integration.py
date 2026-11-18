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


def test_analysis_and_handoff_preserve_exact_source_digest_after_reopen(tmp_path):
    import hashlib
    import json
    from central_ai.review_handoff import create_review_handoff
    db = tmp_path/'tasks.sqlite'
    source = tmp_path/'source'; source.mkdir()
    file = source/'sample.py'
    content = b'def sample():\r\n    return 1\r\n'
    file.write_bytes(content)
    task_id = PersistentTaskBridge(db).submit('Synthetic source provenance')['task_id']
    targets = TaskFileTargets(db); targets.initialize()
    targets.register(task_id, str(source), 'sample.py')
    assert run_batch(enabled='YES', database=str(db), agent='ci-source-digest', max_tasks=1,
                     idle_checks=1, sleep=lambda _:None)['processed'] == 1
    file.write_bytes(b'def replacement(): return 2\n')
    saved = PersistentTaskBridge(db).status(task_id)
    expected = hashlib.sha256(content).hexdigest()
    assert saved['analysis']['source_sha256'] == expected
    assert saved['analysis']['functions'] == ['sample']
    directory = tmp_path/'handoffs'; directory.mkdir(mode=0o700)
    handoff = create_review_handoff(enabled='YES', database=str(db), task_id=task_id,
                                  output_directory=str(directory))
    from pathlib import Path
    payload = json.loads(Path(handoff['path']).read_text())
    assert payload['analysis']['source_sha256'] == expected
    assert payload['approved'] is payload['deployment_allowed'] is False
    assert hashlib.sha256(file.read_bytes()).hexdigest() != expected


def test_analyzer_hashes_same_bytes_as_ast_when_path_changes(tmp_path, monkeypatch):
    import hashlib
    import central_ai.read_only_analyzer as analyzer
    path = tmp_path/'sample.py'
    original = b'def original(): return 1\n'
    path.write_bytes(original)
    parse = analyzer.ast.parse
    def replace_after_read(source, **kwargs):
        path.write_bytes(b'def replaced(): return 2\n')
        return parse(source, **kwargs)
    from types import SimpleNamespace
    monkeypatch.setattr(analyzer, 'ast', SimpleNamespace(parse=replace_after_read,
        walk=analyzer.ast.walk, ClassDef=analyzer.ast.ClassDef,
        FunctionDef=analyzer.ast.FunctionDef, AsyncFunctionDef=analyzer.ast.AsyncFunctionDef))
    result = analyzer.ReadOnlyAnalyzer(tmp_path).analyze('sample.py')
    assert result['functions'] == ['original']
    assert result['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert result['source_sha256'] != hashlib.sha256(path.read_bytes()).hexdigest()
