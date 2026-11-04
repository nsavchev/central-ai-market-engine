import hashlib
import subprocess
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
import pytest

from central_ai.isolated_functional_verifier import run_functional_tests

IMAGE="python@sha256:"+"a"*64


def setup_files(tmp_path):
    candidate=tmp_path/"candidate.py"
    candidate.write_text("def add(a,b):\n    return a+b\n")
    trusted=tmp_path/"test_candidate.py"
    trusted.write_text("assert 1+1==2\n")
    return candidate,trusted


def test_docker_sandbox_contract(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    commands=[]
    def fake_run(args,**kwargs):
        commands.append((args,kwargs))
        return SimpleNamespace(returncode=0, stdout="")
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
        return SimpleNamespace(returncode=0, stdout="")
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
            return SimpleNamespace(returncode=0 if exit_kind == 'passed' else 1)
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
