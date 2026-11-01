"""AI-11: fail-closed, review-only handoff from existing analyzed task.

This prepares an immutable proposal manifest, not a code patch or deployment.
"""
import json
import os
import re
from pathlib import Path

from central_ai.persistent_bridge import PersistentTaskBridge


def create_review_handoff(*, enabled, database, task_id, output_directory):
    if enabled != "YES":
        raise ValueError("HANDOFF_DISABLED")
    if not isinstance(task_id, str) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", task_id
    ):
        raise ValueError("INVALID_TASK_ID")
    db = Path(database)
    if not db.is_absolute() or not db.is_file() or db.is_symlink():
        raise ValueError("INVALID_TASK_DB")
    output = Path(output_directory)
    if not output.is_absolute() or output.is_symlink() or not output.is_dir():
        raise ValueError("INVALID_OUTPUT_DIRECTORY")
    if output.stat().st_mode & 0o022:
        raise ValueError("INSECURE_OUTPUT_DIRECTORY")

    bridge = PersistentTaskBridge(db)
    task = bridge.status(task_id)
    if task is None or task.get("status") != "analyzed":
        raise ValueError("TASK_NOT_ANALYZED")
    overview = bridge.task_overview(task_id)
    if (
        task.get("approved") is not False
        or task.get("deployment_allowed") is not False
        or overview["approved"] is not False
        or overview["deployment_allowed"] is not False
        or overview["effective_status"] != "done"
    ):
        raise ValueError("SECURITY_GATE_BLOCKED")
    analysis = task.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("INVALID_ANALYSIS")
    if not isinstance(analysis.get("functions"), list):
        raise ValueError("INVALID_ANALYSIS")

    manifest = {
        "schema": "ai11-review-handoff-v1",
        "task_id": task_id,
        "source_status": "analyzed",
        "analysis": analysis,
        "proposal_status": "review_required",
        "patch": None,
        "tests": [],
        "test_status": "not_run",
        "approved": False,
        "deployment_allowed": False,
        "production_modified": False,
    }
    content = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True)
    if len(content.encode("utf-8")) > 131072:
        raise ValueError("MANIFEST_TOO_LARGE")
    destination = output / ("handoff_" + task_id + ".json")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content + "\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {"task_id": task_id, "path": str(destination), "status": "review_required", "deployment_allowed": False}
