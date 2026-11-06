"""AI-27 integrated review -> candidate -> verifier; no Docker in unit test."""
import json
import pytest
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch
from central_ai.verified_review_pipeline import prepare_and_verify


@pytest.mark.parametrize("generated", [True, False])
@pytest.mark.parametrize("passed", [True, False])
def test_full_process_preserves_source_and_refuses_deploy(tmp_path, passed, generated):
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
    recommendation="```python\ndef candidate():\n    return 3\n```"
    from test_ai26_verified_review_pipeline import generation_admission_fixture
    extra = {'generator':lambda request:recommendation, 'generator_id':'ci-synthetic',
             'generation_authorization_check':generation_admission_fixture} if generated else {'recommendation':recommendation}
    report=prepare_and_verify(
        enabled="YES",database=str(db),task_id=task["task_id"],
        handoffs=paths[0],proposals=paths[1],candidates=paths[2],
        trusted_test_file="/isolated/operator_test.py",trusted_test_sha256="b"*64,
        image="python@sha256:"+"a"*64,authorization_check=authorize,verifier=verifier,**extra)
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


@pytest.mark.parametrize('backend', ['injected', 'docker'])
@pytest.mark.parametrize('mode', ['timeout', 'quarantine', 'crash'])
def test_process_recovery_preserves_admission_boundary(tmp_path, backend, mode):
    """Same bounded lifecycle locally and in opt-in disposable Docker CI."""
    import ast
    import hashlib
    import multiprocessing
    import os
    from pathlib import Path
    import re
    import shutil
    import subprocess
    from functools import partial
    from types import SimpleNamespace
    from central_ai.isolated_functional_verifier import run_functional_tests
    from central_ai.task_storage import TaskStorage
    image = os.environ.get('CENTRAL_AI_TEST_DOCKER_IMAGE') if backend == 'docker' else 'python@sha256:'+'a'*64
    if not image:
        pytest.skip('real Docker recovery requires explicit disposable CI image')
    db = tmp_path/'tasks.sqlite'
    source = tmp_path/'source'; source.mkdir()
    original = source/'sample.py'; original.write_text('def f(): return 1\n')
    original_bytes = original.read_bytes()
    bridge = PersistentTaskBridge(db)
    registry = TaskFileTargets(db); registry.initialize()
    tasks = [bridge.submit('Synthetic process recovery fixture')['task_id'] for _ in range(2)]
    for task_id in tasks:
        registry.register(task_id, str(source), 'sample.py')
    assert run_batch(enabled='YES', database=str(db), agent='ci-recovery', max_tasks=2,
                     idle_checks=1, sleep=lambda _:None)['processed'] == 2
    paths = []
    for name in ('handoffs', 'proposals', 'candidates'):
        path = tmp_path/name; path.mkdir(mode=0o700); paths.append(str(path))
    test = tmp_path/'test_candidate.py'
    test.write_text('import time\ntime.sleep(30)\n' if mode == 'timeout' else
                    "import sys\nsys.path.insert(0, '/sandbox')\nfrom candidate import f\nassert f() == 2\n")
    params = dict(enabled='YES', database=str(db), task_id=tasks[0], handoffs=paths[0],
        proposals=paths[1], candidates=paths[2], recommendation='```python\ndef f(): return 2\n```',
        trusted_test_file=str(test), trusted_test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(), image=image)
    def authorize(binding):
        return dict(verification_authorized=True, binding=dict(binding), reviewer_id='ci-synthetic-recovery',
                    authorization_id='ci-only', approved=False, deployment_allowed=False)
    def verify_in_child():
        def runner(args, **kwargs):
            if args[1] == 'run':
                audit = TaskStorage(db).get(tasks[0])['verification']
                assert audit['resources']['container_name'] == args[3]
                if backend == 'docker':
                    result = subprocess.run(args, **kwargs)
                elif mode == 'timeout':
                    raise subprocess.TimeoutExpired('synthetic-docker', 5)
                else:
                    root = Path(audit['resources']['snapshot_directory'])
                    record = ast.parse((root/'harness.py').read_text()).body[-1].value.args[1].value.decode()
                    result = SimpleNamespace(returncode=0, stdout=record)
                if mode == 'crash':
                    os._exit(17)  # After real/synthetic container exit, before cleanup/outcome.
                return result
            if mode == 'quarantine':
                # Explicit fault injection: unavailable observation, not a real daemon outage.
                return SimpleNamespace(returncode=1, stdout='')
            return subprocess.run(args, **kwargs) if backend == 'docker' else SimpleNamespace(returncode=0, stdout='')
        report = prepare_and_verify(**params, authorization_check=authorize,
                                   verifier=partial(run_functional_tests, timeout=5, run=runner))
        (tmp_path/'report.json').write_text(json.dumps(report))
    child = multiprocessing.get_context('fork').Process(target=verify_in_child)
    child.start()
    try:
        child.join(timeout=45)
        if child.is_alive():
            child.terminate(); child.join(timeout=5)
            pytest.fail('bounded recovery child exceeded timeout')
        assert child.exitcode == (17 if mode == 'crash' else 0)
        store = TaskStorage(db)  # Reopen after the verification process has exited.
        task = store.get(tasks[0]); audit = task['verification']
        assert audit['phase'] == {'timeout':'completed', 'quarantine':'quarantined', 'crash':'running'}[mode]
        assert task['status'] == 'analyzed'
        assert audit['approved'] is audit['deployment_allowed'] is False
        assert audit['binding']['test_sha256'] == params['trusted_test_sha256']
        root = Path(audit['resources']['snapshot_directory'])
        assert root.exists() is (mode != 'timeout')
        if mode == 'crash':
            assert 'outcome' not in audit and not (tmp_path/'report.json').exists()
        else:
            outcome = audit['outcome']
            assert outcome['test_status'] == ('timeout' if mode == 'timeout' else 'cleanup_unconfirmed')
            assert outcome['tests_passed'] is outcome['completion_confirmed'] is False
            assert outcome['approved'] is outcome['deployment_allowed'] is False
        with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
            prepare_and_verify(**params, authorization_check=lambda _:pytest.fail('must not reauthorize'),
                               verifier=lambda **_:pytest.fail('must not execute again'))
        if mode == 'timeout':
            store.begin_verification(tasks[1], 'b'*32)  # Confirmed cleanup does not block other tasks.
        else:
            with pytest.raises(ValueError, match='VERIFICATION_DATABASE_BLOCKED'):
                store.begin_verification(tasks[1], 'b'*32)
        assert original.read_bytes() == original_bytes
    finally:
        if child.is_alive():
            child.terminate(); child.join(timeout=5)
        audit = TaskStorage(db).get(tasks[0]).get('verification', {})
        handles = audit.get('resources')
        if handles:
            name = handles['container_name']
            assert re.fullmatch(r'central-ai-verifier-[0-9a-f]{32}', name)
            if backend == 'docker':
                query = ['docker','container','ls','--all','--filter','name=^/'+name+'$','--format','{{.Names}}']
                check = subprocess.run(query, capture_output=True, text=True, timeout=10, check=True)
                if check.stdout.strip():
                    subprocess.run(['docker','rm','-f',name], capture_output=True, timeout=10, check=True)
                assert subprocess.run(query, capture_output=True, text=True, timeout=10, check=True).stdout == ''
            # Explicit fixture-owner reconciliation, only after independent absence.
            root = Path(handles['snapshot_directory'])
            if root.exists():
                shutil.rmtree(root)
            assert TaskStorage(db).get(tasks[0])['verification']['phase'] == audit['phase']
            # Manual resource cleanup never clears a durable quarantine/running intent.


