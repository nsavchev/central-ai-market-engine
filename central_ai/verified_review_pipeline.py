"""AI-26: opt-in gate from reviewed candidate to existing isolated verifier.

No automatic retries or deployment. Tests are operator-supplied and kept separate.
"""
from central_ai.review_pipeline import prepare_review_pipeline
from central_ai.isolated_functional_verifier import run_functional_tests


def prepare_and_verify(*, enabled, database, task_id, handoffs, proposals,
                       candidates, recommendation, trusted_test_file, image,
                       verifier=run_functional_tests):
    if enabled != "YES":
        raise ValueError("PIPELINE_VERIFICATION_DISABLED")
    prepared = prepare_review_pipeline(
        enabled="YES", database=database, task_id=task_id,
        handoffs=handoffs, proposals=proposals, candidates=candidates,
        recommendation=recommendation,
    )
    result = verifier(
        enabled="YES", candidate=prepared["candidate_path"],
        expected_sha256=prepared["candidate_sha256"],
        test_file=trusted_test_file, image=image,
    )
    if not isinstance(result, dict) or type(result.get("passed")) is not bool:
        raise ValueError("INVALID_VERIFIER_RESULT")
    return {
        "task_id": task_id,
        "candidate_sha256": prepared["candidate_sha256"],
        "test_status": result.get("status", "unknown"),
        "tests_passed": result["passed"],
        "approved": False,
        "deployment_allowed": False,
    }
