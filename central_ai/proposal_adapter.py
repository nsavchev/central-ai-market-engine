"""AI-12: validated review handoff -> existing proposal schema, no patch execution."""
import json
import os
import re
from pathlib import Path


def create_proposal_from_handoff(*, enabled, handoff_path, output_directory, recommendation):
    if enabled != "YES":
        raise ValueError("PROPOSAL_DISABLED")
    if not isinstance(recommendation, str) or not recommendation.strip() or len(recommendation) > 12000:
        raise ValueError("INVALID_RECOMMENDATION")
    source = Path(handoff_path)
    output = Path(output_directory)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise ValueError("INVALID_HANDOFF")
    if source.stat().st_size > 131072 or source.stat().st_mode & 0o022:
        raise ValueError("UNSAFE_HANDOFF")
    if not output.is_absolute() or output.is_symlink() or not output.is_dir() or output.stat().st_mode & 0o022:
        raise ValueError("INSECURE_OUTPUT")
    data = json.loads(source.read_text("utf-8"))
    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", task_id
    ):
        raise ValueError("INVALID_TASK_ID")
    if source.name != "handoff_" + task_id + ".json":
        raise ValueError("MISMATCHED_SOURCE")
    if (data.get("schema") != "ai11-review-handoff-v1"
        or data.get("source_status") != "analyzed"
        or data.get("proposal_status") != "review_required"
        or data.get("approved") is not False
        or data.get("deployment_allowed") is not False
        or data.get("production_modified") is not False
        or data.get("patch") is not None
        or data.get("test_status") != "not_run"):
        raise ValueError("HANDOFF_GATE_BLOCKED")

    # Use the v2 code-proposal schema; never invoke its fixed-target patch builder.
    proposal = {
        "id": task_id,
        "source_analysis": source.name,
        "target": None,
        "status": "draft",
        "approved": False,
        "production_modified": False,
        "deployment_allowed": False,
        "ai_recommendations": [recommendation],
        "patch": None,
        "tests": [],
        "test_status": "not_run",
        "review_status": "pending",
    }
    path = output / ("proposal_" + task_id + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(proposal, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return {"proposal_id": task_id, "path": str(path), "review_status": "pending", "deployment_allowed": False}
