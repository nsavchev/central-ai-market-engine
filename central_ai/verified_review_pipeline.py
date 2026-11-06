"""AI-26: opt-in gate from reviewed candidate to existing isolated verifier.

No automatic retries or deployment. Tests are operator-supplied and kept separate.
"""
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from central_ai.task_storage import TaskStorage
from central_ai.review_pipeline import prepare_review_pipeline
from central_ai.isolated_functional_verifier import run_functional_tests


def prepare_and_verify(*, enabled, database, task_id, handoffs, proposals,
                       candidates, recommendation=None, trusted_test_file, image,
                       trusted_test_sha256=None, authorization_check=None,
                       verifier=run_functional_tests, generator=None, generator_id=None,
                       generation_authorization_check=None):
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
    if generator is not None and (not callable(generator) or recommendation is not None
            or not isinstance(generator_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', generator_id)):
        raise ValueError("INVALID_GENERATOR_CONFIGURATION")
    if generator is None and generator_id is not None:
        raise ValueError("INVALID_GENERATOR_CONFIGURATION")
    if generator is not None and not callable(generation_authorization_check):
        raise ValueError("GENERATION_AUTHORIZATION_REQUIRED")
    db = Path(database)
    if not db.is_absolute() or not db.is_file() or db.is_symlink():
        raise ValueError("INVALID_TASK_DB")
    storage = TaskStorage(db)
    nonce = secrets.token_hex(16)
    storage.begin_verification(task_id, nonce)
    stage = "generation" if generator is not None else "preparation"
    try:
        if generator is not None:
            request = storage.begin_generation(task_id, nonce, generator_id, trusted_test_sha256, image)
            stage = "generation_authorization"
            receipt = generation_authorization_check(dict(request['binding']))
            request['admission'] = storage.authorize_generation(task_id, nonce, receipt)
            admission_sha256 = request['admission']['admission_sha256']
            # Expiry is a dispatch deadline; it is not an upstream cancellation guarantee.
            if datetime.now(timezone.utc) >= datetime.fromisoformat(request['admission']['expires_at']):
                raise ValueError('GENERATION_ADMISSION_EXPIRED')
            stage = "generation"
            recommendation = generator(request)
            storage.complete_generation(task_id, nonce, recommendation, admission_sha256)
        stage = "preparation"
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


def make_worker_review_handler(*, enabled, database, jobs, generator, generator_id,
                               generation_authorization_check, authorization_check,
                               verifier=run_functional_tests):
    """Trusted-host opt-in wiring; no environment defaults or task auto-approval.

    jobs freezes an explicit task-ID allowlist and independent harness/output
    configuration. Analysis completion is durable before review begins; pending
    allowlisted analyses can therefore resume after a process restart. Existing
    preparing/running/quarantined intents block instead of resending a request.
    """
    import json
    import sqlite3
    from uuid import UUID
    fields = {'handoffs','proposals','candidates','trusted_test_file','trusted_test_sha256','image'}
    db = Path(database)
    if (enabled != 'YES' or not db.is_absolute() or not db.is_file() or db.is_symlink()
            or not callable(generator) or not callable(generation_authorization_check)
            or not callable(authorization_check) or not callable(verifier)
            or not isinstance(generator_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', generator_id)
            or not isinstance(jobs, dict) or not 1 <= len(jobs) <= 100):
        raise ValueError('WORKER_REVIEW_NOT_CONFIGURED')
    captured = {}
    for task_id, config in jobs.items():
        if (not isinstance(task_id, str) or not isinstance(config, dict) or set(config) != fields
                or any(not isinstance(value, str) or not value for value in config.values())):
            raise ValueError('INVALID_WORKER_REVIEW_JOB')
        try:
            if str(UUID(task_id)) != task_id:
                raise ValueError('INVALID_WORKER_REVIEW_JOB')
        except (ValueError, AttributeError):
            raise ValueError('INVALID_WORKER_REVIEW_JOB') from None
        if (not re.fullmatch(r'[0-9a-f]{64}', config['trusted_test_sha256'])
                or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}', config['image'])
                or any(not Path(config[key]).is_absolute() for key in fields-{'trusted_test_sha256','image'})):
            raise ValueError('INVALID_WORKER_REVIEW_JOB')
        captured[task_id] = dict(config)

    def review(task_id):
        if task_id not in captured:
            raise ValueError('WORKER_REVIEW_TASK_NOT_ALLOWED')
        return prepare_and_verify(enabled='YES', database=str(db), task_id=task_id,
            generator=generator, generator_id=generator_id,
            generation_authorization_check=generation_authorization_check,
            authorization_check=authorization_check, verifier=verifier, **captured[task_id])

    def next_task_id():
        with sqlite3.connect(str(db), timeout=10) as conn:
            rows = [(task_id, json.loads(payload)) for task_id, payload in conn.execute(
                'SELECT task_id,payload FROM tasks ORDER BY created_at,task_id')]
            # Global unresolved intents remain a barrier, including tasks outside
            # this handler's allowlist. No new retry/lease/recovery mechanism.
            TaskStorage.check_verification_barrier(task for _, task in rows)
            for task_id, task in rows:
                if task_id in captured and task.get('status') == 'analyzed' and 'verification' not in task:
                    TaskStorage(db)._review_task(conn, task_id)
                    return task_id
        return None

    review.database = str(db)
    review.accepts = lambda task_id: task_id in captured
    review.next_task_id = next_task_id
    return review
