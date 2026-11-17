import hashlib
import json
import subprocess
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
import pytest

from central_ai.isolated_functional_verifier import run_functional_tests

IMAGE="python@sha256:"+"a"*64


def json_function_fixture(tmp_path):
    candidate = tmp_path / 'candidate.py'
    # Fixed benign project-like transformation; not model output on the host.
    candidate.write_text('def summarize(rows):\n    return {"count": len(rows), "total": sum(row["value"] for row in rows)}\n')
    trusted = tmp_path / 'cases.json'
    contract = {'schema': 'json-function-v1', 'function': 'summarize', 'cases': [
        {'args': [[{'value': 3}, {'value': -1}]], 'kwargs': {}, 'expected': {'count': 2, 'total': 2}},
        {'args': [[]], 'kwargs': {}, 'expected': {'count': 0, 'total': 0}}]}
    trusted.write_text(json.dumps(contract))
    candidate.chmod(0o600)
    trusted.chmod(0o600)
    return candidate, trusted, contract


def json_function_params(candidate, trusted):
    return dict(enabled='YES', candidate=str(candidate),
                expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                test_file=str(trusted), expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),
                image=IMAGE, execution_policy='json-function-v1', runner_policy={'fixture': True})


def test_json_function_protocol_real_benign_subprocess_and_hidden_oracle(tmp_path, monkeypatch):
    import sys
    import central_ai.isolated_functional_verifier as verifier
    candidate, trusted, contract = json_function_fixture(tmp_path)
    observed = []
    def factory(policy, images, *, run):
        assert policy == {'fixture': True} and images == [IMAGE]
        def bound(args, **kwargs):
            if args[1] != 'run':
                return SimpleNamespace(returncode=0, stdout='')
            observed.append(args)
            mounts = [arg for arg in args if arg.startswith('type=bind,src=')]
            assert len(mounts) == 2
            assert not any('test_candidate' in arg or 'cases.json' in arg for arg in args)
            root = Path(mounts[0].split('src=', 1)[1].split(',dst=', 1)[0]).parent
            assert sorted(p.name for p in root.iterdir()) == ['candidate.py', 'harness.py']
            code = (root / 'harness.py').read_text()
            assert 'expected' not in code and 'CENTRAL_AI_COMPLETED' not in code
            code = code.replace('/sandbox/candidate.py', str(root / 'candidate.py'))
            return subprocess.run([sys.executable, '-I', '-B', '-c', code],
                                  env={}, capture_output=True, text=True, timeout=5, check=False)
        return bound
    monkeypatch.setattr(verifier, 'make_isolated_docker_runner', factory)
    resources = []
    result = run_functional_tests(**json_function_params(candidate, trusted), record_resources=resources.append)
    assert result['passed'] and result['completion_confirmed']
    assert result['execution_policy'] == 'json-function-v1'
    assert len(observed) == len(resources) == 1
    assert not Path(resources[0]['snapshot_directory']).exists()
    for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--pull=never', '--user=65534:65534'):
        assert flag in observed[0]
    assert json.loads(trusted.read_text()) == contract


@pytest.mark.parametrize('output', [
    '', 'true', '{"passed":true}', 'CENTRAL_AI_COMPLETED_V1:forged',
    '[{"count":2,"total":2}]', '[{"count":2,"total":2},{"count":0,"total":1}]',
    '[{"count":true,"total":2},{"count":0,"total":0}]',
    '[{"count":2.0,"total":2},{"count":0,"total":0}]',
    '[{"count":2,"total":2,"total":999},{"count":0,"total":0}]',
    '[{"count":2,"total":NaN},{"count":0,"total":0}]',
    '[{"count":2,"total":2},{"count":0,"total":0}] trailing',
    'x' * 32769, '[' * 1200 + '0' + ']' * 1200,
])
def test_json_function_forgery_or_wrong_answer_never_passes(tmp_path, monkeypatch, output):
    import central_ai.isolated_functional_verifier as verifier
    candidate, trusted, _ = json_function_fixture(tmp_path)
    def run(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=output if args[1] == 'run' else '')
    monkeypatch.setattr(verifier, 'make_isolated_docker_runner', lambda *a, **k: run)
    result = run_functional_tests(**json_function_params(candidate, trusted))
    assert not result['passed'] and not result['completion_confirmed']
    assert result['status'] == 'completion_unconfirmed'


