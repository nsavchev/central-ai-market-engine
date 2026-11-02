"""AI-16 opt-in isolated Docker candidate verifier.

No shell, no production mounts, no network or Docker socket inside the sandbox.
The caller must supply a pinned, vetted Python runner image by digest.
"""
import hashlib
import os
import re
import subprocess
from pathlib import Path


def verify_candidate(*, enabled, candidate, expected_sha256, image, timeout=30, run=subprocess.run):
    if enabled != "YES":
        raise ValueError("VERIFIER_DISABLED")
    path = Path(candidate)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("INVALID_CANDIDATE")
    if path.suffix != ".py" or path.stat().st_size > 32768 or path.stat().st_mode & 0o022:
        raise ValueError("UNSAFE_CANDIDATE")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("INVALID_SHA256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("CANDIDATE_HASH_MISMATCH")
    if not isinstance(image, str) or not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", image):
        raise ValueError("UNPINNED_IMAGE")
    if type(timeout) is not int or not 5 <= timeout <= 60:
        raise ValueError("INVALID_TIMEOUT")
    # Compilation parses code but never imports or executes candidate functions.
    cmd = [
        "docker", "run", "--rm", "--pull=never",
        "--network", "none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--cpus=0.5",
        "--user=65534:65534",
        "--mount", "type=bind,src=" + str(path) + ",dst=/sandbox/candidate.py,readonly",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m",
        "--workdir", "/tmp", "--entrypoint", "python",
        image, "-I", "-B", "-c",
        "import ast,pathlib;ast.parse(pathlib.Path('/sandbox/candidate.py').read_text('utf-8'))",
    ]
    try:
        result = run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "passed": False, "executed_candidate": False}
    return {
        "status": "syntax_passed" if result.returncode == 0 else "syntax_failed",
        "passed": result.returncode == 0,
        "executed_candidate": False,
        "returncode": result.returncode,
    }
