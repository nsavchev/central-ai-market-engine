"""AI-26: opt-in gate from reviewed candidate to existing isolated verifier.

No automatic retries or deployment. Tests are operator-supplied and kept separate.
"""
import re
import secrets
from pathlib import Path
from central_ai.task_storage import TaskStorage
from central_ai.review_pipeline import prepare_review_pipeline
from central_ai.isolated_functional_verifier import run_functional_tests


def prepare_and_verify(*, enabled, database, task_id, handoffs, proposals,
                       candidates, recommendation, trusted_test_file, image,
                       trusted_test_sha256=None, authorization_check=None,
                       verifier=run_functional_tests):
    if enabled != "YES":
        raise ValueError("PIPELINE_VERIFICATION_DISABLED")
    if not isinstance(trusted_test_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", trusted_test_sha256):
        raise ValueError("INVALID_TEST_HASH")
    # This is a trusted host dependency, never caller-supplied proposal code.
    # No provider is configured by default; hash integrity is not authorization.
    if not callable(authorization_check):
        raise ValueError("REVIEW_AUTHORIZATION_REQUIRED")
    if not isinstance(image, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("UNPINNED_IMAGE")
    db = Path(database)
    if not db.is_absolute() or not db.is_file() or db.is_symlink():
        raise ValueError("INVALID_TASK_DB")
    storage = TaskStorage(db)
    nonce = secrets.token_hex(16)
    storage.begin_verification(task_id, nonce)
    stage = "preparation"
    try:
        prepared = prepare_review_pipeline(
            enabled="YES", database=database, task_id=task_id,
            handoffs=handoffs, proposals=proposals, candidates=candidates,
            recommendation=recommendation,
        )
        binding = {
            "schema": "verification-request-v1",
            "nonce": nonce,
            "task_id": task_id,
            "candidate_sha256": prepared["candidate_sha256"],
            "test_sha256": trusted_test_sha256,
            "image": image,
            "scope": "verify_only",
        }
        # Pass a separate dictionary so a provider cannot mutate the expected tuple.
        stage = "authorization"
        receipt = authorization_check(dict(binding))
        if (
            not isinstance(receipt, dict)
            or receipt.get("verification_authorized") is not True
            or receipt.get("binding") != binding
            or receipt.get("approved") is not False
            or receipt.get("deployment_allowed") is not False
            or not isinstance(receipt.get("reviewer_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,128}", receipt["reviewer_id"])
            or not isinstance(receipt.get("authorization_id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,128}", receipt["authorization_id"])
        ):
            raise ValueError("REVIEW_AUTHORIZATION_DENIED")
        storage.authorize_verification(task_id, nonce, binding, receipt["reviewer_id"], receipt["authorization_id"])
        stage = "execution"
        recorded_resources = None
        def record_resources(resources):
            nonlocal recorded_resources
            storage.record_verification_resources(task_id, nonce, resources)
            recorded_resources = dict(resources)
        result = verifier(
            enabled="YES", candidate=prepared["candidate_path"],
            expected_sha256=prepared["candidate_sha256"],
            test_file=trusted_test_file, expected_test_sha256=trusted_test_sha256, image=image,
            record_resources=record_resources,
        )
        stage = "result"
        if (recorded_resources is None or not isinstance(result, dict)
                or type(result.get("passed")) is not bool):
            raise ValueError("INVALID_VERIFIER_RESULT")
        status = result.get("status")
        if (status not in ("passed", "failed", "completion_unconfirmed", "timeout", "execution_error", "cleanup_unconfirmed")
                or result["passed"] is not (status == "passed")
                or result.get("execution_policy") != "bounded-arithmetic-v1"
                or type(result.get("completion_confirmed")) is not bool
                or result["completion_confirmed"] is not result["passed"]
                or result.get("executed_candidate") is not True
                or result.get("approved", False) is not False
                or result.get("deployment_allowed", False) is not False):
            raise ValueError("INVALID_VERIFIER_RESULT")
        if status in ("passed", "failed", "completion_unconfirmed"):
            code = result.get("returncode")
            if (type(code) is not int or (code == 0) is not (status != "failed")
                    or result.get("test_sha256") != trusted_test_sha256):
                raise ValueError("INVALID_VERIFIER_RESULT")
        quarantine = None
        if status == "cleanup_unconfirmed":
            snapshot, container = result.get("snapshot_directory"), result.get("container_name")
            if (not isinstance(snapshot, str) or len(snapshot) > 4096
                    or any(ord(char) < 32 or ord(char) == 127 for char in snapshot)
                    or not Path(snapshot).is_absolute()
                    or not re.fullmatch(r"central-ai-input-[A-Za-z0-9_-]{1,128}", Path(snapshot).name)
                    or not isinstance(container, str)
                    or not re.fullmatch(r"central-ai-verifier-[0-9a-f]{32}", container)):
                raise ValueError("INVALID_VERIFIER_RESULT")
            if {"snapshot_directory": snapshot, "container_name": container} != recorded_resources:
                raise ValueError("INVALID_VERIFIER_RESULT")
            # Keep the operator's recovery handles; never delete resources from a report.
            quarantine = {"snapshot_directory": snapshot, "container_name": container}
        report = {
            "task_id": task_id,
            "candidate_sha256": prepared["candidate_sha256"],
            "test_sha256": trusted_test_sha256,
            "reviewer_id": receipt["reviewer_id"],
            "authorization_id": receipt["authorization_id"],
            "verification_nonce": binding["nonce"],
            "verification_binding": dict(binding),
            "test_status": status,
            "tests_passed": result["passed"],
            "completion_confirmed": result["completion_confirmed"],
            "execution_policy": result["execution_policy"],
            "quarantine_required": status == "cleanup_unconfirmed",
            "quarantine_resources": quarantine,
            "approved": False,
            "deployment_allowed": False,
        }
        stage = "persistence"
        storage.complete_verification(task_id, nonce, report)
        return dict(report, audit_recorded=True)
    except BaseException as error:
        try:
            storage.fail_verification(task_id, nonce, stage, type(error).__name__)
        except Exception:
            # Never return success when the audit cannot be completed. A durable
            # preparing/running intent remains blocking after write uncertainty.
            raise RuntimeError("VERIFICATION_AUDIT_WRITE_FAILED") from None
        raise