def revision_fixture(monkeypatch, tmp_path):
    from test_ai26_verified_review_pipeline import verification_fixture, valid_result
    params = verification_fixture(monkeypatch, valid_result(passed=False,status='failed',returncode=1), tmp_path)
    report = prepare_and_verify(**params)
    return params, report


def test_revision_family_budget_survives_reopen_and_new_task_ids(monkeypatch, tmp_path):
    params, report = revision_fixture(monkeypatch, tmp_path)
    root = params['task_id']
    for ordinal in (2,3):
        child = PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])
        assert child['revision']['ordinal'] == ordinal and child['revision']['root_task_id'] == root
        assert run_batch(enabled='YES',database=params['database'],agent='revision-test',max_tasks=1,
                         idle_checks=1,sleep=lambda _:None)['processed'] == 1
        params['task_id'] = child['task_id']
        report = prepare_and_verify(**params)
    with pytest.raises(ValueError,match='REVISION_BUDGET_EXHAUSTED'):
        PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])
    family = PersistentTaskBridge(params['database']).status(root)['revision_family']
    assert len(family['members']) == 3


def test_revision_claim_race_has_one_winner(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    params, report = revision_fixture(monkeypatch, tmp_path)
    def claim(_):
        try:
            return PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])
        except ValueError as error:
            assert str(error) == 'REVISION_FAMILY_CONFLICT'
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(x is not None for x in pool.map(claim,range(2))) == 1


