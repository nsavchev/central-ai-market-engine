import hashlib
import subprocess
from types import SimpleNamespace
import pytest
from central_ai.isolated_verifier import verify_candidate

IMAGE="python@sha256:" + "a"*64


def test_locked_down_docker_invocation(tmp_path):
    file=tmp_path/"candidate.py"
    file.write_text("def safe():\n    return 1\n")
    seen=[]
    def fake_run(argv,**kwargs):
        seen.append((argv,kwargs))
        return SimpleNamespace(returncode=0)
    result=verify_candidate(enabled="YES",candidate=str(file),
        expected_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),image=IMAGE,run=fake_run)
    assert result["passed"] is True
    assert result["executed_candidate"] is False
    cmd=seen[0][0]
    for option in ("--network","none","--read-only","--cap-drop=ALL","--pull=never"):
        assert option in cmd
    assert "--privileged" not in cmd
    assert "docker.sock" not in " ".join(cmd)
    assert seen[0][1]["timeout"]==30


def test_denies_unpinned_and_hash_mismatch(tmp_path):
    file=tmp_path/"candidate.py"
    file.write_text("pass\n")
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match="VERIFIER_DISABLED"):
        verify_candidate(enabled="",candidate=str(file),expected_sha256=digest,image=IMAGE)
    with pytest.raises(ValueError,match="UNPINNED_IMAGE"):
        verify_candidate(enabled="YES",candidate=str(file),expected_sha256=digest,image="python:3.12")
    with pytest.raises(ValueError,match="CANDIDATE_HASH_MISMATCH"):
        verify_candidate(enabled="YES",candidate=str(file),expected_sha256="0"*64,image=IMAGE)


def test_timeout_is_not_success(tmp_path):
    file=tmp_path/"candidate.py"
    file.write_text("pass\n")
    def timed_out(*a,**k):
        raise subprocess.TimeoutExpired(cmd="docker",timeout=30)
    result=verify_candidate(enabled="YES",candidate=str(file),
        expected_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        image=IMAGE,run=timed_out)
    assert result["status"]=="timeout" and result["passed"] is False
