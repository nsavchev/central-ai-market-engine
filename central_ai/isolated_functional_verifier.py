"""Opt-in restricted Docker execution of a candidate against operator-supplied tests.

Untrusted candidate *is executed*, but only in a disposable restricted container.
No claim of a hardened security boundary against kernel-level exploits.
"""
import hashlib
import os
import re
import subprocess
import uuid
from pathlib import Path


def run_functional_tests(*, enabled, candidate, expected_sha256, test_file, image,
                         expected_test_sha256=None, timeout=30, run=subprocess.run):
    if enabled != "YES":
        raise ValueError("FUNCTIONAL_TESTS_DISABLED")
    paths = [Path(candidate), Path(test_file)]
    for path in paths:
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.suffix != ".py" or path.stat().st_size > 32768
            or path.stat().st_mode & 0o022):
            raise ValueError("UNSAFE_INPUT")
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError("TEST_FILE_MUST_BE_SEPARATE")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("INVALID_HASH")
    if hashlib.sha256(paths[0].read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("CANDIDATE_HASH_MISMATCH")
    if not isinstance(expected_test_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_test_sha256):
        raise ValueError("INVALID_TEST_HASH")
    if hashlib.sha256(paths[1].read_bytes()).hexdigest() != expected_test_sha256:
        raise ValueError("TEST_HASH_MISMATCH")
    if not isinstance(image, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("UNPINNED_IMAGE")
    if type(timeout) is not int or not 5 <= timeout <= 60:
        raise ValueError("INVALID_TIMEOUT")
    container_name = 'central-ai-verifier-' + uuid.uuid4().hex
    cmd = [
        'docker', 'run', '--name', container_name, '--rm', '--pull=never',
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=32",
        "--memory=128m", "--cpus=0.5", "--user=65534:65534",
        "--mount", "type=bind,src=" + str(paths[0]) + ",dst=/sandbox/candidate.py,readonly",
        "--mount", "type=bind,src=" + str(paths[1]) + ",dst=/sandbox/test_candidate.py,readonly",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m",
        "--workdir", "/tmp", "--entrypoint", "python",
        image, "-I", "-B", "/sandbox/test_candidate.py",
    ]
    try:
        result = run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        # A client timeout does not prove Docker stopped its container.
        # Fail closed until a forced removal has been confirmed.
        try:
            cleanup = run(
                ["docker", "rm", "-f", container_name],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return {"status": "cleanup_unconfirmed", "passed": False, "executed_candidate": True}
        if cleanup.returncode != 0:
            return {"status": "cleanup_unconfirmed", "passed": False, "executed_candidate": True}
        return {"status": "timeout", "passed": False, "executed_candidate": True}
    return {"test_sha256": expected_test_sha256, "status": "passed" if result.returncode == 0 else "failed",
            "passed": result.returncode == 0, "executed_candidate": True,
            "returncode": result.returncode}
