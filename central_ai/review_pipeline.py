"""AI-25: one opt-in review pipeline; no extra queue or deployment."""
import hashlib
from pathlib import Path

from central_ai.review_handoff import create_review_handoff
from central_ai.proposal_adapter import create_proposal_from_handoff
from central_ai.verifier_gate import check_proposal_for_verifier
from central_ai.isolated_candidate import prepare_candidate


def prepare_review_pipeline(*, enabled, database, task_id, handoffs,
                            proposals, candidates, recommendation):
    if enabled != "YES":
        raise ValueError("PIPELINE_DISABLED")
    # Existing bridge checks stored task, queue completion and security flags.
    handoff = create_review_handoff(
        enabled="YES", database=database, task_id=task_id,
        output_directory=handoffs)
    proposal = create_proposal_from_handoff(
        enabled="YES", handoff_path=handoff["path"],
        output_directory=proposals, recommendation=recommendation)
    gate = check_proposal_for_verifier(
        enabled="YES", proposal_path=proposal["path"])
    # No candidate if there is no single valid Python block.
    candidate = prepare_candidate(
        enabled="YES", proposal_path=proposal["path"],
        candidate_directory=candidates,
        expected_recommendation_sha256=hashlib.sha256(recommendation.encode('utf-8')).hexdigest())
    return {
        "task_id": task_id,
        "proposal_path": proposal["path"],
        "candidate_path": candidate["candidate_path"],
        "candidate_sha256": candidate["sha256"],
        "verifier_status": gate["verifier_status"],
        "executed": False,
        "approved": False,
        "deployment_allowed": False,
    }
