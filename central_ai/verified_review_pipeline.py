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


def load_worker_review_config(*, enabled, config_path, database, validation_only=False):
    """Strict trusted-host runtime policy; review-only profiles are rejected.

    Credentials and policy must be provisioned outside task/artifact storage.
    This loader neither creates a ledger/key/task nor activates a service.
    """
    import hashlib,hmac,json,os,sqlite3,time
    from datetime import timedelta
    from uuid import UUID
    from central_ai.verifier_gate import read_private_host_file,make_hmac_review_authorizer
    from central_ai.isolated_functional_verifier import _read_input
    from central_ai.app import make_openai_generator
    if enabled!='YES' or type(validation_only) is not bool:
        raise ValueError('WORKER_REVIEW_CONFIG_DISABLED')
    db=Path(database)
    if not db.is_absolute() or db.is_symlink() or not db.is_file() or db.resolve()!=db:
        raise ValueError('TASK_DB_UNAVAILABLE')
    def reject():raise ValueError('WORKER_REVIEW_CONFIG_INVALID')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:reject()
            result[key]=value
        return result
    def constant(value):reject()
    config=json.loads(read_private_host_file(config_path,max_bytes=256*1024),
                      object_pairs_hook=pairs,parse_constant=constant)
    fields={'schema','scope','execution_policy','execution_authorized','approved','deployment_allowed','database','policy_id',
            'model','max_output_tokens','budget','authority','runtime_sha256','jobs'}
    if (not isinstance(config,dict) or set(config)!=fields
            or config['schema']!='worker-review-runtime-v1' or config['scope']!='isolated_only'
            or config['execution_policy']!='bounded-arithmetic-v1'
            or type(config['execution_authorized']) is not bool
            or (not validation_only and config['execution_authorized'] is not True)
            or config['approved'] is not False or config['deployment_allowed'] is not False
            or config['database']!=str(db) or config['model']!='gpt-4.1-mini'
            or type(config['max_output_tokens']) is not int or not 1<=config['max_output_tokens']<=128
            or not isinstance(config['policy_id'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',config['policy_id'])):
        reject()
    budget=config['budget'];authority=config['authority']
    if (not isinstance(budget,dict) or set(budget)!={'currency','limit_microusd','reserved_microusd','call_limit'}
            or budget['currency']!='USD'
            or any(type(budget[k]) is not int for k in ('limit_microusd','reserved_microusd','call_limit'))
            or not 1<=budget['reserved_microusd']<=budget['limit_microusd']<=10**12
            or budget['call_limit']!=1
            or not isinstance(authority,dict) or set(authority)!={'generation_id','reviewer_id','reviewer_key_file'}
            or not isinstance(authority.get('reviewer_key_file'),str)
            or any(not isinstance(authority[k],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',authority[k])
                   for k in ('generation_id','reviewer_id'))):
        reject()
    core={'app.py','task_storage.py','verified_review_pipeline.py','verifier_gate.py',
          'developer_worker_coordinator.py','worker_batch.py','worker_scheduler.py','worker_supervised.py'}
    hashes=config['runtime_sha256']
    if not isinstance(hashes,dict) or set(hashes)!=core:reject()
    for name,digest in hashes.items():
        if (not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)
                or hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()!=digest):
            raise ValueError('WORKER_REVIEW_RUNTIME_CHANGED')
    key_path=Path(authority['reviewer_key_file'])
    if key_path.is_relative_to(db.parent) or Path(config_path).is_relative_to(db.parent):
        raise ValueError('WORKER_REVIEW_AUTHORITY_INSIDE_STATE')
    key=read_private_host_file(key_path,max_bytes=128)
    if not 32<=len(key)<=128:reject()
    grants=config['jobs']
    if not isinstance(grants,dict) or not 1<=len(grants)<=100:reject()
    job_fields={'handoffs','proposals','candidates','trusted_test_file','trusted_test_sha256','image'}
    jobs={}
    # Read-only inspection cannot create/backfill tasks, targets or budgets.
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=10) as conn:
        conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
        for task_id,grant in grants.items():
            if (not isinstance(task_id,str) or str(UUID(task_id))!=task_id or not isinstance(grant,dict)
                    or set(grant)!=job_fields|{'source_file','source_sha256','spec_sha256'}
                    or any(not isinstance(v,str) or not v for v in grant.values())):reject()
            if (not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}',grant['image'])
                    or any(not Path(grant[field]).is_absolute() or Path(grant[field]).resolve()!=Path(grant[field])
                           for field in ('source_file','trusted_test_file','handoffs','proposals','candidates'))
                    or any(not Path(grant[field]).is_dir() or Path(grant[field]).stat().st_mode & 0o022
                           for field in ('handoffs','proposals','candidates'))):
                reject()
            row=conn.execute('SELECT payload FROM tasks WHERE task_id=?',(task_id,)).fetchone()
            target=conn.execute('SELECT workspace,filename,approved,deployment_allowed FROM task_file_targets WHERE task_id=?',(task_id,)).fetchone()
            if row is None or target is None or target[2:]!=(0,0):reject()
            task=json.loads(row[0])
            source=Path(grant['source_file'])
            if (not source.is_absolute() or source.resolve()!=source
                    or source!=(Path(target[0])/target[1])
                    or hashlib.sha256(_read_input(source)).hexdigest()!=grant['source_sha256']
                    or hashlib.sha256(task['task']['task'].encode()).hexdigest()!=grant['spec_sha256']
                    or task.get('approved') is not False or task.get('deployment_allowed') is not False
                    or task['task'].get('approved') is not False or task['task'].get('deployment_allowed') is not False
                    or hashlib.sha256(_read_input(Path(grant['trusted_test_file']))).hexdigest()!=grant['trusted_test_sha256']):
                raise ValueError('WORKER_REVIEW_GRANT_CHANGED')
            for area in [Path(grant[field]) for field in ('handoffs','proposals','candidates')]+[source.parent]:
                if key_path.is_relative_to(area) or Path(config_path).is_relative_to(area):
                    raise ValueError('WORKER_REVIEW_AUTHORITY_INSIDE_ARTIFACTS')
            jobs[task_id]={field:grant[field] for field in job_fields}
    if validation_only:
        return dict(config_validated=True,validation_only=True,
            execution_authorized=config['execution_authorized'],reviewer_key_loaded=True,
            task_grants=len(jobs),generation_started=False,worker_started=False,
            provider_key_verified=False,database_modified=False)
    def admit(binding):
        grant=grants.get(binding.get('task_id'))
        if (grant is None or binding.get('source_sha256')!=grant['source_sha256']
                or binding.get('spec_sha256')!=grant['spec_sha256'] or binding.get('test_sha256')!=grant['trusted_test_sha256']
                or binding.get('image')!=grant['image'] or binding.get('provider_id')!='openai-bounded-v1'
                or binding.get('root_task_id')!=binding.get('task_id')
                or type(binding.get('ordinal')) is not int or binding.get('ordinal')!=1):
            raise ValueError('WORKER_REVIEW_GENERATION_DENIED')
        now=datetime.now(timezone.utc)
        return dict(schema='generation-admission-usd-v2',generation_authorized=True,binding=dict(binding),
            scope='generate_only',disclosure='task_description_only',
            authorization_id=authority['generation_id']+':'+binding['nonce'],budget_period=now.strftime('%Y-%m'),
            budget_limit_microusd=budget['limit_microusd'],reserved_microusd=budget['reserved_microusd'],
            budget_call_limit=budget['call_limit'],model=config['model'],max_output_tokens=config['max_output_tokens'],
            expires_at=(now+timedelta(seconds=60)).isoformat(),approved=False,deployment_allowed=False)
    def issue(binding):
        grant=grants.get(binding.get('task_id'))
        if grant is None or binding.get('test_sha256')!=grant['trusted_test_sha256'] or binding.get('image')!=grant['image']:
            raise ValueError('WORKER_REVIEW_VERIFICATION_DENIED')
        now=int(time.time())
        receipt=dict(schema='review-hmac-sha256-v1',binding=dict(binding),reviewer_id=authority['reviewer_id'],
            authorization_id=config['policy_id']+':'+binding['nonce'],issued_at=now,expires_at=now+60,
            verification_authorized=True,approved=False,deployment_allowed=False)
        payload=json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        return dict(receipt,mac=hmac.new(key,payload,'sha256').hexdigest())
    authorize=make_hmac_review_authorizer(reviewer_keys={authority['reviewer_id']:key},request_receipt=issue)
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError('WORKER_REVIEW_PROVIDER_NOT_CONFIGURED')
    generator=make_openai_generator(enabled='YES',database=str(db))
    return make_worker_review_handler(enabled='YES',database=str(db),jobs=jobs,generator=generator,
        generator_id=generator.generator_id,generation_authorization_check=admit,authorization_check=authorize)