def test_revision_reservation_rolls_back_with_queue_failure(monkeypatch, tmp_path):
    from central_ai.task_queue import TaskQueue
    params, report = revision_fixture(monkeypatch, tmp_path)
    def fail(*args,**kwargs): raise OSError('synthetic write failure')
    with monkeypatch.context() as context:
        context.setattr(TaskQueue,'enqueue',fail)
        with pytest.raises(OSError):
            PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])
    bridge=PersistentTaskBridge(params['database'])
    assert len(bridge.list_tasks()) == 1 and 'revision_family' not in bridge.status(params['task_id'])
    assert bridge.submit_revision(params['task_id'],report['verification_nonce'])['revision']['ordinal'] == 2


@pytest.mark.parametrize('change',['source','tests'])
def test_revision_cannot_change_source_or_trusted_tests(monkeypatch,tmp_path,change):
    params, report=revision_fixture(monkeypatch,tmp_path)
    child=PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])
    if change=='source': (tmp_path/'source'/'sample.py').write_text('def changed(): return 99\n')
    run_batch(enabled='YES',database=params['database'],agent='revision-test',max_tasks=1,idle_checks=1,sleep=lambda _:None)
    params['task_id']=child['task_id']
    if change=='tests': params['trusted_test_sha256']='d'*64
    with pytest.raises(ValueError,match='REVISION_SOURCE_CHANGED|REVISION_TESTS_CHANGED'):
        prepare_and_verify(**params)


@pytest.mark.parametrize('status',['passed','timeout','completion_unconfirmed'])
def test_only_completed_semantic_failure_can_reserve_revision(monkeypatch,tmp_path,status):
    from test_ai26_verified_review_pipeline import verification_fixture, valid_result
    result=valid_result(status=status,passed=status=='passed',returncode=0)
    params=verification_fixture(monkeypatch,result,tmp_path)
    report=prepare_and_verify(**params)
    with pytest.raises(ValueError,match='REVISION_PARENT_NOT_ELIGIBLE'):
        PersistentTaskBridge(params['database']).submit_revision(params['task_id'],report['verification_nonce'])


@pytest.mark.parametrize('change',['child_spec','root_source'])
def test_generated_revision_rejects_corrupted_root_context_before_dispatch(monkeypatch,tmp_path,change):
    import json
    import sqlite3
    params,report=revision_fixture(monkeypatch,tmp_path)
    root=params['task_id']
    child=PersistentTaskBridge(params['database']).submit_revision(root,report['verification_nonce'])
    run_batch(enabled='YES',database=params['database'],agent='negative-revision',max_tasks=1,
              idle_checks=1,sleep=lambda _:None)
    victim=child['task_id'] if change=='child_spec' else root
    with sqlite3.connect(params['database']) as conn:
        task=json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?',(victim,)).fetchone()[0])
        if change=='child_spec': task['task']['task']='Synthetic unrelated task substitution'
        else: task['analysis']['source_sha256']='f'*64
        conn.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(task),victim))
    params.update(task_id=child['task_id']);params.pop('recommendation')
    calls=[]
    with pytest.raises(ValueError,match='GENERATION_FAMILY_CONFLICT'):
        prepare_and_verify(**params,generator=lambda request:calls.append(request) or '```python\ndef f(): return 2\n```',
                           generator_id='ci-synthetic')
    assert calls==[]


@pytest.mark.parametrize('commit_happened',[False,True])
def test_revision_commit_uncertainty_clears_transient_registry(monkeypatch,tmp_path,commit_happened):
    from contextlib import contextmanager
    params,report=revision_fixture(monkeypatch,tmp_path)
    bridge=PersistentTaskBridge(params['database'])
    original_connect=bridge.storage._connect
    @contextmanager
    def uncertain_connection():
        connection=original_connect()
        try:
            yield connection
            if commit_happened: connection.commit()
            else: connection.rollback()
            raise OSError('synthetic commit uncertainty')
        finally:
            connection.close()
    monkeypatch.setattr(bridge.storage,'_connect',uncertain_connection)
    with pytest.raises(OSError,match='commit uncertainty'):
        bridge.submit_revision(params['task_id'],report['verification_nonce'])
    assert bridge.bridge.registry=={}
    reopened=PersistentTaskBridge(params['database'])
    tasks=reopened.list_tasks()
    assert len(tasks)==(2 if commit_happened else 1)
    if commit_happened:
        with pytest.raises(ValueError,match='REVISION_FAMILY_CONFLICT'):
            reopened.submit_revision(params['task_id'],report['verification_nonce'])
    else:
        assert 'revision_family' not in reopened.status(params['task_id'])