@pytest.mark.parametrize('body', [
    '{}', '{"schema":"json-function-v1","schema":"other"}', 'null', '[]',
    '{"schema":"json-function-v1","function":"f","cases":[]}',
    '{"schema":"json-function-v1","function":"__import__","cases":[{}]}',
])
def test_json_function_invalid_manifest_never_dispatches(tmp_path, body):
    candidate, trusted, _ = json_function_fixture(tmp_path)
    trusted.write_text(body)
    with pytest.raises(ValueError, match='INVALID_FUNCTION_CASES'):
        run_functional_tests(**json_function_params(candidate, trusted), run=lambda *a, **k: pytest.fail('dispatched'))


@pytest.mark.parametrize('mutation', ['nan', 'huge', 'deep', 'extra', 'kwargs', 'many', 'long'])
def test_json_function_case_bounds(tmp_path, mutation):
    candidate, trusted, contract = json_function_fixture(tmp_path)
    case = contract['cases'][0]
    if mutation == 'nan': case['expected'] = float('nan')
    if mutation == 'huge': case['expected'] = 2**53
    if mutation == 'deep':
        value = 0
        for _ in range(18): value = [value]
        case['expected'] = value
    if mutation == 'extra': case['approved'] = True
    if mutation == 'kwargs': case['kwargs'] = {'__builtins__': {}}
    if mutation == 'many': contract['cases'] = [case] * 129
    if mutation == 'long': case['expected'] = 'x' * 4097
    trusted.write_text(json.dumps(contract))
    with pytest.raises(ValueError, match='INVALID_FUNCTION_CASES'):
        run_functional_tests(**json_function_params(candidate, trusted), run=lambda *a, **k: pytest.fail('dispatched'))


def test_json_function_requires_rootless_identity_before_snapshot(tmp_path, monkeypatch):
    import central_ai.isolated_functional_verifier as verifier
    candidate, trusted, _ = json_function_fixture(tmp_path)
    monkeypatch.setattr(verifier.tempfile, 'mkdtemp', lambda **k: pytest.fail('snapshot before identity check'))
    params = json_function_params(candidate, trusted)
    params['runner_policy'] = None
    with pytest.raises(ValueError, match='ISOLATED_RUNNER_REQUIRED'):
        run_functional_tests(**params, run=lambda *a, **k: pytest.fail('dispatched'))


