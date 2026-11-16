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


def correction_context_fixture(monkeypatch, tmp_path, *, call_limit=100, runner_factory=None, image=None):
    """Real persisted pipeline/HTTP adapter; static code and HTTP are test fixtures.

    This intentionally is not a rootless Docker or real-provider acceptance.
    """
    import hashlib
    import httpx
    from pathlib import Path
    from central_ai.app import make_openai_generator
    from central_ai.isolated_functional_verifier import _validate_bounded_candidate
    from test_ai26_verified_review_pipeline import generation_admission_fixture
    db = tmp_path / 'tasks.sqlite'
    source = tmp_path / 'source'
    source.mkdir(mode=0o700)
    original = source / 'relative.py'
    wrong = 'def relative_performance_pp(asset_return, benchmark_return):\n    return asset_return + benchmark_return\n'
    correct = wrong.replace(' + ', ' - ')
    original.write_text(wrong)
    original.chmod(0o600)
    bridge = PersistentTaskBridge(db)
    root = bridge.submit('Implement relative_performance_pp(asset_return, benchmark_return): '
        'subtract benchmark percentage return from asset percentage return, yielding percentage points. '
        'Return one Python code block with a single arithmetic function; no imports or calls.')['task_id']
    targets = TaskFileTargets(db)
    targets.initialize()
    targets.register(root, str(source), original.name)
    run_batch(enabled='YES', database=str(db), agent='ci-correction-root', max_tasks=1, idle_checks=1, sleep=lambda _: None)
    paths = {}
    for name in ('handoffs', 'proposals', 'candidates'):
        directory = tmp_path / name
        directory.mkdir(mode=0o700)
        paths[name] = str(directory)
    test = tmp_path / 'independent_test.py'
    constraints = ''
    if runner_factory is not None:
        constraints = '''import sys, os
from pathlib import Path
sys.path.insert(0, '/sandbox')
from candidate import relative_performance_pp
assert os.getuid() == os.geteuid() == 65534
status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert all(int(status[k].strip(), 16) == 0 for k in ('CapEff', 'CapPrm', 'CapAmb'))
assert status['NoNewPrivs'].strip() == '1'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '134217728'
assert Path('/sys/fs/cgroup/pids.max').read_text().strip() == '32'
quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
assert int(quota) * 2 == int(period)
assert not any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:])
assert not os.environ.get('OPENAI_API_KEY')
try:
    Path('/forbidden-root-write').write_text('forbidden')
except OSError as error:
    assert error.errno == 30
else:
    raise AssertionError('root filesystem writable')
'''
    test.write_text(constraints + 'assert abs(relative_performance_pp(5, 2) - 3) < 1e-9\n'
        'assert abs(relative_performance_pp(-5, 2) + 7) < 1e-9\n'
        'assert abs(relative_performance_pp(5, -2) - 7) < 1e-9\n')
    test.chmod(0o600)
    test_sha = hashlib.sha256(test.read_bytes()).hexdigest()
    seen = []
    def transport(request):
        body = json.loads(request.content)
        seen.append(body)
        answer = wrong if len(seen) == 1 else correct
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(
            {'choices': [{'message': {'content': '```python\n' + answer + '```'}}]}).encode()))
    monkeypatch.setenv('OPENAI_API_KEY', 'ci-secret-not-real')
    generator = make_openai_generator(enabled='YES', database=str(db), transport=httpx.MockTransport(transport))
    def authorize(binding):
        return dict(verification_authorized=True, binding=dict(binding), reviewer_id='ci-independent-review',
                    authorization_id='ci-review-' + binding['nonce'], approved=False, deployment_allowed=False)
    if runner_factory is not None:
        import hmac
        import secrets
        from central_ai.verifier_gate import make_hmac_review_authorizer
        key = secrets.token_bytes(32)  # Ephemeral synthetic acceptance identity only.
        def issue(binding):
            receipt = dict(schema='review-hmac-sha256-v1', binding=dict(binding),
                reviewer_id='ci-independent-review', authorization_id='ci-review-' + binding['nonce'],
                issued_at=1000, expires_at=1100, verification_authorized=True,
                approved=False, deployment_allowed=False)
            raw = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            return dict(receipt, mac=hmac.new(key, raw, 'sha256').hexdigest())
        authorize = make_hmac_review_authorizer(reviewer_keys={'ci-independent-review': key},
            request_receipt=issue, clock=lambda: 1050)
    def verifier(**kwargs):
        if runner_factory is not None:
            from central_ai.isolated_functional_verifier import run_functional_tests
            return run_functional_tests(**kwargs, run=runner_factory())
        kwargs['record_resources'](dict(snapshot_directory='/tmp/central-ai-input-ci-correction',
            container_name='central-ai-verifier-' + 'c' * 32))
        raw = Path(kwargs['candidate']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == kwargs['expected_sha256']
        assert hashlib.sha256(test.read_bytes()).hexdigest() == kwargs['expected_test_sha256']
        _validate_bounded_candidate(raw)
        # Execute only these authored, bounded arithmetic fixtures in this unit test.
        namespace = {'__builtins__': {'abs': abs}}
        exec(compile(raw, '<static-test-candidate>', 'exec'), namespace)
        passed = True
        try:
            exec(compile(test.read_bytes(), '<trusted-test>', 'exec'), namespace)
        except AssertionError:
            passed = False
        return dict(status='passed' if passed else 'failed', passed=passed,
            executed_candidate=True, completion_confirmed=passed, execution_policy='bounded-arithmetic-v1',
            returncode=0 if passed else 1, test_sha256=test_sha)
    def base_admit(binding):
        if runner_factory is not None:
            runner_factory()  # Recheck host/daemon/image before reservation or HTTP.
        receipt = generation_admission_fixture(binding)
        receipt['budget_call_limit'] = call_limit
        return receipt
    params = dict(enabled='YES', database=str(db), task_id=root, **paths,
        trusted_test_file=str(test), trusted_test_sha256=test_sha, image=image or 'python@sha256:' + 'a' * 64,
        authorization_check=authorize, verifier=verifier, generator=generator,
        generator_id=generator.generator_id, generation_authorization_check=base_admit)
    report = prepare_and_verify(**params)
    assert report['test_status'] == 'failed'
    parent_candidate = tmp_path / 'candidates' / ('candidate_' + root + '.py')
    child = bridge.submit_revision(root, report['verification_nonce'])['task_id']
    run_batch(enabled='YES', database=str(db), agent='ci-correction-child', max_tasks=1, idle_checks=1, sleep=lambda _: None)
    params.update(task_id=child, revision_candidate_file=str(parent_candidate))
    def admit(binding):
        receipt = base_admit(binding)
        receipt['disclosure'] = 'task_description_and_parent_candidate'
        return receipt
    params['generation_authorization_check'] = admit
    return params, root, seen, original, wrong


def test_correction_context_drives_fail_to_pass_and_hashes_actual_prompt(monkeypatch, tmp_path):
    import hashlib
    from central_ai.task_storage import TaskStorage
    params, root, seen, original, wrong = correction_context_fixture(monkeypatch, tmp_path)
    report = prepare_and_verify(**params)
    assert report['tests_passed'] and not report['approved'] and not report['deployment_allowed']
    assert len(seen) == 2
    prompt = seen[1]['messages'][-1]['content']
    assert 'previous candidate failed' in prompt and 'candidate_code' in prompt
    assert 'asset_return + benchmark_return' in prompt
    assert 'independent_test.py' not in prompt and 'ci-secret-not-real' not in prompt
    saved = TaskStorage(params['database']).get(params['task_id'])['generation']
    assert saved['dispatch']['prompt_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
    assert saved['dispatch']['prompt_sha256'] != saved['binding']['spec_sha256']
    assert 'candidate_code' not in json.dumps(saved) and wrong not in json.dumps(saved)
    assert TaskStorage(params['database']).get(root)['verification']['outcome']['test_status'] == 'failed'
    assert original.read_text() == wrong


def test_correction_fixture_inputs_remain_trusted_with_group_writable_umask(monkeypatch, tmp_path):
    import os
    from pathlib import Path
    from central_ai.isolated_functional_verifier import _read_input
    previous = os.umask(0o002)
    try:
        params, _, _, original, wrong = correction_context_fixture(monkeypatch, tmp_path)
    finally:
        os.umask(previous)
    assert _read_input(original).decode() == wrong
    assert _read_input(Path(params['trusted_test_file']))


@pytest.mark.parametrize('failure', ['missing', 'wrong_code', 'old_disclosure', 'context_tamper', 'parent_tamper', 'lineage_tamper', 'code_tamper'])
def test_correction_context_rejects_mismatch_before_second_http(monkeypatch, tmp_path, failure):
    import sqlite3
    from pathlib import Path
    from central_ai.task_storage import TaskStorage
    from test_ai26_verified_review_pipeline import generation_admission_fixture
    params, root, seen, _, _ = correction_context_fixture(monkeypatch, tmp_path)
    if failure == 'missing':
        params.pop('revision_candidate_file')
    elif failure == 'wrong_code':
        wrong = tmp_path / 'substitution.py'
        wrong.write_text('def other(): return 1\n')
        params['revision_candidate_file'] = str(wrong)
    elif failure == 'old_disclosure':
        params['generation_authorization_check'] = generation_admission_fixture
    else:
        original = params['generator']
        def tamper(request):
            if failure == 'context_tamper':
                request['revision_context']['test_status'] = 'passed'
            elif failure == 'code_tamper':
                request['revision_context']['candidate_code'] += '\n'
            else:
                with sqlite3.connect(params['database']) as conn:
                    victim = params['task_id'] if failure == 'lineage_tamper' else root
                    task = json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?', (victim,)).fetchone()[0])
                    if failure == 'lineage_tamper': task['revision']['ordinal'] = 3
                    else: task['verification']['nonce'] = 'f' * 32
                    conn.execute('UPDATE tasks SET payload=? WHERE task_id=?', (json.dumps(task), victim))
            return original(request)
        params['generator'] = tamper
    with pytest.raises(ValueError):
        prepare_and_verify(**params)
    assert len(seen) == 1
    saved = TaskStorage(params['database']).get(params['task_id'])
    assert saved['verification']['phase'] == 'blocked'
    assert 'dispatch' not in saved.get('generation', {})
    if failure in ('missing', 'wrong_code', 'old_disclosure'):
        assert 'admission' not in saved.get('generation', {})


def test_correction_context_does_not_create_another_paid_call_allowance(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params, root, seen, _, _ = correction_context_fixture(monkeypatch, tmp_path, call_limit=1)
    with pytest.raises(ValueError, match='GENERATION_CALL_BUDGET_EXHAUSTED'):
        prepare_and_verify(**params)
    assert len(seen) == 1
    assert 'admission' not in TaskStorage(params['database']).get(params['task_id'])['generation']
    assert TaskStorage(params['database']).get(root)['generation']['admission']['receipt']['budget_call_limit'] == 1


def test_correction_context_changed_after_http_is_blocked_without_retry(monkeypatch, tmp_path):
    import sqlite3
    from central_ai.task_storage import TaskStorage
    params, root, seen, _, _ = correction_context_fixture(monkeypatch, tmp_path)
    original = params['generator']
    def change_after_dispatch(request):
        response = original(request)
        with sqlite3.connect(params['database']) as conn:
            task = json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?', (root,)).fetchone()[0])
            task['verification']['nonce'] = 'f' * 32
            conn.execute('UPDATE tasks SET payload=? WHERE task_id=?', (json.dumps(task), root))
        return response
    params['generator'] = change_after_dispatch
    with pytest.raises(ValueError, match='REVISION_CONTEXT_INVALID'):
        prepare_and_verify(**params)
    saved = TaskStorage(params['database']).get(params['task_id'])
    assert 'dispatch' in saved['generation'] and saved['generation']['phase'] == 'requested'
    assert saved['verification']['phase'] == 'blocked' and len(seen) == 2
    with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params)
    assert len(seen) == 2


def test_real_rootless_bound_correction_context(monkeypatch, tmp_path):
    """Opt-in real private daemon; model responses and host allowance are synthetic."""
    import hashlib
    import os
    from pathlib import Path
    from central_ai.isolated_functional_verifier import make_isolated_docker_runner
    from central_ai.task_storage import TaskStorage
    runner_file = os.environ.get('CENTRAL_AI_ROOTLESS_CI_POLICY')
    if not runner_file:
        pytest.skip('requires intended nonroot/private rootless daemon')
    policy = json.loads(Path(runner_file).read_text())
    image = os.environ['CENTRAL_AI_ROOTLESS_CI_IMAGE']
    def checked():
        return make_isolated_docker_runner(policy, [image])
    checked()  # No host or verifier guard is replaced in this acceptance.
    def containers():
        result = checked()(['docker', 'container', 'ls', '--all', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0
        return set(result.stdout.splitlines())
    before = containers()
    params, root, seen, original, wrong = correction_context_fixture(monkeypatch, tmp_path,
        call_limit=2, runner_factory=checked, image=image)
    test = Path(params['trusted_test_file'])
    test_before = test.read_bytes()
    result = prepare_and_verify(**params)
    assert result['test_status'] == 'passed' and result['completion_confirmed']
    assert not result['approved'] and not result['deployment_allowed']
    store = TaskStorage(params['database'])
    first = store.get(root)
    second = store.get(params['task_id'])
    assert first['verification']['outcome']['test_status'] == 'failed'
    assert second['verification']['outcome']['test_status'] == 'passed'
    assert second['generation']['binding']['schema'] == 'generation-request-v2'
    prompt = seen[1]['messages'][-1]['content']
    assert hashlib.sha256(prompt.encode()).hexdigest() == second['generation']['dispatch']['prompt_sha256']
    assert len(seen) == 2 and original.read_text() == wrong and test.read_bytes() == test_before
    assert first['revision_family']['members'] == [root, params['task_id']]
    assert first['generation']['admission']['receipt']['budget_call_limit'] == 2
    for record in (first, second):
        assert record['verification']['phase'] == 'completed'
        assert not Path(record['verification']['resources']['snapshot_directory']).exists()
    assert containers() == before
    with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params)
    with pytest.raises(ValueError, match='REVISION_PARENT_NOT_ELIGIBLE'):
        PersistentTaskBridge(params['database']).submit_revision(params['task_id'], result['verification_nonce'])
    assert len(seen) == 2 and containers() == before
    print('ROOTLESS_BOUND_CORRECTION_CONTEXT_PASSED')
    print(json.dumps(dict(provider='mock', root='failed', correction='passed',
        callbacks=2, cleanup_confirmed=True, promotion_allowed=False)))


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
