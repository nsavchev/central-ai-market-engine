import hashlib
import subprocess
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
        return SimpleNamespace(returncode=0)
    result=run_functional_tests(enabled="YES",candidate=str(candidate),
        expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        test_file=str(trusted),image=IMAGE,run=fake_run)
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
                             test_file=str(trusted),image=IMAGE)
    with pytest.raises(ValueError,match="UNPINNED_IMAGE"):
        run_functional_tests(enabled="YES",candidate=str(candidate),expected_sha256=digest,
                             test_file=str(trusted),image="python:latest")
    with pytest.raises(ValueError,match="CANDIDATE_HASH_MISMATCH"):
        run_functional_tests(enabled="YES",candidate=str(candidate),expected_sha256="0"*64,
                             test_file=str(trusted),image=IMAGE)


def test_nonzero_and_timeout_fail_closed(tmp_path):
    candidate,trusted=setup_files(tmp_path)
    params=dict(enabled="YES",candidate=str(candidate),
                expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                test_file=str(trusted),image=IMAGE)
    r=run_functional_tests(**params,run=lambda *a,**k:SimpleNamespace(returncode=1))
    assert r["status"]=="failed" and not r["passed"]
    def fail(*a,**k):
        raise subprocess.TimeoutExpired("docker",30)
    r=run_functional_tests(**params,run=fail)
    assert r["status"]=="timeout" and not r["passed"]
