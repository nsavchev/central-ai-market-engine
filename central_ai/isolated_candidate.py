"""Extract a single Python candidate into an isolated directory; never execute or deploy."""
import ast
import hashlib
import json
import os
import re
from pathlib import Path


def prepare_candidate(*, enabled, proposal_path, candidate_directory, expected_recommendation_sha256=None):
    if enabled != "YES":
        raise ValueError("CANDIDATE_DISABLED")
    source, dest = Path(proposal_path), Path(candidate_directory)
    if not source.is_absolute() or source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
        raise ValueError("INVALID_PROPOSAL")
    if source.stat().st_mode & 0o022:
        raise ValueError("UNSAFE_PROPOSAL")
    if not dest.is_absolute() or dest.is_symlink() or not dest.is_dir() or dest.stat().st_mode & 0o022:
        raise ValueError("INSECURE_CANDIDATE_DIRECTORY")
    data = json.loads(source.read_text("utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("approved") is not False
        or data.get("deployment_allowed") is not False
        or data.get("production_modified") is not False
        or data.get("target") is not None
        or data.get("patch") is not None
        or data.get("review_status") != "pending"
        or data.get("test_status") != "not_run"
        or data.get("status") != "draft"
    ):
        raise ValueError("PROPOSAL_GATE_BLOCKED")
    task_id = data.get("id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", task_id):
        raise ValueError("INVALID_ID")
    answers = data.get("ai_recommendations")
    if not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], str):
        raise ValueError("INVALID_RECOMMENDATION")
    if expected_recommendation_sha256 is not None and (
        not isinstance(expected_recommendation_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_recommendation_sha256)
        or hashlib.sha256(answers[0].encode('utf-8')).hexdigest() != expected_recommendation_sha256
    ):
        raise ValueError("PROPOSAL_RECOMMENDATION_CHANGED")
    matches = re.findall(r"```python\s*\n(.*?)```", answers[0], flags=re.I | re.S)
    if len(matches) != 1:
        raise ValueError("REQUIRE_SINGLE_PYTHON_BLOCK")
    code = matches[0]
    if not code.strip() or len(code.encode("utf-8")) > 32768:
        raise ValueError("INVALID_CANDIDATE_SIZE")
    ast.parse(code, filename="<untrusted-candidate>")
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    out = dest / ("candidate_" + task_id + ".py")
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(code)
    return {"candidate_path": str(out), "sha256": digest, "executed": False, "deployment_allowed": False}
