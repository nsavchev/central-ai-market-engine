"""AI-27 integrated review -> candidate -> verifier; no Docker in unit test."""
import json
import pytest
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch
from central_ai.verified_review_pipeline import prepare_and_verify


@pytest.mark.parametrize("passed", [True, False])
def test_full_process_preserves_source_and_refuses_deploy(tmp_path, passed):
    db=tmp_path/"tasks.sqlite"
    source=tmp_path/"source"
    source.mkdir()
    file=source/"original.py"
    file.write_text("def original():\n    return 2\n")
    untouched=file.read_bytes()
    bridge=PersistentTaskBridge(db)
    task=bridge.submit("Inspect original.py")
    registry=TaskFileTargets(db)
    registry.initialize()
    registry.register(task["task_id"],str(source),"original.py")
    assert run_batch(enabled="YES",database=str(db),agent="ai27-test",max_tasks=1,idle_checks=1,sleep=lambda _:None)["processed"]==1
    paths=[]
    for name in ("handoffs","proposals","candidates"):
        directory=tmp_path/name
        directory.mkdir(mode=0o700)
        paths.append(str(directory))
    def verifier(**kwargs):
        kwargs['record_resources']({'snapshot_directory':'/tmp/central-ai-input-ci-fixture',
                                    'container_name':'central-ai-verifier-'+'f'*32})
        assert kwargs["enabled"]=="YES"
        assert kwargs["candidate"].endswith(".py")
        assert kwargs["expected_test_sha256"]=="b"*64
        assert kwargs["expected_sha256"]
        return {"passed": passed, "status":"passed" if passed else "failed",
                "executed_candidate":True,"returncode":0 if passed else 1,
                "execution_policy":"bounded-arithmetic-v1","completion_confirmed":passed,
                "test_sha256":kwargs["expected_test_sha256"]}
    def authorize(binding):
        assert binding["task_id"]==task["task_id"]
        assert binding["scope"]=="verify_only"
        return {"verification_authorized":True,"binding":binding,
                "reviewer_id":"ci-trusted-review-fixture","authorization_id":"ci-only",
                "approved":False,"deployment_allowed":False}
    report=prepare_and_verify(
        enabled="YES",database=str(db),task_id=task["task_id"],
        handoffs=paths[0],proposals=paths[1],candidates=paths[2],
        recommendation="```python\ndef candidate():\n    return 3\n```",
        trusted_test_file="/isolated/operator_test.py",trusted_test_sha256="b"*64,
        image="python@sha256:"+"a"*64,authorization_check=authorize,verifier=verifier)
    assert report["tests_passed"] is passed
    assert report["approved"] is False and report["deployment_allowed"] is False
    assert file.read_bytes()==untouched
    assert PersistentTaskBridge(db).status(task["task_id"])["status"]=="analyzed"


@pytest.mark.parametrize('mode', ['passed', 'failed', 'timeout', 'quarantine', 'record_failure'])
def test_existing_pipeline_low_level_verifier_and_journal_together(tmp_path, monkeypatch, mode):
    from functools import partial
    from hashlib import sha256
    from pathlib import Path
    from types import SimpleNamespace
    import shutil
    import subprocess
    from central_ai.isolated_functional_verifier import run_functional_tests
    from central_ai.task_storage import TaskStorage
    db = tmp_path/'tasks.sqlite'
    source = tmp_path/'source'
    source.mkdir()
    original = source/'sample.py'
    original.write_text('def f(): return 1\n')
    before = original.read_bytes()
    task_id = PersistentTaskBridge(db).submit('Synthetic isolated lifecycle')['task_id']
    registry = TaskFileTargets(db)
    registry.initialize()
    registry.register(task_id, str(source), 'sample.py')
    assert run_batch(enabled='YES', database=str(db), agent='ci-lifecycle', max_tasks=1,
                     idle_checks=1, sleep=lambda _:None)['processed'] == 1
    directories = []
    for name in ('handoffs', 'proposals', 'candidates'):
        path = tmp_path/name
        path.mkdir(mode=0o700)
        directories.append(str(path))
    test = tmp_path/'test_candidate.py'
    test.write_text('assert 1 == 1\n')
    commands = []
    handles = []
    def runner(args, **kwargs):
        commands.append(args)
        if args[1] == 'run':
            audit = TaskStorage(db).get(task_id)['verification']
            assert audit['phase'] == 'running'
            assert audit['resources']['container_name'] == args[3]
            root = Path(audit['resources']['snapshot_directory'])
            assert root.is_dir()
            handles.append(root)
            if mode == 'timeout':
                raise subprocess.TimeoutExpired('docker', 30)
            import ast
            record = ast.parse((root/'harness.py').read_text()).body[-1].value.args[1].value.decode()
            return SimpleNamespace(returncode=1 if mode == 'failed' else 0, stdout=record)
        return SimpleNamespace(returncode=1 if mode == 'quarantine' else 0, stdout='')
    def authorize(binding):
        return dict(verification_authorized=True, binding=dict(binding), reviewer_id='ci-synthetic',
                    authorization_id='ci-only', approved=False, deployment_allowed=False)
    if mode == 'record_failure':
        def fail(*args, **kwargs):
            raise OSError('synthetic audit unavailable')
        monkeypatch.setattr(TaskStorage, 'record_verification_resources', fail)
    params = dict(enabled='YES', database=str(db), task_id=task_id, handoffs=directories[0],
        proposals=directories[1], candidates=directories[2], recommendation='```python\ndef f(): return 2\n```',
        trusted_test_file=str(test), trusted_test_sha256=sha256(test.read_bytes()).hexdigest(),
        image='python@sha256:'+'a'*64, authorization_check=authorize,
        verifier=partial(run_functional_tests, run=runner))
    if mode == 'record_failure':
        with pytest.raises(OSError, match='synthetic audit'):
            prepare_and_verify(**params)
        assert commands == []
        assert TaskStorage(db).get(task_id)['verification']['phase'] == 'quarantined'
        return
    try:
        report = prepare_and_verify(**params)
        audit = TaskStorage(db).get(task_id)['verification']
        assert report['test_status'] == ('cleanup_unconfirmed' if mode == 'quarantine' else mode)
        assert audit['phase'] == ('quarantined' if mode == 'quarantine' else 'completed')
        assert report['tests_passed'] is (mode == 'passed')
        assert report['approved'] is report['deployment_allowed'] is False
        assert handles[0].exists() is (mode == 'quarantine')
        assert original.read_bytes() == before
        assert TaskStorage(db).get(task_id)['status'] == 'analyzed'
    finally:
        for root in handles:
            if root.exists():
                shutil.rmtree(root)  # Only synthetic, test-owned retained snapshots.