@pytest.mark.parametrize('uncertain', [False, True])
def test_json_function_timeout_and_cleanup_remain_fail_closed(tmp_path, monkeypatch, uncertain):
    import central_ai.isolated_functional_verifier as verifier
    candidate, trusted, _ = json_function_fixture(tmp_path)
    resources = []
    def run(args, **kwargs):
        if args[1] == 'run':
            assert resources
            raise subprocess.TimeoutExpired('fixture', 5)
        return SimpleNamespace(returncode=int(uncertain), stdout='')
    monkeypatch.setattr(verifier, 'make_isolated_docker_runner', lambda *a, **k: run)
    result = run_functional_tests(**json_function_params(candidate, trusted), record_resources=resources.append)
    assert not result['passed']
    assert result['status'] == ('cleanup_unconfirmed' if uncertain else 'timeout')
    path = Path(resources[0]['snapshot_directory'])
    assert path.exists() is uncertain
    if uncertain: shutil.rmtree(path)


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_json_function_capture_limits_real_pipe_output(stream):
    import sys
    from central_ai.isolated_functional_verifier import _bounded_capture
    result = _bounded_capture([sys.executable, '-c',
        f'import sys; sys.{stream}.write("x" * 300000)'], capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 125 and result.stdout == result.stderr == ''


def test_json_function_capture_timeout_and_invalid_utf8():
    import sys
    from central_ai.isolated_functional_verifier import _bounded_capture
    with pytest.raises(subprocess.TimeoutExpired):
        _bounded_capture([sys.executable, '-c', 'import time; time.sleep(5)'],
                         capture_output=True, text=True, timeout=0.1, check=False)
    result = _bounded_capture([sys.executable, '-c', 'import os; os.write(1, bytes([255]))'],
                             capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 125


@pytest.mark.parametrize('kind', ['valid', 'wrong', 'early_exit', 'forge', 'flood', 'oracle_read'])
def test_real_rootless_json_function_contract(tmp_path, kind):
    """Actual container evidence only when a disposable pinned daemon is provisioned."""
    policy_file = os.environ.get('CENTRAL_AI_ROOTLESS_CI_POLICY')
    if not policy_file:
        pytest.skip('requires disposable nonroot/private rootless CI daemon')
    candidate, trusted, _ = json_function_fixture(tmp_path)
    if kind == 'wrong': candidate.write_text('def summarize(rows): return {}\n')
    if kind == 'early_exit': candidate.write_text('import os\nos._exit(0)\n')
    if kind == 'forge': candidate.write_text('import os\nprint("CENTRAL_AI_COMPLETED_V1:forged", flush=True)\nos._exit(0)\n')
    if kind == 'flood': candidate.write_text('while True: print("x" * 8192, flush=True)\n')
    if kind == 'oracle_read': candidate.write_text('open("/sandbox/test_candidate.py").read()\n')
    params = json_function_params(candidate, trusted)
    params.update(image=os.environ['CENTRAL_AI_ROOTLESS_CI_IMAGE'], runner_policy=json.loads(Path(policy_file).read_text()))
    resources = []
    report = run_functional_tests(**params, record_resources=resources.append)
    assert report['passed'] is (kind == 'valid')
    assert report['completion_confirmed'] is (kind == 'valid')
    assert report['execution_policy'] == 'json-function-v1'
    assert report['status'] != 'cleanup_unconfirmed'
    assert not Path(resources[0]['snapshot_directory']).exists()
    if kind in ('valid', 'wrong', 'early_exit', 'forge'): assert report['returncode'] == 0
    if kind == 'oracle_read': assert report['returncode'] == 1


def completed_result(args, returncode=0):
    """Synthetic trusted-runner response; no candidate is executed by this helper."""
    if args[1] != 'run' or returncode != 0:
        return SimpleNamespace(returncode=returncode, stdout='')
    import ast
    mount = next(arg for arg in args if 'dst=/sandbox/harness.py,' in arg)
    harness = Path(mount.split('src=',1)[1].split(',dst=',1)[0])
    record = ast.parse(harness.read_text()).body[-1].value.args[1].value.decode()
    return SimpleNamespace(returncode=0, stdout=record)


def setup_files(tmp_path):
    candidate=tmp_path/"candidate.py"
    candidate.write_text("def add(a,b):\n    return a+b\n")
    trusted=tmp_path/"test_candidate.py"
    trusted.write_text("assert 1+1==2\n")
    # CI runners may use a permissive umask; trusted source/test fixture files
    # must satisfy the existing verifier's no-group/world-write contract.
    candidate.chmod(0o600)
    trusted.chmod(0o600)
    return candidate,trusted


def test_docker_sandbox_contract(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    commands=[]
    def fake_run(args,**kwargs):
        commands.append((args,kwargs))
        return completed_result(args)
    result=run_functional_tests(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image=IMAGE,run=fake_run)
    assert result["passed"] and result["executed_candidate"]
    cmd=commands[0][0]
    for required in ("--network=none","--read-only","--cap-drop=ALL",
                     "--security-opt=no-new-privileges","--pull=never"):
        assert required in cmd
    assert not any("docker.sock" in x for x in cmd)
    assert commands[0][1]["timeout"]==30


def test_denies_unsafe_inputs(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match="FUNCTIONAL_TESTS_DISABLED"):
        run_functional_tests(enabled="",candidate=str(candidate),expected_sha256=digest,
                             test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image=IMAGE)
    with pytest.raises(ValueError,match="UNPINNED_IMAGE"):
        run_functional_tests(enabled="YES",candidate=str(candidate),expected_sha256=digest,
                             test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image="python:latest")
    with pytest.raises(ValueError,match="CANDIDATE_HASH_MISMATCH"):
        run_functional_tests(enabled="YES",candidate=str(candidate),expected_sha256="0"*64,
                             test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image=IMAGE)


def test_nonzero_and_timeout_fail_closed(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    params=dict(enabled="YES",candidate=str(candidate),
                expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image=IMAGE)
    r=run_functional_tests(**params,run=lambda args,**k:SimpleNamespace(returncode=1 if args[1]=="run" else 0, stdout=""))
    assert r["status"]=="failed" and not r["passed"]
    def fail(*a,**k):
        raise subprocess.TimeoutExpired("docker",30)
    r=run_functional_tests(**params,run=fail)
    assert r["status"]=="cleanup_unconfirmed" and not r["passed"]
    shutil.rmtree(r["snapshot_directory"])


def test_timeout_cleanup_is_checked(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    calls=[]
    def fake_run(args,**kwargs):
        calls.append(args)
        if args[1]=="run":
            raise subprocess.TimeoutExpired("docker",30)
        return SimpleNamespace(returncode=0, stdout=calls[0][3]+"\n" if len(calls)==2 else "")
    result=run_functional_tests(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),image=IMAGE,run=fake_run)
    assert result["status"]=="timeout" and not result["passed"]
    assert calls[0][2]=="--name"
    assert calls[1][1:3] == ["container", "ls"]
    assert calls[2]==["docker","rm","-f",calls[0][3]]
    assert calls[3] == calls[1]



def test_test_integrity_is_required_before_docker(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    calls=[]
    params=dict(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        test_file=str(trusted),image=IMAGE,run=lambda *a,**k:calls.append(a))
    with pytest.raises(ValueError,match="INVALID_TEST_HASH"):
        run_functional_tests(**params)
    digest=hashlib.sha256(trusted.read_bytes()).hexdigest()
    trusted.write_text("raise RuntimeError('tampered test')\n")
    with pytest.raises(ValueError,match="TEST_HASH_MISMATCH"):
        run_functional_tests(**params,expected_test_sha256=digest)
    assert calls==[]


@pytest.mark.parametrize("digest", ["", "a"*63, "A"*64, "z"*64])
def test_malformed_test_hash_never_executes(tmp_path,digest):
    candidate,trusted=setup_files(tmp_path)
    def forbidden(*args,**kwargs):
        raise AssertionError("Docker must not run")
    with pytest.raises(ValueError,match="INVALID_TEST_HASH"):
        run_functional_tests(enabled="YES",candidate=str(candidate),
            expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
            test_file=str(trusted),expected_test_sha256=digest,image=IMAGE,run=forbidden)



def test_original_replacement_cannot_change_mounted_bytes(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    originals=[candidate.read_bytes(),trusted.read_bytes()]
    snapshots=[]
    def replace_before_docker(args,**kwargs):
        if args[1] != "run":
            return SimpleNamespace(returncode=0, stdout="")
        candidate.unlink()
        candidate.write_text("raise RuntimeError('replaced candidate')\n")
        trusted.unlink()
        trusted.write_text("raise RuntimeError('replaced tests')\n")
        mounts=[arg for arg in args if arg.startswith("type=bind,src=")]
        for original,mount,expected in zip((candidate,trusted),mounts,originals):
            frozen=Path(mount.split("src=",1)[1].split(",dst=",1)[0])
            snapshots.append(frozen)
            assert frozen != original
            assert frozen.read_bytes()==expected
            assert frozen.stat().st_mode & 0o222 == 0
            assert frozen.parent.stat().st_mode & 0o077 == 0
        return completed_result(args)
    result=run_functional_tests(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(originals[0]).hexdigest(),
        test_file=str(trusted),expected_test_sha256=hashlib.sha256(originals[1]).hexdigest(),
        image=IMAGE,run=replace_before_docker)
    assert result["passed"]
    assert snapshots and all(not path.parent.exists() for path in snapshots)


@pytest.mark.parametrize("kind",["symlink","hardlink","fifo","oversize"])
def test_unsafe_input_never_reaches_docker(tmp_path,kind):
    candidate,trusted=setup_files(tmp_path)
    digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
    if kind=="symlink":
        target=tmp_path/"target.py"
        candidate.rename(target)
        candidate.symlink_to(target)
    elif kind=="hardlink":
        os.link(candidate,tmp_path/"alias.py")
    elif kind=="fifo":
        candidate.unlink()
        os.mkfifo(candidate)
    else:
        candidate.write_bytes(b"x"*32769)
    def forbidden(*args,**kwargs):
        raise AssertionError("Docker must not start")
    with pytest.raises(ValueError,match="UNSAFE_INPUT"):
        run_functional_tests(enabled="YES",candidate=str(candidate),expected_sha256=digest,
            test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),
            image=IMAGE,run=forbidden)


def test_uncertain_cleanup_retains_snapshot_for_quarantine(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    def unavailable(args,**kwargs):
        if args[1]=="run":
            raise subprocess.TimeoutExpired("docker",30)
        return SimpleNamespace(returncode=1)
    result=run_functional_tests(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        test_file=str(trusted),expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),
        image=IMAGE,run=unavailable)
    root=Path(result["snapshot_directory"])
    try:
        assert result["status"]=="cleanup_unconfirmed" and result["passed"] is False
        assert (root/"candidate.py").read_bytes()==candidate.read_bytes()
        assert (root/"test_candidate.py").read_bytes()==trusted.read_bytes()
        assert result["container_name"].startswith("central-ai-verifier-")
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize('exit_kind', ['passed', 'failed', 'timeout', 'oserror'])
@pytest.mark.parametrize('cleanup_kind', ['absent', 'removed', 'daemon_error', 'rm_error', 'still_present'])
def test_independent_absence_proof_after_every_exit(tmp_path, exit_kind, cleanup_kind):
    candidate, trusted = setup_files(tmp_path)
    calls = []
    name = None
    probes = 0
    def runner(args, **kwargs):
        nonlocal name, probes
        calls.append(args)
        if args[1] == 'run':
            name = args[3]
            if exit_kind == 'timeout':
                raise subprocess.TimeoutExpired('docker', 5)
            if exit_kind == 'oserror':
                raise OSError('synthetic daemon error')
            return completed_result(args, 0 if exit_kind == 'passed' else 1)
        if args[1:3] == ['container', 'ls']:
            probes += 1
            assert 'name=^/' + name + '$' in args
            if cleanup_kind == 'daemon_error':
                return SimpleNamespace(returncode=1, stdout='')
            absent = cleanup_kind == 'absent' or (cleanup_kind == 'removed' and probes > 1)
            return SimpleNamespace(returncode=0, stdout='' if absent else name+'\n')
        assert args == ['docker', 'rm', '-f', name]
        return SimpleNamespace(returncode=1 if cleanup_kind == 'rm_error' else 0)
    result = run_functional_tests(enabled='YES', candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
        expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE, run=runner)
    uncertain = cleanup_kind not in ('absent', 'removed')
    try:
        assert result['status'] == ('cleanup_unconfirmed' if uncertain else
            {'passed':'passed', 'failed':'failed', 'timeout':'timeout', 'oserror':'execution_error'}[exit_kind])
        assert result['passed'] is (exit_kind == 'passed' and not uncertain)
        assert probes >= 1
        if uncertain:
            assert Path(result['snapshot_directory']).is_dir()
    finally:
        if 'snapshot_directory' in result:
            shutil.rmtree(result['snapshot_directory'])


def test_resource_record_failure_prevents_any_docker_dispatch(tmp_path):
    candidate, trusted = setup_files(tmp_path)
    resources = []
    def cannot_record(handles):
        resources.append(handles)
        assert Path(handles['snapshot_directory']).is_dir()
        raise OSError('synthetic audit write error')
    with pytest.raises(OSError, match='synthetic audit'):
        run_functional_tests(enabled='YES', candidate=str(candidate),
            expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
            expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE,
            record_resources=cannot_record, run=lambda *a, **k: pytest.fail('must not dispatch'))
    assert resources and not Path(resources[0]['snapshot_directory']).exists()


@pytest.mark.parametrize('interrupt_at', ['run', 'probe'])
def test_cancellation_preserves_unknown_resources(tmp_path, interrupt_at):
    candidate, trusted = setup_files(tmp_path)
    resources = []
    def runner(args, **kwargs):
        if args[1] == 'run':
            raise KeyboardInterrupt('synthetic cancellation')
        if interrupt_at == 'probe':
            raise KeyboardInterrupt('synthetic cancellation')
        raise OSError('synthetic daemon unavailable')
    with pytest.raises(KeyboardInterrupt):
        run_functional_tests(enabled='YES', candidate=str(candidate),
            expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
            expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE,
            record_resources=lambda handles: resources.append(handles), run=runner)
    root = Path(resources[0]['snapshot_directory'])
    try:
        assert root.is_dir()
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize('cleanup', ['absent', 'removed'])
def test_cancellation_with_independent_daemon_absence_cleans_snapshot(tmp_path, cleanup):
    """Client interruption cannot count as success; clean only after daemon proof."""
    candidate, trusted = setup_files(tmp_path)
    resources = []
    calls = []
    probes = 0
    def runner(args, **kwargs):
        nonlocal probes
        calls.append(args)
        if args[1] == 'run':
            raise KeyboardInterrupt('synthetic client interruption')
        if args[1:3] == ['container', 'ls']:
            probes += 1
            assert 'name=^/' + resources[0]['container_name'] + '$' in args
            present = cleanup == 'removed' and probes == 1
            return SimpleNamespace(returncode=0,
                                   stdout=resources[0]['container_name'] + '\n' if present else '')
        assert args == ['docker', 'rm', '-f', resources[0]['container_name']]
        return SimpleNamespace(returncode=0, stdout='')
    with pytest.raises(KeyboardInterrupt, match='synthetic client interruption'):
        run_functional_tests(enabled='YES', candidate=str(candidate),
            expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
            test_file=str(trusted),
            expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(),
            image=IMAGE, record_resources=lambda value: resources.append(value), run=runner)
    assert len(resources) == 1
    assert probes == (2 if cleanup == 'removed' else 1)
    assert not Path(resources[0]['snapshot_directory']).exists()
    assert (len([args for args in calls if args[1:3] == ['rm', '-f']]) ==
            (1 if cleanup == 'removed' else 0))


@pytest.mark.parametrize('body', [
    'import os\nos._exit(0)\n',
    'def f():\n    return __import__("os")._exit(0)\n',
    'def f():\n    import os\n    os._exit(0)\n',
    '@print\ndef f(): return 1\n',
    'def f(x=print("forged")): return 1\n',
    'def f(x: print("forged")): return 1\n',
    'def f(x): return x.__class__\n',
    'def f(x): return globals()\n',
    'def f(x): return [v for v in x]\n',
    'def f(x): return x ** 999999\n',
    'def f(x): return (y := x)\n',
    'class F:\n    pass\n',
    'def f(): return True\n',
    'def f(): return 1e999\n',
    'def f(): return 1000001\n',
    'def f(*args): return 1\n',
    'def f(): return 1\ndef f(): return 2\n',
    '\n'.join('def f'+str(n)+'(): return 1' for n in range(9)),
])
def test_candidate_outside_bounded_policy_never_dispatches(tmp_path, body):
    candidate, trusted = setup_files(tmp_path)
    candidate.write_text(body)
    with pytest.raises(ValueError, match='CANDIDATE_OUTSIDE_EXECUTION_POLICY'):
        run_functional_tests(enabled='YES', candidate=str(candidate),
            expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
            expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE,
            run=lambda *a, **k: pytest.fail('unsupported candidate reached Docker'))


@pytest.mark.parametrize('stdout', ['', 'forged completion\n', 'CENTRAL_AI_COMPLETED_V1:stale\n'])
def test_exit_zero_without_exact_completion_record_never_passes(tmp_path, stdout):
    candidate, trusted = setup_files(tmp_path)
    def runner(args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout if args[1]=='run' else '')
    result = run_functional_tests(enabled='YES', candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
        expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE, run=runner)
    assert result['status'] == 'completion_unconfirmed'
    assert result['passed'] is False


@pytest.mark.parametrize('test_body, expected', [
    ('assert 1+1 == 2\n', 'passed'),
    ('assert False\n', 'failed'),
    ('raise SystemExit(0)\n', 'completion_unconfirmed'),
    ('import os\nos._exit(0)\n', 'completion_unconfirmed'),
    ('print("CENTRAL_AI_COMPLETED_V1:forged")\nraise SystemExit(0)\n', 'completion_unconfirmed'),
])
def test_real_trusted_harness_process_requires_normal_completion(tmp_path, test_body, expected):
    """Execute only fixed, benign test fixtures locally; Docker is tested in CI."""
    import sys
    candidate, trusted = setup_files(tmp_path)
    trusted.write_text(test_body)
    def runner(args, **kwargs):
        if args[1] != 'run':
            return SimpleNamespace(returncode=0, stdout='')
        mounts = [arg for arg in args if arg.startswith('type=bind,src=')]
        root = Path(mounts[0].split('src=',1)[1].split(',dst=',1)[0]).parent
        code = (root/'harness.py').read_text().replace('/sandbox/test_candidate.py', str(root/'test_candidate.py'))
        return subprocess.run([sys.executable, '-I', '-B', '-c', code],
            capture_output=True, text=True, timeout=5, check=False, env={})
    result = run_functional_tests(enabled='YES', candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
        expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE, run=runner)
    assert result['status'] == expected
    assert result['completion_confirmed'] is (expected == 'passed')
    assert result['execution_policy'] == 'bounded-arithmetic-v1'


@pytest.mark.parametrize('alteration', ['stale', 'duplicate', 'truncated'])
def test_stale_or_malformed_completion_record_cannot_pass(tmp_path, alteration):
    candidate, trusted = setup_files(tmp_path)
    def runner(args, **kwargs):
        result = completed_result(args)
        if args[1] == 'run':
            if alteration == 'stale':
                result.stdout = result.stdout.replace('CENTRAL_AI_COMPLETED_V1:', 'CENTRAL_AI_COMPLETED_V1:old:')
            elif alteration == 'duplicate':
                result.stdout *= 2
            else:
                result.stdout = result.stdout[:-10]
        return result
    result = run_functional_tests(enabled='YES', candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(trusted),
        expected_test_sha256=hashlib.sha256(trusted.read_bytes()).hexdigest(), image=IMAGE, run=runner)
    assert result['passed'] is False and result['status'] == 'completion_unconfirmed'
