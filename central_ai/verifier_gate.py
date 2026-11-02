"""AI-13: validate a draft proposal before manual verifier handoff.

This module never executes source, runs tests, writes to workspaces or deploys.
"""
import json
from pathlib import Path


def check_proposal_for_verifier(*, enabled, proposal_path):
    if enabled != "YES":
        raise ValueError("VERIFIER_GATE_DISABLED")
    path = Path(proposal_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("INVALID_PROPOSAL")
    if path.stat().st_size > 65536 or path.stat().st_mode & 0o022:
        raise ValueError("UNSAFE_PROPOSAL")
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("INVALID_PROPOSAL")
    if (
        data.get("status") != "draft"
        or data.get("approved") is not False
        or data.get("deployment_allowed") is not False
        or data.get("production_modified") is not False
        or data.get("patch") is not None
        or data.get("target") is not None
        or data.get("test_status") != "not_run"
        or data.get("review_status") != "pending"
        or data.get("tests") != []
    ):
        raise ValueError("VERIFIER_GATE_BLOCKED")
    suggestions = data.get("ai_recommendations")
    if (
        not isinstance(suggestions, list)
        or len(suggestions) != 1
        or not isinstance(suggestions[0], str)
        or not suggestions[0].strip()
    ):
        raise ValueError("INVALID_RECOMMENDATIONS")
    return {
        "proposal_id": data.get("id"),
        "verifier_status": "awaiting_isolated_candidate",
        "tests_executed": False,
        "approved": False,
        "deployment_allowed": False,
    }
