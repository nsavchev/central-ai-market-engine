import pytest
from central_ai.verified_review_pipeline import prepare_and_verify


def generation_admission_fixture(binding):
    """Synthetic host decision only; not a production authority or real price."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    return dict(schema='generation-admission-v1', generation_authorized=True,
        binding=dict(binding), scope='generate_only', disclosure='task_description_only',
        authorization_id='ci-'+binding['nonce'], budget_period=now.strftime('%Y-%m'),
        budget_limit_microuros=1000000, budget_call_limit=100, reserved_microuros=1000,
        model='ci-fixture-model', max_output_tokens=100,
        expires_at=(now+timedelta(minutes=1)).isoformat(), approved=False, deployment_allowed=False)


def record_fixture_resources(kwargs):
    """Synthetic host-verifier contract, not a claim that Docker was invoked."""
    kwargs['record_resources']({'snapshot_directory':'/tmp/central-ai-input-ci-fixture',
                                'container_name':'central-ai-verifier-'+'f'*32})


def analyzed_task(tmp_path):
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / 'tasks.sqlite'
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'sample.py').write_text('def sample():\n    return 1\n')
    bridge = PersistentTaskBridge(database)
    task_id = bridge.submit('Synthetic verification audit fixture')['task_id']
    targets = TaskFileTargets(database)
    targets.initialize()
    targets.register(task_id, str(source), 'sample.py')
    assert run_batch(enabled='YES', database=str(database), agent='ci-audit',
                     max_tasks=1, idle_checks=1, sleep=lambda _: None)['processed'] == 1
    return str(database), task_id


def test_disabled_pipeline_does_not_call_verifier():
    def fail(**kwargs):
        raise AssertionError("should not execute")
    with pytest.raises(ValueError, match="PIPELINE_VERIFICATION_DISABLED"):
        prepare_and_verify(enabled="",database="",task_id="",handoffs="",
                           proposals="",candidates="",recommendation="",
                           trusted_test_file="",image="",verifier=fail)



def test_enabled_pipeline_requires_independent_test_digest_before_preparation():
    def forbidden(**kwargs):
        raise AssertionError("should not execute")
    with pytest.raises(ValueError,match="INVALID_TEST_HASH"):
        prepare_and_verify(enabled="YES",database="",task_id="",handoffs="",
                           proposals="",candidates="",recommendation="",
                           trusted_test_file="",image="",verifier=forbidden)



def test_no_authorizer_fails_before_preparation(monkeypatch):
    import central_ai.verified_review_pipeline as pipeline
    def forbidden(**kwargs):
        raise AssertionError("must not prepare or execute")
    monkeypatch.setattr(pipeline,"prepare_review_pipeline",forbidden)
    with pytest.raises(ValueError,match="REVIEW_AUTHORIZATION_REQUIRED"):
        pipeline.prepare_and_verify(enabled="YES",database="",task_id="",handoffs="",
            proposals="",candidates="",recommendation="",trusted_test_file="",
            trusted_test_sha256="b"*64,image="",verifier=forbidden)


@pytest.mark.parametrize("change", [
    "denied","task_id","candidate_sha256","test_sha256","image","nonce","scope",
    "approved","deployment_allowed","reviewer_id","authorization_id","mutate_request",
])
def test_authorization_denial_never_calls_verifier(monkeypatch,change,tmp_path):
    database, task_id = analyzed_task(tmp_path)
    import central_ai.verified_review_pipeline as pipeline
    monkeypatch.setattr(pipeline,"prepare_review_pipeline",lambda **kw:
        {"candidate_path":"/ci/candidate.py","candidate_sha256":"a"*64})
    def authorizer(binding):
        receipt={"verification_authorized":True,"binding":dict(binding),
                 "reviewer_id":"ci-reviewer","authorization_id":"ci-decision",
                 "approved":False,"deployment_allowed":False}
        if change=="denied":
            receipt["verification_authorized"]=False
        elif change in ("approved","deployment_allowed"):
            receipt[change]=True
        elif change in ("reviewer_id","authorization_id"):
            receipt[change]=""
        elif change=="mutate_request":
            binding["candidate_sha256"]="f"*64
            receipt["binding"]=binding
        else:
            receipt["binding"][change]="different"
        return receipt
    def forbidden(**kw):
        raise AssertionError("verifier must not execute")
    with pytest.raises(ValueError,match="REVIEW_AUTHORIZATION_DENIED"):
        pipeline.prepare_and_verify(enabled="YES",database=database,task_id=task_id,handoffs="",
            proposals="",candidates="",recommendation="",trusted_test_file="/ci/test.py",
            trusted_test_sha256="b"*64,image="python@sha256:"+"c"*64,
            authorization_check=authorizer,verifier=forbidden)


def test_previous_receipt_cannot_authorize_new_invocation(monkeypatch,tmp_path):
    database, task_id = analyzed_task(tmp_path / "first")
    import central_ai.verified_review_pipeline as pipeline
    monkeypatch.setattr(pipeline,"prepare_review_pipeline",lambda **kw:
        {"candidate_path":"/ci/candidate.py","candidate_sha256":"a"*64})
    nonces=iter(["1"*32,"2"*32])
    monkeypatch.setattr(pipeline.secrets,"token_hex",lambda size:next(nonces))
    receipts=[]
    executions=[]
    def authorizer(binding):
        if not receipts:
            receipts.append({"verification_authorized":True,"binding":binding,
                "reviewer_id":"ci-reviewer","authorization_id":"ci-decision",
                "approved":False,"deployment_allowed":False})
        return receipts[0]
    def verifier(**kw):
        record_fixture_resources(kw)
        executions.append(kw)
        return valid_result()
    params=dict(enabled="YES",database=database,task_id=task_id,handoffs="",proposals="",
        candidates="",recommendation="",trusted_test_file="/ci/test.py",
        trusted_test_sha256="b"*64,image="python@sha256:"+"c"*64,
        authorization_check=authorizer,verifier=verifier)
    report=pipeline.prepare_and_verify(**params)
    assert report["approved"] is False and report["deployment_allowed"] is False
    with pytest.raises(ValueError,match="REVIEW_AUTHORIZATION_DENIED"):
        second_database, second_task = analyzed_task(tmp_path / "second")
        pipeline.prepare_and_verify(**dict(params, database=second_database, task_id=second_task))
    assert len(executions)==1



def signed_review_fixture(request_binding, key, **changes):
    """Synthetic CI receipt; no real reviewer key is provisioned."""
    import json,hmac
    receipt={"schema":"review-hmac-sha256-v1","binding":request_binding,"reviewer_id":"ci-reviewer",
        "authorization_id":"ci-only","issued_at":1000,"expires_at":1100,
        "verification_authorized":True,"approved":False,"deployment_allowed":False}
    receipt.update(changes)
    payload=json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return dict(receipt,mac=hmac.new(key,payload,"sha256").hexdigest())


@pytest.mark.parametrize("case,error", [
    ("tamper","REVIEW_MAC_MISMATCH"),("wrong_key","REVIEW_MAC_MISMATCH"),
    ("unknown","UNKNOWN_REVIEWER"),("expired","REVIEW_RECEIPT_EXPIRED"),
    ("future","REVIEW_RECEIPT_EXPIRED"),("long_lifetime","REVIEW_RECEIPT_EXPIRED"),
    ("bool_time","REVIEW_RECEIPT_EXPIRED"),("binding","REVIEW_AUTHORIZATION_DENIED"),
    ("deployment","REVIEW_AUTHORIZATION_DENIED"),("bad_mac","INVALID_REVIEW_MAC"),
])
def test_hmac_review_rejects_invalid_receipts(case,error):
    import secrets
    from central_ai.verifier_gate import make_hmac_review_authorizer
    key=secrets.token_bytes(32)
    binding={"schema":"verification-request-v1","nonce":"1"*32,"task_id":"ci-task",
             "candidate_sha256":"a"*64,"test_sha256":"b"*64,"image":"python@sha256:"+"c"*64,"scope":"verify_only"}
    def transport(request):
        changes={}
        if case=="unknown":changes["reviewer_id"]="unconfigured"
        elif case=="expired":changes.update(issued_at=900,expires_at=1000)
        elif case=="future":changes.update(issued_at=1060,expires_at=1100)
        elif case=="long_lifetime":changes["expires_at"]=1400
        elif case=="bool_time":changes["issued_at"]=True
        elif case=="binding":changes["binding"]=dict(request,nonce="2"*32)
        elif case=="deployment":changes["deployment_allowed"]=True
        receipt=signed_review_fixture(request,secrets.token_bytes(32) if case=="wrong_key" else key,**changes)
        if case=="tamper":receipt["authorization_id"]="tampered"
        if case=="bad_mac":receipt["mac"]="not-a-mac"
        return receipt
    authorize=make_hmac_review_authorizer(reviewer_keys={"ci-reviewer":key},request_receipt=transport,clock=lambda:1050)
    with pytest.raises(ValueError,match=error):
        authorize(binding)


def test_hmac_adapter_in_existing_pipeline(monkeypatch,tmp_path):
    database, task_id = analyzed_task(tmp_path)
    import secrets
    import central_ai.verified_review_pipeline as pipeline
    from central_ai.verifier_gate import make_hmac_review_authorizer
    key=secrets.token_bytes(32)
    keys={"ci-reviewer":key}
    authorize=make_hmac_review_authorizer(reviewer_keys=keys,
        request_receipt=lambda binding:signed_review_fixture(binding,key),clock=lambda:1050)
    keys.clear()  # The adapter captured trusted configuration, not a mutable caller map.
    monkeypatch.setattr(pipeline,"prepare_review_pipeline",lambda **kw:
        {"candidate_path":"/ci/candidate.py","candidate_sha256":"a"*64})
    calls=[]
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        calls.append(kwargs)
        return valid_result()
    result=pipeline.prepare_and_verify(enabled="YES",database=database,task_id=task_id,handoffs="",
        proposals="",candidates="",recommendation="",trusted_test_file="/ci/test.py",
        trusted_test_sha256="b"*64,image="python@sha256:"+"c"*64,
        authorization_check=authorize,verifier=verifier)
    assert len(calls)==1 and result["reviewer_id"]=="ci-reviewer"
    assert result["approved"] is False and result["deployment_allowed"] is False


def test_hmac_authorizer_has_no_default_keys():
    from central_ai.verifier_gate import make_hmac_review_authorizer
    with pytest.raises(ValueError,match="REVIEW_AUTHORIZER_NOT_CONFIGURED"):
        make_hmac_review_authorizer(reviewer_keys={},request_receipt=lambda request:None)
    with pytest.raises(ValueError,match="INVALID_REVIEWER_KEYS"):
        make_hmac_review_authorizer(reviewer_keys={"weak":b"short"},request_receipt=lambda request:None)


def verification_fixture(monkeypatch, result, tmp_path):
    database, task_id = analyzed_task(tmp_path)
    import central_ai.verified_review_pipeline as pipeline
    monkeypatch.setattr(pipeline, 'prepare_review_pipeline', lambda **kwargs:
        {'candidate_path': '/ci/candidate.py', 'candidate_sha256': 'a'*64})
    def authorize(binding):
        return {'verification_authorized': True, 'binding': dict(binding),
                'reviewer_id': 'ci-reviewer', 'authorization_id': 'ci-only',
                'approved': False, 'deployment_allowed': False}
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        return {'execution_policy':'bounded-arithmetic-v1', 'completion_confirmed':result.get('passed',False), **result}
    return dict(enabled='YES', database=database, task_id=task_id, handoffs='', proposals='',
                candidates='', recommendation='', trusted_test_file='/ci/test.py',
                trusted_test_sha256='b'*64, image='python@sha256:'+'c'*64,
                authorization_check=authorize, verifier=verifier,
                generation_authorization_check=generation_admission_fixture)


def valid_result(**changes):
    result = dict(passed=True, status='passed', executed_candidate=True,
                  execution_policy='bounded-arithmetic-v1', completion_confirmed=True,
                  test_sha256='b'*64, returncode=0)
    result.update(changes)
    if 'passed' in changes and 'completion_confirmed' not in changes:
        result['completion_confirmed'] = changes['passed']
    return result


@pytest.mark.parametrize('result', [
    valid_result(status='cleanup_unconfirmed'), valid_result(status='timeout'),
    valid_result(status='failed'), valid_result(passed=False), valid_result(status='unknown'),
    valid_result(executed_candidate=False), valid_result(returncode=1),
    valid_result(returncode=True), valid_result(test_sha256='d'*64),
    valid_result(approved=True), valid_result(deployment_allowed=True),
    {'passed': True, 'status': 'passed'},
])
def test_inconsistent_or_unbound_verifier_result_never_reports_success(monkeypatch, result, tmp_path):
    params = verification_fixture(monkeypatch, result, tmp_path)
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)


def test_floating_image_is_rejected_before_artifacts_or_authorization(monkeypatch, tmp_path):
    import central_ai.verified_review_pipeline as pipeline
    calls = []
    monkeypatch.setattr(pipeline, 'prepare_review_pipeline', lambda **kwargs: calls.append('prepare'))
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    monkeypatch.setattr(pipeline, 'prepare_review_pipeline', lambda **kwargs: calls.append('prepare'))
    params['image'] = 'python:latest'
    params['authorization_check'] = lambda binding: calls.append('authorize')
    with pytest.raises(ValueError, match='UNPINNED_IMAGE'):
        prepare_and_verify(**params)
    assert calls == []


def test_cleanup_uncertainty_preserves_operator_resources_and_binding(monkeypatch, tmp_path):
    resources = {'snapshot_directory': '/tmp/central-ai-input-ci-fixture',
                 'container_name': 'central-ai-verifier-'+'f'*32}
    params = verification_fixture(monkeypatch, dict(status='cleanup_unconfirmed', passed=False,
                                                   executed_candidate=True, **resources), tmp_path)
    report = prepare_and_verify(**params)
    assert report['test_status'] == 'cleanup_unconfirmed' and report['tests_passed'] is False
    assert report['quarantine_required'] is True
    assert report['quarantine_resources'] == resources
    assert report['verification_binding']['image'] == params['image']
    assert report['verification_binding']['test_sha256'] == params['trusted_test_sha256']
    assert report['verification_binding']['nonce'] == report['verification_nonce']
    assert report['approved'] is report['deployment_allowed'] is False


@pytest.mark.parametrize('resources', [
    {}, {'snapshot_directory': 'relative', 'container_name': 'unexpected'},
    {'snapshot_directory': '/tmp/central-ai-input-ci-fixture', 'container_name': 'production'},
])
def test_cleanup_uncertainty_requires_identifiable_quarantine_resources(monkeypatch, resources, tmp_path):
    params = verification_fixture(monkeypatch, dict(status='cleanup_unconfirmed', passed=False,
                                                   executed_candidate=True, **resources), tmp_path)
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)


@pytest.mark.parametrize('result', [
    valid_result(), valid_result(status='failed', passed=False, returncode=1),
    {'status': 'timeout', 'passed': False, 'executed_candidate': True},
])
def test_consistent_terminal_results_preserve_bound_report(monkeypatch, result, tmp_path):
    params = verification_fixture(monkeypatch, result, tmp_path)
    report = prepare_and_verify(**params)
    assert report['tests_passed'] is result['passed']
    assert report['test_status'] == result['status']
    assert report['quarantine_required'] is False and report['quarantine_resources'] is None
    assert report['verification_binding']['candidate_sha256'] == 'a'*64


def test_verification_outcome_is_durable_and_cannot_execute_twice(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    report = prepare_and_verify(**params)
    saved = TaskStorage(params['database']).get(params['task_id'])
    assert saved['status'] == 'analyzed'
    audit = saved['verification']
    assert audit['phase'] == 'completed'
    assert audit['outcome']['verification_binding'] == report['verification_binding']
    assert audit['outcome']['reviewer_id'] == report['reviewer_id']
    assert audit['outcome']['tests_passed'] is True
    assert report['audit_recorded'] is True
    params['verifier'] = lambda **kwargs: pytest.fail('duplicate execution')
    with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params)


def test_authorization_and_running_intent_are_stored_before_dispatch(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def inspect_before_execution(**kwargs):
        audit = TaskStorage(params['database']).get(params['task_id'])['verification']
        assert audit['phase'] == 'running'
        assert audit['binding']['candidate_sha256'] == kwargs['expected_sha256']
        assert audit['binding']['test_sha256'] == kwargs['expected_test_sha256']
        assert audit['binding']['image'] == kwargs['image']
        assert audit['reviewer_id'] == 'ci-reviewer'
        assert audit['authorization_id'] == 'ci-only'
        record_fixture_resources(kwargs)
        return valid_result()
    params['verifier'] = inspect_before_execution
    prepare_and_verify(**params)


def test_durable_quarantine_blocks_other_tasks_even_with_different_artifact_directories(monkeypatch, tmp_path):
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    result = dict(status='cleanup_unconfirmed', passed=False, executed_candidate=True,
                  snapshot_directory='/tmp/central-ai-input-ci-fixture',
                  container_name='central-ai-verifier-'+'f'*32)
    params = verification_fixture(monkeypatch, result, tmp_path)
    report = prepare_and_verify(**params)
    stored = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert stored['phase'] == 'quarantined'
    assert stored['outcome']['quarantine_resources'] == report['quarantine_resources']
    bridge = PersistentTaskBridge(params['database'])
    second = bridge.submit('Second synthetic verification task')['task_id']
    TaskFileTargets(params['database']).register(second, str(tmp_path/'source'), 'sample.py')
    assert run_batch(enabled='YES', database=params['database'], agent='ci-second', max_tasks=1,
                     idle_checks=1, sleep=lambda _: None)['processed'] == 1
    params.update(task_id=second, handoffs='/ci/new-handoffs', candidates='/ci/new-candidates',
                  verifier=lambda **kwargs: pytest.fail('must remain quarantined'))
    with pytest.raises(ValueError, match='VERIFICATION_DATABASE_BLOCKED'):
        prepare_and_verify(**params)


def test_crashed_running_intent_survives_process_exit_and_blocks_resubmission(tmp_path):
    import subprocess
    import sys
    from central_ai.task_storage import TaskStorage
    database, task_id = analyzed_task(tmp_path)
    script = '''from central_ai.task_storage import TaskStorage
import sys
store=TaskStorage(sys.argv[1])
store.begin_verification(sys.argv[2], 'a'*32)
store.authorize_verification(sys.argv[2], 'a'*32,
    {'schema':'verification-request-v1','nonce':'a'*32,'task_id':sys.argv[2],
     'candidate_sha256':'b'*64,'test_sha256':'c'*64,'image':'python@sha256:'+'d'*64,'scope':'verify_only'},
    'ci-reviewer','ci-only')
import os
os._exit(7)
'''
    child = subprocess.run([sys.executable, '-c', script, database, task_id], timeout=15)
    assert child.returncode == 7
    store = TaskStorage(database)
    assert store.get(task_id)['verification']['phase'] == 'running'
    with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
        store.begin_verification(task_id, 'b'*32)


@pytest.mark.parametrize('error_class', [RuntimeError, KeyboardInterrupt])
def test_verifier_exception_is_quarantined_without_persisting_raw_error(monkeypatch, tmp_path, error_class):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def broken(**kwargs):
        raise error_class('synthetic-secret-must-not-enter-audit')
    params['verifier'] = broken
    with pytest.raises(error_class, match='synthetic-secret'):
        prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'quarantined'
    assert audit['error_type'] == error_class.__name__
    assert 'synthetic-secret' not in str(audit)


def test_denied_authorization_is_durably_blocked_without_verifier_call(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    params['authorization_check'] = lambda binding: {'verification_authorized': False}
    params['verifier'] = lambda **kwargs: pytest.fail('unauthorized execution')
    with pytest.raises(ValueError, match='REVIEW_AUTHORIZATION_DENIED'):
        prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'blocked' and audit['error_stage'] == 'authorization'


def test_concurrent_verification_claims_have_only_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from central_ai.task_storage import TaskStorage
    database, task_id = analyzed_task(tmp_path)
    stores = [TaskStorage(database), TaskStorage(database)]
    barrier = Barrier(2)
    def contend(index):
        barrier.wait(timeout=5)
        try:
            stores[index].begin_verification(task_id, str(index+1)*32)
            return True
        except ValueError as error:
            assert str(error) == 'VERIFICATION_ALREADY_STARTED'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(contend, range(2)))
    assert sum(outcomes) == 1


def test_audit_binding_write_failure_prevents_dispatch(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def cannot_bind(*args, **kwargs):
        raise OSError('synthetic write failure')
    monkeypatch.setattr(TaskStorage, 'authorize_verification', cannot_bind)
    params['verifier'] = lambda **kwargs: pytest.fail('must not dispatch without durable binding')
    with pytest.raises(OSError):
        prepare_and_verify(**params)
    assert TaskStorage(params['database']).get(params['task_id'])['verification']['phase'] == 'blocked'


def test_result_write_failure_never_returns_success_and_quarantines(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def cannot_finish(*args, **kwargs):
        raise OSError('synthetic write failure')
    monkeypatch.setattr(TaskStorage, 'complete_verification', cannot_finish)
    with pytest.raises(OSError):
        prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'quarantined' and audit['error_stage'] == 'persistence'


def test_unavailable_audit_keeps_durable_running_intent_blocking(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def unavailable(*args, **kwargs):
        raise OSError('synthetic unavailable database')
    with monkeypatch.context() as context:
        context.setattr(TaskStorage, 'complete_verification', unavailable)
        context.setattr(TaskStorage, 'fail_verification', unavailable)
        with pytest.raises(RuntimeError, match='VERIFICATION_AUDIT_WRITE_FAILED'):
            prepare_and_verify(**params)
    store = TaskStorage(params['database'])
    assert store.get(params['task_id'])['verification']['phase'] == 'running'
    with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
        store.begin_verification(params['task_id'], 'b'*32)


def test_invalid_result_is_durably_quarantined_without_raw_output(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(status='cleanup_unconfirmed',
                                                           stdout='synthetic-sensitive-output'), tmp_path)
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'quarantined' and audit['error_stage'] == 'result'
    assert 'synthetic-sensitive-output' not in str(audit)


def test_successful_audit_never_persists_verifier_stdout_or_authority_flags(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(stdout='synthetic-sensitive-output'), tmp_path)
    prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert 'synthetic-sensitive-output' not in str(audit)
    assert audit['approved'] is audit['deployment_allowed'] is False
    assert audit['outcome']['approved'] is audit['outcome']['deployment_allowed'] is False


def test_two_different_task_claims_in_same_database_are_serialized(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    database, first = analyzed_task(tmp_path)
    second = PersistentTaskBridge(database).submit('Second synthetic task')['task_id']
    TaskFileTargets(database).register(second, str(tmp_path/'source'), 'sample.py')
    assert run_batch(enabled='YES', database=database, agent='ci-second', max_tasks=1,
                     idle_checks=1, sleep=lambda _: None)['processed'] == 1
    stores = [TaskStorage(database), TaskStorage(database)]
    tasks = [first, second]
    barrier = Barrier(2)
    def contend(index):
        barrier.wait(timeout=5)
        try:
            stores[index].begin_verification(tasks[index], str(index+1)*32)
            return True
        except ValueError as error:
            assert str(error) == 'VERIFICATION_DATABASE_BLOCKED'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(contend, range(2))) == 1


def test_non_analyzed_task_cannot_claim_verification(tmp_path):
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_storage import TaskStorage
    database = str(tmp_path/'tasks.sqlite')
    task_id = PersistentTaskBridge(database).submit('Unanalyzed fixture')['task_id']
    store = TaskStorage(database)
    with pytest.raises(ValueError, match='VERIFICATION_TASK_NOT_READY'):
        store.begin_verification(task_id, 'a'*32)
    assert 'verification' not in store.get(task_id)


def test_success_without_resource_intent_is_rejected(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    params['verifier'] = lambda **kwargs: valid_result()
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)
    assert TaskStorage(params['database']).get(params['task_id'])['verification']['phase'] == 'quarantined'


@pytest.mark.parametrize('change', ['path', 'name', 'overwrite'])
def test_resource_intent_is_validated_and_cannot_be_replaced(monkeypatch, tmp_path, change):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    def verifier(**kwargs):
        resources = {'snapshot_directory':'/tmp/central-ai-input-ci-fixture',
                     'container_name':'central-ai-verifier-'+'f'*32}
        if change == 'path':
            resources['snapshot_directory'] = '/unrelated/path'
        elif change == 'name':
            resources['container_name'] = 'unrelated-container'
        else:
            kwargs['record_resources'](dict(resources))
        kwargs['record_resources'](resources)
        pytest.fail('invalid/replaced resource intent accepted')
    params['verifier'] = verifier
    with pytest.raises(ValueError, match='INVALID_VERIFICATION_RESOURCES|VERIFICATION_AUDIT_CONFLICT'):
        prepare_and_verify(**params)
    assert TaskStorage(params['database']).get(params['task_id'])['verification']['phase'] == 'quarantined'


def test_quarantine_result_cannot_replace_pre_dispatch_handles(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, dict(status='cleanup_unconfirmed', passed=False,
        executed_candidate=True, snapshot_directory='/tmp/central-ai-input-different',
        container_name='central-ai-verifier-'+'d'*32), tmp_path)
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'quarantined'
    assert audit['resources']['snapshot_directory'] == '/tmp/central-ai-input-ci-fixture'


def test_resource_intent_survives_abrupt_exit_before_docker(tmp_path):
    import subprocess
    import sys
    from central_ai.task_storage import TaskStorage
    database, task_id = analyzed_task(tmp_path)
    script = '''import hashlib, os, sys
from pathlib import Path
from central_ai.task_storage import TaskStorage
from central_ai.isolated_functional_verifier import run_functional_tests
store=TaskStorage(sys.argv[1]); task_id=sys.argv[2]; nonce='a'*32
store.begin_verification(task_id, nonce)
store.authorize_verification(task_id, nonce,
    {'schema':'verification-request-v1','nonce':nonce,'task_id':task_id,
     'candidate_sha256':'b'*64,'test_sha256':'c'*64,'image':'python@sha256:'+'d'*64,'scope':'verify_only'},
    'ci-reviewer','ci-only')
root=Path(sys.argv[1]).parent
candidate=root/'candidate.py'; candidate.write_text('def f(): return 1\\n')
test=root/'test_candidate.py'; test.write_text('assert True\\n')
def record(resources):
    store.record_verification_resources(task_id, nonce, resources)
    os._exit(9)
run_functional_tests(enabled='YES', candidate=str(candidate),
    expected_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), test_file=str(test),
    expected_test_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
    image='python@sha256:'+'d'*64, record_resources=record,
    run=lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not dispatch')))
'''
    child = subprocess.run([sys.executable, '-c', script, database, task_id], timeout=15)
    assert child.returncode == 9
    store = TaskStorage(database)
    audit = store.get(task_id)['verification']
    from pathlib import Path
    import shutil
    root = Path(audit['resources']['snapshot_directory'])
    try:
        assert audit['phase'] == 'running'
        assert root.is_dir() and (root/'candidate.py').is_file()
        assert audit['resources']['container_name'].startswith('central-ai-verifier-')
        with pytest.raises(ValueError, match='VERIFICATION_ALREADY_STARTED'):
            store.begin_verification(task_id, 'b'*32)
    finally:
        shutil.rmtree(root)  # Test-owned orphan; no Docker command was dispatched.


@pytest.mark.parametrize('change', [
    {'completion_confirmed':False}, {'completion_confirmed':1},
    {'execution_policy':'arbitrary-python'}, {'execution_policy':None},
])
def test_pass_requires_bounded_policy_and_confirmed_completion(monkeypatch, tmp_path, change):
    params = verification_fixture(monkeypatch, valid_result(**change), tmp_path)
    with pytest.raises(ValueError, match='INVALID_VERIFIER_RESULT'):
        prepare_and_verify(**params)


def test_completion_uncertainty_is_durable_failure_without_deployment(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = verification_fixture(monkeypatch, valid_result(passed=False, completion_confirmed=False,
        status='completion_unconfirmed', returncode=0), tmp_path)
    report = prepare_and_verify(**params)
    audit = TaskStorage(params['database']).get(params['task_id'])['verification']
    assert audit['phase'] == 'completed'
    assert audit['outcome']['test_status'] == 'completion_unconfirmed'
    assert report['tests_passed'] is report['completion_confirmed'] is False
    assert report['approved'] is report['deployment_allowed'] is False
    assert report['execution_policy'] == 'bounded-arithmetic-v1'


def test_generator_intent_is_durable_before_callback_and_response_is_hashed(monkeypatch,tmp_path):
    import hashlib
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path)
    params.pop('recommendation')
    answer='```python\ndef f(): return 2\n```'
    def generate(request):
        saved=TaskStorage(params['database']).get(params['task_id'])
        assert saved['generation']['phase']=='requested'
        assert saved['generation']['binding']==request['binding']
        assert saved['revision_family']['members']==[params['task_id']]
        assert request['binding']['ordinal']==1
        request['binding']['source_sha256']='tampered'
        return answer
    prepare_and_verify(**params,generator=generate,generator_id='ci-synthetic')
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['phase']=='completed'
    assert saved['generation']['response_sha256']==hashlib.sha256(answer.encode()).hexdigest()
    assert saved['generation']['binding']['source_sha256']!='tampered'
    assert answer not in str(saved['generation'])
    with pytest.raises(ValueError,match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params,generator=lambda _:pytest.fail('replay'),generator_id='ci-synthetic')


@pytest.mark.parametrize('response',[None,'','x'*12001,{'approved':True}])
def test_invalid_generated_response_is_not_authority_or_retry(monkeypatch,tmp_path,response):
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path); params.pop('recommendation')
    params['authorization_check']=lambda _:pytest.fail('must not authorize invalid response')
    with pytest.raises(ValueError,match='INVALID_GENERATED_RECOMMENDATION'):
        prepare_and_verify(**params,generator=lambda _:response,generator_id='ci-synthetic')
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['phase']=='requested'
    assert saved['verification']['phase']=='blocked'
    with pytest.raises(ValueError,match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params,generator=lambda _:pytest.fail('must not retry'),generator_id='ci-synthetic')


def test_generator_exception_keeps_intent_without_raw_exception(monkeypatch,tmp_path):
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    def fail(_): raise RuntimeError('synthetic-sensitive-key')
    with pytest.raises(RuntimeError):
        prepare_and_verify(**params,generator=fail,generator_id='ci-synthetic')
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['verification']['error_stage']=='generation'
    assert 'synthetic-sensitive-key' not in str(saved)
    assert saved['generation']['phase']=='requested'


def test_generator_cannot_replace_supplied_recommendation(monkeypatch,tmp_path):
    params=verification_fixture(monkeypatch,valid_result(),tmp_path)
    with pytest.raises(ValueError,match='INVALID_GENERATOR_CONFIGURATION'):
        prepare_and_verify(**params,generator=lambda _:pytest.fail('must not call'),generator_id='ci-synthetic')


def test_process_exit_inside_generator_preserves_one_shot_intent(monkeypatch,tmp_path):
    import multiprocessing
    import os
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    def child():
        def terminate(_): os._exit(23)
        prepare_and_verify(**params,generator=terminate,generator_id='ci-synthetic')
    process=multiprocessing.get_context('fork').Process(target=child)
    process.start();process.join(timeout=15)
    if process.is_alive(): process.terminate();process.join(timeout=5);pytest.fail('child hung')
    assert process.exitcode==23
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['phase']=='requested'
    assert saved['generation']['admission']['receipt']['reserved_microuros'] == 1000
    assert saved['generation']['admission_sha256']
    assert saved['verification']['phase']=='preparing'
    with pytest.raises(ValueError,match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params,generator=lambda _:pytest.fail('replay'),generator_id='ci-synthetic')


@pytest.mark.parametrize('kind',['denied','stale'])
def test_generated_candidate_requires_independent_current_authority(monkeypatch,tmp_path,kind):
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    def authorize(binding):
        return dict(verification_authorized=kind!='denied',binding=dict(binding,nonce='0'*32) if kind=='stale' else dict(binding),
                    reviewer_id='ci-only',authorization_id='ci-only',approved=False,deployment_allowed=False)
    params['authorization_check']=authorize
    params['verifier']=lambda **_:pytest.fail('must not dispatch')
    with pytest.raises(ValueError,match='REVIEW_AUTHORIZATION_DENIED'):
        prepare_and_verify(**params,generator=lambda _:'```python\ndef f(): return 2\n```',generator_id='ci-synthetic')
    audit=TaskStorage(params['database']).get(params['task_id'])
    assert audit['generation']['phase']=='completed' and audit['verification']['phase']=='blocked'


def test_generated_response_write_failure_never_retries_or_authorizes(monkeypatch,tmp_path):
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    params['authorization_check']=lambda _:pytest.fail('no authorization before response journal')
    def fail(*args,**kwargs): raise OSError('synthetic-sensitive-audit-error')
    with monkeypatch.context() as context:
        context.setattr(TaskStorage,'complete_generation',fail)
        with pytest.raises(OSError):
            prepare_and_verify(**params,generator=lambda _:'```python\ndef f(): return 2\n```',generator_id='ci-synthetic')
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['phase']=='requested' and saved['verification']['phase']=='blocked'
    assert 'synthetic-sensitive-audit-error' not in str(saved)
    with pytest.raises(ValueError,match='VERIFICATION_ALREADY_STARTED'):
        prepare_and_verify(**params,generator=lambda _:pytest.fail('retry'),generator_id='ci-synthetic')


def test_concurrent_requests_dispatch_generator_once(monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    calls=[]
    def generate(request): calls.append(request['binding']['nonce']);return '```python\ndef f(): return 2\n```'
    def attempt(_):
        try:
            prepare_and_verify(**params,generator=generate,generator_id='ci-synthetic')
            return True
        except ValueError as error:
            assert str(error)=='VERIFICATION_ALREADY_STARTED'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt,range(2)))==1
    assert len(calls)==1


def test_context_change_during_callback_rejects_response_commit(monkeypatch,tmp_path):
    import json
    import sqlite3
    from central_ai.task_storage import TaskStorage
    params=verification_fixture(monkeypatch,valid_result(),tmp_path);params.pop('recommendation')
    params['authorization_check']=lambda _:pytest.fail('changed task must not authorize')
    def generate(_):
        with sqlite3.connect(params['database']) as conn:
            saved=json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?',(params['task_id'],)).fetchone()[0])
            saved['task']['task']='Synthetic changed specification'
            conn.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(saved),params['task_id']))
        return '```python\ndef f(): return 2\n```'
    with pytest.raises(ValueError,match='GENERATION_AUDIT_CONFLICT'):
        prepare_and_verify(**params,generator=generate,generator_id='ci-synthetic')
    audit=TaskStorage(params['database']).get(params['task_id'])
    assert audit['generation']['phase']=='requested' and audit['verification']['phase']=='blocked'


def generation_params(monkeypatch, tmp_path):
    params = verification_fixture(monkeypatch, valid_result(), tmp_path)
    params.pop('recommendation')
    params.update(generator=lambda _: '```python\ndef f(): return 2\n```', generator_id='ci-synthetic')
    return params


def add_analyzed_generation_task(params):
    from pathlib import Path
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    task = PersistentTaskBridge(params['database']).submit('Synthetic budget continuation')
    targets = TaskFileTargets(params['database'])
    targets.initialize()
    targets.register(task['task_id'], str(Path(params['database']).parent/'source'), 'sample.py')
    assert run_batch(enabled='YES', database=params['database'], agent='ci-budget',
                     max_tasks=1, idle_checks=1, sleep=lambda _:None)['processed'] == 1
    return dict(params, task_id=task['task_id'])


def budget_authorizer(*, cap=1000000, reserve=1000, calls=100, authorization_id=None):
    def authorize(binding):
        receipt = generation_admission_fixture(binding)
        receipt.update(budget_limit_microuros=cap, reserved_microuros=reserve, budget_call_limit=calls)
        if authorization_id is not None:
            receipt['authorization_id'] = authorization_id
        return receipt
    return authorize


def test_generator_requires_separate_admission_before_journal_or_dispatch(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    params.pop('generation_authorization_check')
    params['generator'] = lambda _:pytest.fail('must not dispatch')
    with pytest.raises(ValueError, match='GENERATION_AUTHORIZATION_REQUIRED'):
        prepare_and_verify(**params)
    assert 'verification' not in TaskStorage(params['database']).get(params['task_id'])


@pytest.mark.parametrize('change', [
    {'generation_authorized':False}, {'scope':'deploy'}, {'disclosure':'workspace_contents'},
    {'approved':True}, {'deployment_allowed':True}, {'budget_limit_microuros':True},
    {'reserved_microuros':0}, {'reserved_microuros':1000001}, {'budget_call_limit':0},
    {'budget_period':'2000-01'}, {'max_output_tokens':1501}, {'model':''},
    {'expires_at':'2000-01-01T00:00:00+00:00'}, {'expires_at':'2099-01-01T00:00:00+00:00'},
])
def test_invalid_generation_admission_never_dispatches_or_reserves(monkeypatch, tmp_path, change):
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    def deny(binding):
        return dict(generation_admission_fixture(binding), **change)
    params.update(generation_authorization_check=deny, generator=lambda _:pytest.fail('must not dispatch'))
    with pytest.raises(ValueError, match='INVALID_GENERATION_ADMISSION'):
        prepare_and_verify(**params)
    task = TaskStorage(params['database']).get(params['task_id'])
    assert 'admission' not in task['generation']
    assert task['verification']['error_stage'] == 'generation_authorization'


def test_admission_binding_cannot_be_mutated_by_authorizer(monkeypatch, tmp_path):
    params = generation_params(monkeypatch, tmp_path)
    def replaced(binding):
        binding['source_sha256'] = 'f'*64
        return generation_admission_fixture(binding)
    params.update(generation_authorization_check=replaced, generator=lambda _:pytest.fail('must not dispatch'))
    with pytest.raises(ValueError, match='INVALID_GENERATION_ADMISSION'):
        prepare_and_verify(**params)


def test_reservation_is_committed_before_callback_and_reopen_preserves_it(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    def generate(request):
        task = TaskStorage(params['database']).get(params['task_id'])
        admission = task['generation']['admission']
        assert admission['receipt']['reserved_microuros'] == 1000
        assert admission['receipt']['model'] == request['admission']['model'] == 'ci-fixture-model'
        assert task['generation']['admission_sha256'] == request['admission']['admission_sha256']
        request['admission']['model'] = 'in-memory-mutation'
        return '```python\ndef f(): return 2\n```'
    params['generator'] = generate
    prepare_and_verify(**params)
    task = TaskStorage(params['database']).get(params['task_id'])
    assert task['generation']['admission']['receipt']['model'] == 'ci-fixture-model'
    assert 'Synthetic verification audit fixture' not in str(task['generation'])


def test_monthly_ceiling_survives_new_task_ids_and_failed_dispatch(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    params['generation_authorization_check'] = budget_authorizer(cap=1000, reserve=1000)
    def uncertain(_):
        raise RuntimeError('synthetic provider uncertainty')
    params['generator'] = uncertain
    with pytest.raises(RuntimeError, match='uncertainty'):
        prepare_and_verify(**params)
    assert TaskStorage(params['database']).get(params['task_id'])['generation']['admission']
    second = add_analyzed_generation_task(params)
    second['generator'] = lambda _:pytest.fail('reservation must not be refunded')
    with pytest.raises(ValueError, match='GENERATION_BUDGET_EXHAUSTED'):
        prepare_and_verify(**second)


def test_monthly_call_count_cannot_restart_with_new_task_uuid(monkeypatch, tmp_path):
    params = generation_params(monkeypatch, tmp_path)
    params['generation_authorization_check'] = budget_authorizer(calls=2)
    prepare_and_verify(**params)
    params = add_analyzed_generation_task(params)
    prepare_and_verify(**params)
    params = add_analyzed_generation_task(params)
    params['generator'] = lambda _:pytest.fail('call allowance exhausted')
    with pytest.raises(ValueError, match='GENERATION_CALL_BUDGET_EXHAUSTED'):
        prepare_and_verify(**params)


@pytest.mark.parametrize('changed', ['cap','calls'])
def test_new_task_cannot_raise_the_existing_month_policy(monkeypatch, tmp_path, changed):
    params = generation_params(monkeypatch, tmp_path)
    prepare_and_verify(**params)
    second = add_analyzed_generation_task(params)
    second.update(generation_authorization_check=budget_authorizer(
        cap=2000000 if changed=='cap' else 1000000,
        calls=200 if changed=='calls' else 100), generator=lambda _:pytest.fail('policy changed'))
    with pytest.raises(ValueError, match='GENERATION_BUDGET_POLICY_CONFLICT'):
        prepare_and_verify(**second)


def test_rebinding_used_authorization_id_to_new_task_is_replay(monkeypatch, tmp_path):
    params = generation_params(monkeypatch, tmp_path)
    params['generation_authorization_check'] = budget_authorizer(authorization_id='ci-fixed-decision')
    prepare_and_verify(**params)
    second = add_analyzed_generation_task(params)
    second['generator'] = lambda _:pytest.fail('authorization replay')
    with pytest.raises(ValueError, match='GENERATION_AUTHORIZATION_REPLAY'):
        prepare_and_verify(**second)


def test_denied_admission_does_not_consume_reservation(monkeypatch, tmp_path):
    params = generation_params(monkeypatch, tmp_path)
    params.update(generation_authorization_check=lambda b:dict(generation_admission_fixture(b), generation_authorized=False),
                  generator=lambda _:pytest.fail('denied'))
    with pytest.raises(ValueError, match='INVALID_GENERATION_ADMISSION'):
        prepare_and_verify(**params)
    second = add_analyzed_generation_task(params)
    second.update(generation_authorization_check=budget_authorizer(cap=1000,reserve=1000),
                  generator=lambda _: '```python\ndef f(): return 2\n```')
    assert prepare_and_verify(**second)['tests_passed']


def test_concurrent_admission_has_one_committed_winner(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    storage = TaskStorage(params['database'])
    nonce = 'd'*32
    storage.begin_verification(params['task_id'], nonce)
    request = storage.begin_generation(params['task_id'],nonce,'ci-synthetic',params['trusted_test_sha256'],params['image'])
    receipt = generation_admission_fixture(request['binding'])
    def reserve(_):
        try:
            TaskStorage(params['database']).authorize_generation(params['task_id'],nonce,receipt)
            return True
        except ValueError as error:
            assert str(error) == 'GENERATION_ADMISSION_CONFLICT'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve,range(2))) == 1
    assert TaskStorage(params['database']).get(params['task_id'])['generation']['admission']


@pytest.mark.parametrize('tamper', ['receipt','legacy'])
def test_unknown_or_corrupted_budget_history_blocks_later_dispatch(monkeypatch, tmp_path, tamper):
    import json, sqlite3
    params = generation_params(monkeypatch, tmp_path)
    prepare_and_verify(**params)
    with sqlite3.connect(params['database']) as conn:
        task = json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?',(params['task_id'],)).fetchone()[0])
        if tamper == 'receipt': task['generation']['admission']['receipt']['reserved_microuros'] = 1
        else: task['generation'].pop('admission_required')
        conn.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(task),params['task_id']))
    second = add_analyzed_generation_task(params)
    second['generator'] = lambda _:pytest.fail('unaccounted history')
    with pytest.raises(ValueError, match='INVALID_GENERATION_BUDGET_HISTORY|UNACCOUNTED_GENERATION_HISTORY'):
        prepare_and_verify(**second)


def test_callback_cannot_change_persisted_admission_before_response_commit(monkeypatch, tmp_path):
    import json, sqlite3
    params = generation_params(monkeypatch, tmp_path)
    def change(_):
        with sqlite3.connect(params['database']) as conn:
            task = json.loads(conn.execute('SELECT payload FROM tasks WHERE task_id=?',(params['task_id'],)).fetchone()[0])
            task['generation']['admission']['receipt']['model'] = 'replacement-model'
            conn.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(task),params['task_id']))
        return '```python\ndef f(): return 2\n```'
    params['generator'] = change
    with pytest.raises(ValueError, match='GENERATION_AUDIT_CONFLICT'):
        prepare_and_verify(**params)


def test_failed_reservation_write_never_calls_generator(monkeypatch, tmp_path):
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    original = TaskStorage._write_review_task
    def fail(self, conn, task_id, task):
        if task.get('generation',{}).get('admission'):
            raise OSError('synthetic sensitive reservation write failure')
        return original(self, conn, task_id, task)
    monkeypatch.setattr(TaskStorage, '_write_review_task', fail)
    params['generator'] = lambda _:pytest.fail('must not dispatch before committed reservation')
    with pytest.raises(OSError):
        prepare_and_verify(**params)
    task = TaskStorage(params['database']).get(params['task_id'])
    assert 'admission' not in task['generation']
    assert 'sensitive reservation' not in str(task)


def test_utc_month_rollover_keeps_history_and_clock_rewind_cannot_reset_budget(monkeypatch, tmp_path):
    from datetime import datetime, timezone, timedelta
    import central_ai.task_storage as storage_module
    import central_ai.verified_review_pipeline as pipeline
    from central_ai.task_storage import TaskStorage
    clock = [datetime(2030,1,5,tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock[0]
    monkeypatch.setattr(storage_module, 'datetime', Clock)
    monkeypatch.setattr(pipeline, 'datetime', Clock)
    params = generation_params(monkeypatch, tmp_path)
    def authorize(binding):
        return dict(budget_authorizer(cap=1000,reserve=1000)(binding),
                    budget_period=clock[0].strftime('%Y-%m'),
                    expires_at=(clock[0]+timedelta(minutes=1)).isoformat())
    params['generation_authorization_check'] = authorize
    first_id = params['task_id']
    prepare_and_verify(**params)
    clock[0] = datetime(2030,2,5,tzinfo=timezone.utc)
    second = add_analyzed_generation_task(params)
    assert prepare_and_verify(**second)['tests_passed']
    assert TaskStorage(params['database']).get(first_id)['generation']['admission']['receipt']['budget_period'] == '2030-01'
    clock[0] = datetime(2030,1,6,tzinfo=timezone.utc)
    third = add_analyzed_generation_task(params)
    third['generator'] = lambda _:pytest.fail('clock rewind cannot refund prior month')
    with pytest.raises(ValueError, match='GENERATION_BUDGET_EXHAUSTED'):
        prepare_and_verify(**third)


def test_admission_expiry_is_checked_after_waiting_for_sqlite_write_lock(monkeypatch, tmp_path):
    from datetime import datetime, timezone, timedelta
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import sqlite3
    import central_ai.task_storage as storage_module
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    clock = [datetime(2030,1,5,tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock[0]
    monkeypatch.setattr(storage_module, 'datetime', Clock)
    store = TaskStorage(params['database'])
    nonce = 'e'*32
    store.begin_verification(params['task_id'], nonce)
    request = store.begin_generation(params['task_id'],nonce,'ci-synthetic',params['trusted_test_sha256'],params['image'])
    receipt = dict(generation_admission_fixture(request['binding']), budget_period='2030-01',
                   expires_at=(clock[0]+timedelta(minutes=1)).isoformat())
    waiting = Event()
    original = store._connect
    def traced():
        connection = original()
        connection.set_trace_callback(lambda sql:waiting.set() if sql=='BEGIN IMMEDIATE' else None)
        return connection
    monkeypatch.setattr(store, '_connect', traced)
    writer = sqlite3.connect(params['database'])
    writer.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.authorize_generation,params['task_id'],nonce,receipt)
        try:
            assert waiting.wait(timeout=5)
            clock[0] += timedelta(minutes=2)
        finally:
            writer.rollback(); writer.close()
        with pytest.raises(ValueError, match='INVALID_GENERATION_ADMISSION'):
            future.result(timeout=5)
    assert 'admission' not in TaskStorage(params['database']).get(params['task_id'])['generation']


@pytest.mark.parametrize('committed', [False,True])
def test_uncertain_reservation_commit_never_dispatches_and_preserves_conservative_accounting(monkeypatch, tmp_path, committed):
    from contextlib import contextmanager
    import json
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    params.update(generation_authorization_check=budget_authorizer(cap=1000,reserve=1000),
                  generator=lambda _:pytest.fail('uncertain commit must never dispatch'))
    original = TaskStorage._connect
    triggered = []
    @contextmanager
    def uncertain(self):
        conn = original(self)
        try:
            yield conn
            row = conn.execute('SELECT payload FROM tasks WHERE task_id=?',(params['task_id'],)).fetchone()
            has_reservation = row and json.loads(row[0]).get('generation',{}).get('admission')
            if not triggered and conn.in_transaction and has_reservation:
                triggered.append(True)
                conn.commit() if committed else conn.rollback()
                raise OSError('synthetic sensitive commit uncertainty')
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
    monkeypatch.setattr(TaskStorage, '_connect', uncertain)
    with pytest.raises(OSError, match='commit uncertainty'):
        prepare_and_verify(**params)
    saved = TaskStorage(params['database']).get(params['task_id'])
    assert bool(saved['generation'].get('admission')) is committed
    assert 'sensitive commit' not in str(saved)
    second = add_analyzed_generation_task(params)
    second['generator'] = lambda _: '```python\ndef f(): return 2\n```'
    if committed:
        with pytest.raises(ValueError, match='GENERATION_BUDGET_EXHAUSTED'):
            prepare_and_verify(**second)
    else:
        assert prepare_and_verify(**second)['tests_passed']


def admitted_openai_fixture(monkeypatch, tmp_path, handler):
    import httpx
    from central_ai.app import make_openai_generator
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-secret-never-log')
    monkeypatch.setenv('OPENAI_MODEL', 'unapproved-environment-model')
    generate = make_openai_generator(enabled='YES', database=params['database'],
                                     transport=httpx.MockTransport(handler))
    storage = TaskStorage(params['database'])
    nonce = 'e'*32
    storage.begin_verification(params['task_id'], nonce)
    request = storage.begin_generation(params['task_id'], nonce, generate.generator_id,
                                       params['trusted_test_sha256'], params['image'])
    request['admission'] = storage.authorize_generation(params['task_id'], nonce,
                                                       generation_admission_fixture(request['binding']))
    return params, storage, request, generate


def test_openai_adapter_approved_profile_and_durable_one_shot(monkeypatch, tmp_path):
    import httpx, json
    from pathlib import Path
    seen = []
    def handler(outgoing):
        journal = storage.get(params['task_id'])['generation']
        assert journal['dispatch']['model'] == 'ci-fixture-model'
        body = json.loads(outgoing.content)
        assert body == dict(model='ci-fixture-model', max_tokens=100,
                            messages=[dict(role='user', content=request['task_description'])])
        assert str(outgoing.url) == 'https://api.openai.com/v1/chat/completions'
        seen.append(body)
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(
            {'choices':[{'message':{'content':'```python\ndef f(): return 2\n```'}}]}).encode()))
    params, storage, request, generate = admitted_openai_fixture(monkeypatch, tmp_path, handler)
    original = (Path(params['database']).parent/'source/sample.py').read_bytes()
    answer = generate(request)
    with pytest.raises(ValueError, match='OPENAI_DISPATCH_CONFLICT'):
        generate(request)
    storage.complete_generation(params['task_id'], request['binding']['nonce'], answer,
                                request['admission']['admission_sha256'])
    assert len(seen) == 1
    saved = storage.get(params['task_id'])['generation']
    assert saved['phase'] == 'completed'
    assert 'synthetic-secret' not in json.dumps(saved)
    assert request['task_description'] not in json.dumps(saved)
    assert (Path(params['database']).parent/'source/sample.py').read_bytes() == original


@pytest.mark.parametrize('field', ['model','tokens','prompt','nonce','provider','spec','digest','extra','typed'])
def test_openai_adapter_rejects_changed_request_without_http(monkeypatch, tmp_path, field):
    params, storage, request, generate = admitted_openai_fixture(
        monkeypatch, tmp_path, lambda _:pytest.fail('unauthorized HTTP'))
    if field == 'model': request['admission']['model'] = 'unapproved'
    if field == 'tokens': request['admission']['max_output_tokens'] = 1500
    if field == 'prompt': request['task_description'] = 'unapproved content'
    if field == 'nonce': request['binding']['nonce'] = 'f'*32
    if field == 'provider': request['binding']['provider_id'] = 'other'
    if field == 'spec': request['binding']['spec_sha256'] = 'a'*64
    if field == 'digest': request['admission']['admission_sha256'] = 'a'*64
    if field == 'extra': request['source'] = 'must not disclose'
    if field == 'typed': request['binding']['ordinal'] = True
    with pytest.raises(ValueError): generate(request)
    assert 'dispatch' not in storage.get(params['task_id'])['generation']


@pytest.mark.parametrize('failure', ['status','timeout','cancel'])
def test_openai_adapter_failed_attempt_is_not_retried(monkeypatch, tmp_path, failure):
    import asyncio, httpx
    calls = []
    def handler(outgoing):
        calls.append(1)
        if failure == 'timeout': raise httpx.ReadTimeout('private upstream detail')
        if failure == 'cancel': raise asyncio.CancelledError()
        return httpx.Response(429, stream=httpx.ByteStream(b'private upstream detail'))
    params, storage, request, generate = admitted_openai_fixture(monkeypatch, tmp_path, handler)
    expected = asyncio.CancelledError if failure == 'cancel' else RuntimeError
    with pytest.raises(expected): generate(request)
    with pytest.raises(ValueError, match='OPENAI_DISPATCH_CONFLICT'): generate(request)
    assert len(calls) == 1
    assert storage.get(params['task_id'])['generation']['admission']['receipt']['reserved_microuros'] == 1000


@pytest.mark.parametrize('change', ['expired','deleted','model','hash'])
def test_openai_adapter_rechecks_journal_and_dispatch(monkeypatch, tmp_path, change):
    import json, sqlite3
    from datetime import datetime, timedelta, timezone
    params, storage, request, generate = admitted_openai_fixture(
        monkeypatch, tmp_path, lambda _:pytest.fail('unauthorized HTTP'))
    task = storage.get(params['task_id'])
    if change == 'expired':
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        class FutureClock(datetime):
            @classmethod
            def now(cls, tz=None): return future
        monkeypatch.setattr('central_ai.task_storage.datetime', FutureClock)
    else:
        if change == 'deleted': del task['generation']['admission']
        if change == 'model': task['generation']['admission']['receipt']['model'] = 'unapproved'
        if change == 'hash': task['generation']['admission_sha256'] = 'f'*64
        with sqlite3.connect(params['database']) as conn:
            conn.execute('UPDATE tasks SET payload=? WHERE task_id=?', (json.dumps(task),params['task_id']))
    with pytest.raises(ValueError): generate(request)


def test_openai_adapter_sync_and_configuration_gates(monkeypatch, tmp_path):
    import asyncio
    from central_ai.app import make_openai_generator
    params, storage, request, generate = admitted_openai_fixture(
        monkeypatch, tmp_path, lambda _:pytest.fail('unauthorized HTTP'))
    async def invoke():
        with pytest.raises(ValueError, match='SYNC_CONTEXT'): generate(request)
    asyncio.run(invoke())
    monkeypatch.delenv('OPENAI_API_KEY')
    with pytest.raises(ValueError, match='NOT_CONFIGURED'): generate(request)
    with pytest.raises(ValueError, match='NOT_CONFIGURED'):
        make_openai_generator(enabled='NO',database=params['database'])
    with pytest.raises(ValueError, match='NOT_CONFIGURED'):
        make_openai_generator(enabled='YES',database=str(tmp_path/'absent.sqlite'))
    assert not (tmp_path/'absent.sqlite').exists()
    assert 'dispatch' not in storage.get(params['task_id'])['generation']


def test_openai_adapter_pipeline_integration_and_dispatch_tamper(monkeypatch, tmp_path):
    import httpx, json, sqlite3
    from central_ai.app import make_openai_generator
    from central_ai.task_storage import TaskStorage
    params = generation_params(monkeypatch, tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    def handler(outgoing):
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(
            {'choices':[{'message':{'content':'```python\ndef f(): return 2\n```'}}]}).encode()))
    generate = make_openai_generator(enabled='YES',database=params['database'],transport=httpx.MockTransport(handler))
    params.update(generator=generate,generator_id=generate.generator_id)
    assert prepare_and_verify(**params)['tests_passed']
    saved = TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['phase'] == 'completed'
    assert saved['approved'] is saved['deployment_allowed'] is False

    other = tmp_path/'tampered'
    other.mkdir()
    params, storage, request, generate = admitted_openai_fixture(monkeypatch, other, handler)
    answer = generate(request)
    task = storage.get(params['task_id'])
    task['generation']['dispatch']['max_output_tokens'] = 1500
    with sqlite3.connect(params['database']) as conn:
        conn.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(task),params['task_id']))
    with pytest.raises(ValueError,match='OPENAI_DISPATCH_CONFLICT'):
        storage.complete_generation(params['task_id'],request['binding']['nonce'],answer,
                                    request['admission']['admission_sha256'])


def test_openai_adapter_concurrent_dispatch_has_one_winner(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    params, storage, request, generate = admitted_openai_fixture(
        monkeypatch,tmp_path,lambda _:pytest.fail('no HTTP in journal concurrency check'))
    def claim(_):
        try:
            storage.begin_openai_dispatch(request)
            return True
        except ValueError as error:
            assert str(error)=='OPENAI_DISPATCH_CONFLICT'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(claim,range(2)))==1
    # A new adapter/storage object cannot erase an interrupted dispatch.
    from central_ai.task_storage import TaskStorage
    with pytest.raises(ValueError,match='OPENAI_DISPATCH_CONFLICT'):
        TaskStorage(params['database']).begin_openai_dispatch(request)


def test_openai_adapter_missing_dispatch_cannot_accept_response(monkeypatch, tmp_path):
    params, storage, request, generate = admitted_openai_fixture(
        monkeypatch,tmp_path,lambda _:pytest.fail('no HTTP'))
    with pytest.raises(ValueError,match='OPENAI_DISPATCH_CONFLICT'):
        storage.complete_generation(params['task_id'],request['binding']['nonce'],
                                    'synthetic response',request['admission']['admission_sha256'])


def test_admitted_connectivity_probe_exact_payload_usage_and_no_execution(monkeypatch,tmp_path):
    import httpx, json
    from scripts.openai_admitted_acceptance import probe
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-secret-no-real-provider')
    requests=[]
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps(dict(
            choices=[dict(message=dict(content='OK'))],
            usage=dict(prompt_tokens=5,completion_tokens=1,total_tokens=6))).encode()))
    report=probe(tmp_path,httpx.MockTransport(handle))
    assert report['acceptance']=='passed' and report['attempts']==1
    assert report['usage']==dict(prompt_tokens=5,completion_tokens=1,total_tokens=6)
    assert requests==[dict(model='gpt-4.1-mini',max_tokens=16,
                           messages=[dict(role='user',content='Return exactly OK.')])]
    assert report['production_tasks_modified'] is report['worker_activated'] is report['generated_code_executed'] is False
    assert 'synthetic-secret' not in json.dumps(report)


@pytest.mark.parametrize('kind',['missing_key','upstream','unexpected_answer'])
def test_admitted_connectivity_probe_failure_never_retries_or_exposes_body(monkeypatch,tmp_path,kind):
    import httpx,json
    from scripts.openai_admitted_acceptance import probe
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-private')
    if kind=='missing_key': monkeypatch.delenv('OPENAI_API_KEY')
    requests=[]
    def handle(request):
        requests.append(1)
        return httpx.Response(429 if kind=='upstream' else 200,stream=httpx.ByteStream(json.dumps(
            dict(choices=[dict(message=dict(content='private upstream text'))])).encode()))
    report=probe(tmp_path,httpx.MockTransport(handle))
    assert report['acceptance']=='failed'
    assert len(requests)==(0 if kind=='missing_key' else 1)
    assert 'private' not in json.dumps(report)


def test_admitted_connectivity_host_claim_is_durable_and_replay_blocked(tmp_path):
    from scripts.openai_admitted_acceptance import claim_once
    case=tmp_path/'case'
    assert claim_once(case)==case
    assert (case/'attempt.started').is_file()
    with pytest.raises(FileExistsError): claim_once(case)
    public=tmp_path/'public'
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError,match='NOT_PRIVATE'): claim_once(public)
    link=tmp_path/'link'
    link.symlink_to(case,target_is_directory=True)
    with pytest.raises(ValueError,match='INVALID_ACCEPTANCE_DIRECTORY'): claim_once(link)


def test_admitted_connectivity_source_mismatch_prevents_claim_and_docker(monkeypatch,tmp_path):
    import sys,io
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setattr(sys,'argv',['check','--container','fixture','--case-directory',str(tmp_path/'case'),'--send-once'])
    monkeypatch.setattr(check,'urlopen',lambda *a,**kw:io.BytesIO(b'changed remote source'))
    monkeypatch.setattr(check.subprocess,'run',lambda *a,**kw:pytest.fail('must not dispatch'))
    with pytest.raises(ValueError,match='PINNED_SOURCE_MISMATCH'):check.main()
    assert not (tmp_path/'case').exists()


def test_admitted_connectivity_composed_child_and_host_replay(monkeypatch,tmp_path,capsys):
    import io,json,sys
    from pathlib import Path
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-child-secret')
    case=tmp_path/'case'
    monkeypatch.setattr(sys,'argv',['check','--container','ci-fixture','--case-directory',str(case),'--send-once'])
    root=Path(__file__).resolve().parents[1]
    def source(url,**kwargs):
        for path,digest in check.FILES.values():
            if url.endswith('/'+path):return io.BytesIO((root/path).read_bytes())
        pytest.fail('unexpected source URL')
    monkeypatch.setattr(check,'urlopen',source)
    # Composition uses this checkout as a synthetic source fixture; the actual
    # operator manifest stays pinned to its reviewed historical commit.
    import hashlib
    monkeypatch.setattr(check,'FILES',{name:(path,hashlib.sha256((root/path).read_bytes()).hexdigest())
                                       for name,(path,_) in check.FILES.items()})
    original_run=check.subprocess.run
    calls=[]
    def child(args,**kwargs):
        assert args==['docker','exec','-i','ci-fixture','python','-']
        assert (case/'attempt.started').is_file()
        program=kwargs['input']
        assert 'synthetic-child-secret' not in program
        mock="httpx.MockTransport(lambda request:httpx.Response(200,stream=httpx.ByteStream(b'{\"choices\":[{\"message\":{\"content\":\"OK\"}}]}')))"
        program=program.replace(' report=probe(directory)', ' import httpx\n report=probe(directory,'+mock+')')
        kwargs['input']=program
        calls.append(1)
        return original_run([sys.executable,'-'],**kwargs)
    monkeypatch.setattr(check.subprocess,'run',child)
    assert check.main()==0
    assert json.loads((case/'report.json').read_text())['acceptance']=='passed'
    with pytest.raises(FileExistsError):check.main()
    assert len(calls)==1
    assert 'synthetic-child-secret' not in capsys.readouterr().out


def e2e_generator_fixture(monkeypatch, answer, calls):
    import httpx,json
    from central_ai.app import make_openai_generator
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-e2e-secret')
    def factory(database):
        def handler(request):
            payload=json.loads(request.content)
            calls.append(payload)
            assert payload['model']=='gpt-4.1-mini' and payload['max_tokens']==128
            assert '3, 4' not in payload['messages'][0]['content']
            return httpx.Response(200,stream=httpx.ByteStream(json.dumps(
                dict(choices=[dict(message=dict(content=answer))])).encode()))
        return make_openai_generator(enabled='YES',database=database,transport=httpx.MockTransport(handler))
    return factory


def test_operator_e2e_real_task_and_analyzer_mock_provider_and_verifier(monkeypatch,tmp_path):
    from scripts.openai_admitted_acceptance import run_e2e_case
    calls=[]
    factory=e2e_generator_fixture(monkeypatch,'```python\ndef f(a, b):\n    return a * b\n```',calls)
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        return valid_result(test_sha256=kwargs['expected_test_sha256'])
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier)
    assert result['acceptance']=='passed',result
    assert result['provider_mode']==result['verifier_mode']=='mock'
    assert result['analysis_completed'] and result['generation_completed'] and result['verification_journal_completed']
    assert result['source_unchanged'] and result['trusted_tests_unchanged'] and result['snapshot_removed']
    assert result['approved'] is result['deployment_allowed'] is result['worker_activated'] is False
    assert len(calls)==1
    replay=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier)
    assert replay['acceptance']=='failed_or_uncertain' and len(calls)==1


@pytest.mark.parametrize('answer', ['bad format','```python\nimport os\ndef f(a,b): return 2\n```'])
def test_operator_e2e_invalid_generated_code_never_executes_or_retries(monkeypatch,tmp_path,answer):
    from scripts.openai_admitted_acceptance import run_e2e_case
    calls=[]
    factory=e2e_generator_fixture(monkeypatch,answer,calls)
    def verifier(**kwargs):
        from central_ai.isolated_functional_verifier import _validate_bounded_candidate
        from pathlib import Path
        _validate_bounded_candidate(Path(kwargs['candidate']).read_bytes())
        pytest.fail('forbidden candidate reached execution')
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier)
    assert result['acceptance']=='failed_or_uncertain'
    assert len(calls)==1


def test_operator_e2e_independent_test_failure_is_not_success(monkeypatch,tmp_path):
    from scripts.openai_admitted_acceptance import run_e2e_case
    calls=[]
    factory=e2e_generator_fixture(monkeypatch,'```python\ndef f(a,b): return a + b\n```',calls)
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        return valid_result(passed=False,status='failed',returncode=1,completion_confirmed=False,
                            test_sha256=kwargs['expected_test_sha256'])
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier)
    assert result['acceptance']=='candidate_failed' and result['test_status']=='failed'
    assert result['verification_journal_completed'] and len(calls)==1


def test_operator_e2e_pinned_bundle_contains_local_import_closure():
    import ast
    from pathlib import Path
    from scripts.openai_admitted_acceptance import E2E_FILES
    root=Path(__file__).resolve().parents[1]
    for name,(path,digest) in E2E_FILES.items():
        if not path.endswith('.py'):continue
        for node in ast.walk(ast.parse((root/path).read_text())):
            if isinstance(node,ast.ImportFrom) and node.module and node.module.split('.')[0] in ('central_ai','developer_agent'):
                assert node.module in E2E_FILES,(name,node.module)


def test_operator_e2e_pinned_download_mismatch_blocks_setup(monkeypatch,tmp_path):
    import io
    from types import SimpleNamespace
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setattr(check,'urlopen',lambda *a,**kw:io.BytesIO(b'changed pinned source'))
    monkeypatch.setattr(check.subprocess,'run',lambda *a,**kw:pytest.fail('must not execute unverified source'))
    case=tmp_path/'case'
    with pytest.raises(ValueError,match='E2E_SOURCE_MISMATCH'):
        check.end_to_end_main(SimpleNamespace(case_directory=str(case),container='ci-only'))
    assert (case/'attempt.started').is_file()


def test_operator_e2e_unavailable_key_never_dispatches_or_leaks(monkeypatch,tmp_path):
    import subprocess,json
    from types import SimpleNamespace
    from scripts.openai_admitted_acceptance import run_e2e_case
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1,stdout='private-key-data',stderr='private-error'))
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,key_container='ci-only')
    assert result['acceptance']=='failed_or_uncertain'
    assert 'private' not in json.dumps(result)


def worker_review_fixture(monkeypatch,tmp_path,*,call_limit=100):
    from central_ai.verified_review_pipeline import make_worker_review_handler
    params=generation_params(monkeypatch,tmp_path)
    calls=[]
    def generate(request):
        calls.append(request['binding']['task_id'])
        return '```python\ndef f(): return 2\n```'
    jobs={params['task_id']:{key:params[key] for key in (
        'handoffs','proposals','candidates','trusted_test_file','trusted_test_sha256','image')}}
    for key in ('handoffs','proposals','candidates'):
        path=tmp_path/key; path.mkdir();jobs[params['task_id']][key]=str(path)
    def build(custom_jobs=None,generator=generate):
        return make_worker_review_handler(enabled='YES',database=params['database'],
            jobs=jobs if custom_jobs is None else custom_jobs,generator=generator,generator_id='ci-worker-generator',
            generation_authorization_check=budget_authorizer(calls=call_limit),
            authorization_check=params['authorization_check'],verifier=params['verifier'])
    return params,jobs,calls,build


def test_worker_review_pending_analysis_resumes_once_across_cycles(monkeypatch,tmp_path):
    from central_ai.worker_scheduler import scheduled_cycles
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    handler=build()
    def batch(**kwargs):return run_batch(**kwargs,idle_checks=1,sleep=lambda _:None)
    result=scheduled_cycles(enabled='YES',database=params['database'],agent='ci-review',
        lock_path=str(tmp_path/'scheduler.lock'),cycles=3,interval=1,max_tasks=1,
        sleep=lambda _:None,batch=batch,review_handler=handler)
    assert result==dict(status='complete',cycles=3,processed=1)
    assert calls==[params['task_id']]
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['verification']['phase']=='completed' and saved['generation']['phase']=='completed'
    assert saved['approved'] is saved['deployment_allowed'] is False
    assert run_batch(enabled='YES',database=params['database'],agent='restart',max_tasks=1,
        idle_checks=1,review_handler=build())['processed']==0
    assert len(calls)==1


def test_worker_review_new_analysis_finishes_before_generation(monkeypatch,tmp_path):
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    bridge=PersistentTaskBridge(params['database'])
    task_id=bridge.submit('New explicitly allowed source task')['task_id']
    TaskFileTargets(params['database']).register(task_id,str(tmp_path/'source'),'sample.py')
    job=dict(jobs[params['task_id']])
    handler=build({task_id:job})
    def batch():return run_batch(enabled='YES',database=params['database'],agent='ci-analysis-review',
        max_tasks=1,idle_checks=1,review_handler=handler)
    assert batch()['processed']==1
    saved=TaskStorage(params['database']).get(task_id)
    assert saved['status']=='analyzed' and saved['verification']['phase']=='completed'
    assert calls==[task_id]
    assert batch()['processed']==0
    assert 'verification' not in TaskStorage(params['database']).get(params['task_id'])


def test_worker_review_freezes_allowlist_and_configuration(monkeypatch,tmp_path):
    from central_ai.worker_batch import run_batch
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    handler=build()
    jobs[params['task_id']]['image']='invalid'
    jobs.clear()
    assert handler.accepts(params['task_id']) and not handler.accepts('other')
    with pytest.raises(ValueError,match='NOT_ALLOWED'):handler('other')
    assert run_batch(enabled='YES',database=params['database'],agent='ci',max_tasks=1,
                     idle_checks=1,review_handler=handler)['processed']==1
    assert calls==[params['task_id']]


def test_worker_review_persistent_budget_survives_new_handler_and_task(monkeypatch,tmp_path):
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path,call_limit=1)
    second=add_analyzed_generation_task(params)
    jobs[second['task_id']]=dict(jobs[params['task_id']])
    def batch(handler):return run_batch(enabled='YES',database=params['database'],agent='budget',
        max_tasks=1,idle_checks=1,review_handler=handler)
    assert batch(build())['processed']==1
    with pytest.raises(ValueError,match='CALL_BUDGET_EXHAUSTED'):batch(build())
    assert len(calls)==1
    saved=TaskStorage(params['database']).get(second['task_id'])
    assert saved['verification']['phase']=='blocked'
    assert batch(build())['processed']==0 and len(calls)==1


def test_worker_review_uncertain_dispatch_blocks_restart_without_retry(monkeypatch,tmp_path):
    import multiprocessing,os
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    def child():
        handler=build(generator=lambda request:os._exit(23))
        run_batch(enabled='YES',database=params['database'],agent='crash',max_tasks=1,idle_checks=1,review_handler=handler)
    process=multiprocessing.get_context('fork').Process(target=child)
    process.start();process.join(10)
    assert process.exitcode==23
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['admission']['receipt']['generation_authorized'] is True
    assert saved['verification']['phase']=='preparing'
    with pytest.raises(ValueError,match='DATABASE_BLOCKED'):
        run_batch(enabled='YES',database=params['database'],agent='restart',max_tasks=1,idle_checks=1,review_handler=build())
    assert not calls


def test_worker_review_concurrent_selection_cannot_double_dispatch(monkeypatch,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    barrier=Barrier(2)
    handlers=[build(),build()]
    for handler in handlers:
        original=handler.next_task_id
        def select(original=original):
            task_id=original();barrier.wait(timeout=5);return task_id
        handler.next_task_id=select
    workers=[DeveloperWorkerCoordinator(params['database'],'race-'+str(i),review_handler=handler)
             for i,handler in enumerate(handlers)]
    def run(worker):
        try:return worker.run_once()['verification']['tests_passed']
        except ValueError as error:
            assert str(error)=='VERIFICATION_ALREADY_STARTED'
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(run,workers))==1
    assert calls==[params['task_id']]


def test_worker_review_requires_explicit_matching_handler(monkeypatch,tmp_path):
    from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
    from central_ai.worker_batch import run_batch
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    assert run_batch(enabled='YES',database=params['database'],agent='default',max_tasks=1,idle_checks=1)['processed']==0
    assert not calls
    handler=build()
    with pytest.raises(ValueError,match='INVALID_WORKER_REVIEW_HANDLER'):
        DeveloperWorkerCoordinator(tmp_path/'other.sqlite','wrong-db',review_handler=handler)
    assert not (tmp_path/'other.sqlite').exists()
    with pytest.raises(ValueError,match='AMBIGUOUS_REVIEW_COORDINATOR'):
        run_batch(enabled='YES',database=params['database'],agent='ci',review_handler=handler,coordinator=object())


def test_worker_review_supervisor_propagates_explicit_handler_and_sanitizes_status(monkeypatch,tmp_path):
    import json
    from central_ai.worker_supervised import run_supervised
    from central_ai.worker_scheduler import scheduled_cycles
    from central_ai.worker_batch import run_batch
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    def batch(**kwargs):return run_batch(**kwargs,idle_checks=1,sleep=lambda _:None)
    def schedule(**kwargs):return scheduled_cycles(**kwargs,batch=batch,sleep=lambda _:None)
    result=run_supervised(enabled='YES',database=params['database'],agent='ci-supervised',
        lock_path=str(tmp_path/'run.lock'),status_path=str(tmp_path/'status.json'),
        cycles=2,interval=1,max_tasks=1,scheduler=schedule,review_handler=build())
    assert result['processed']==1 and len(calls)==1
    status=json.loads((tmp_path/'status.json').read_text())
    assert status['state']=='verified' and status['processed']==1
    assert params['task_id'] not in json.dumps(status) and 'generation-admission' not in json.dumps(status)


@pytest.mark.parametrize('bad', ['disabled','authority','generator','jobs','image','paths'])
def test_worker_review_factory_rejects_incomplete_host_configuration(monkeypatch,tmp_path,bad):
    from central_ai.verified_review_pipeline import make_worker_review_handler
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    options=dict(enabled='YES',database=params['database'],jobs=jobs,generator=lambda _:pytest.fail('must not dispatch'),
        generator_id='ci-only',generation_authorization_check=budget_authorizer(),
        authorization_check=params['authorization_check'],verifier=params['verifier'])
    if bad=='disabled':options['enabled']='NO'
    if bad=='authority':options['generation_authorization_check']=None
    if bad=='generator':options['generator']=None
    if bad=='jobs':options['jobs']={}
    if bad=='image':jobs[params['task_id']]['image']='python:latest'
    if bad=='paths':jobs[params['task_id']]['candidates']='relative-path'
    with pytest.raises(ValueError):make_worker_review_handler(**options)
    assert not calls


def test_operator_worker_case_three_cycles_one_generation(monkeypatch,tmp_path):
    from scripts.openai_admitted_acceptance import run_e2e_case
    calls=[]
    factory=e2e_generator_fixture(monkeypatch,'```python\ndef f(a, b): return a*b\n```',calls)
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        return valid_result(test_sha256=kwargs['expected_test_sha256'])
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier,worker_cycles=3)
    assert result['acceptance']=='passed',result
    assert result['scope']=='isolated_worker_generation_and_verification'
    assert result['worker_cycles_completed']==3 and result['worker_processed']==1
    assert result['generator_invocations']==len(calls)==1 and result['post_completion_idle_cycles']==2
    assert result['source_unchanged'] and result['trusted_tests_unchanged'] and result['snapshot_removed']
    assert result['persistent_worker_enabled_by_check'] is result['worker_activated'] is False
    assert run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier,worker_cycles=3)['acceptance']=='failed_or_uncertain'
    assert len(calls)==1


def test_operator_worker_case_failed_test_is_not_repeated(monkeypatch,tmp_path):
    from scripts.openai_admitted_acceptance import run_e2e_case
    calls=[]
    factory=e2e_generator_fixture(monkeypatch,'```python\ndef f(a, b): return a+b\n```',calls)
    def verifier(**kwargs):
        record_fixture_resources(kwargs)
        return valid_result(passed=False,status='failed',returncode=1,completion_confirmed=False,
                            test_sha256=kwargs['expected_test_sha256'])
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,generator_factory=factory,verifier=verifier,worker_cycles=3)
    assert result['acceptance']=='candidate_failed' and result['test_status']=='failed'
    assert result['worker_cycles_completed']==3 and result['generator_invocations']==1 and len(calls)==1
    assert result['approved'] is result['deployment_allowed'] is False


@pytest.mark.parametrize('cycles',[True,1,4,-1])
def test_operator_worker_case_rejects_unreviewed_cycle_limits(tmp_path,cycles):
    from scripts.openai_admitted_acceptance import run_e2e_case
    result=run_e2e_case(tmp_path,'python@sha256:'+'a'*64,worker_cycles=cycles)
    assert result['acceptance']=='failed_or_uncertain'
    assert not (tmp_path/'e2e.sqlite').exists()


def test_operator_worker_cli_requires_explicit_end_to_end(monkeypatch,tmp_path):
    import sys
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setattr(sys,'argv',['check','--container','ci','--case-directory',str(tmp_path/'case'),
                                   '--send-once','--worker-check'])
    with pytest.raises(ValueError,match='REQUIRES_END_TO_END'):check.main()
    assert not (tmp_path/'case').exists()


def test_operator_worker_setup_selects_separately_pinned_bundle(monkeypatch,tmp_path):
    import hashlib,io
    from types import SimpleNamespace
    from scripts import openai_admitted_acceptance as check
    content=b'public synthetic bundle fixture'
    monkeypatch.setattr(check,'WORKER_FILES',{'fixture':('fixture.py',hashlib.sha256(content).hexdigest())})
    urls=[]
    def download(url,**kwargs):
        urls.append(url)
        return io.BytesIO(content)
    monkeypatch.setattr(check,'urlopen',download)
    monkeypatch.setattr(check.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1,stdout='',stderr='private-setup-text'))
    with pytest.raises(RuntimeError,match='DEPENDENCY_SETUP_FAILED'):
        check.end_to_end_main(SimpleNamespace(case_directory=str(tmp_path/'case'),container='ci',worker_check=True))
    assert len(urls)==1 and '/'+check.WORKER_SOURCE+'/' in urls[0]
    assert (tmp_path/'case/attempt.started').is_file()


def usd_admission_fixture(binding, *, limit=20000000, reserved=10000, calls=1):
    receipt=generation_admission_fixture(binding)
    receipt.pop('budget_limit_microuros');receipt.pop('reserved_microuros')
    return dict(receipt,schema='generation-admission-usd-v2',budget_limit_microusd=limit,
                reserved_microusd=reserved,budget_call_limit=calls)


def test_usd_budget_survives_task_and_handler_changes(monkeypatch,tmp_path):
    from central_ai.task_storage import TaskStorage
    params=generation_params(monkeypatch,tmp_path)
    requests=[]
    def generate(request):
        requests.append(request)
        return '```python\ndef f(): return 2\n```'
    params.update(generator=generate,generation_authorization_check=lambda b:usd_admission_fixture(b,limit=10000,reserved=6000,calls=2))
    second=add_analyzed_generation_task(params)
    assert prepare_and_verify(**params)['tests_passed']
    saved=TaskStorage(params['database']).get(params['task_id'])['generation']
    assert saved['admission']['receipt']['budget_limit_microusd']==10000
    assert 'budget_limit_microuros' not in saved['admission']['receipt']
    with pytest.raises(ValueError,match='BUDGET_EXHAUSTED'):prepare_and_verify(**second)
    assert len(requests)==1


@pytest.mark.parametrize('first_usd',[False,True])
def test_budget_currencies_cannot_be_mixed_in_same_period(monkeypatch,tmp_path,first_usd):
    params=generation_params(monkeypatch,tmp_path)
    requests=[]
    def generate(request):
        requests.append(request)
        return '```python\ndef f(): return 2\n```'
    eur=lambda binding:dict(generation_admission_fixture(binding),budget_limit_microuros=1000000,
                            reserved_microuros=1000,budget_call_limit=100)
    usd=lambda binding:usd_admission_fixture(binding,limit=1000000,reserved=1000,calls=100)
    params.update(generator=generate,generation_authorization_check=usd if first_usd else eur)
    second=add_analyzed_generation_task(params)
    second['generation_authorization_check']=eur if first_usd else usd
    assert prepare_and_verify(**params)['tests_passed']
    with pytest.raises(ValueError,match='CURRENCY_CONFLICT'):prepare_and_verify(**second)
    assert len(requests)==1


@pytest.mark.parametrize('change',[
    {'schema':'generation-admission-v2'}, {'budget_limit_microusd':True},
    {'reserved_microusd':0}, {'reserved_microusd':20000001},
    {'budget_limit_microuros':20000000}, {'currency':'EUR'},
])
def test_usd_budget_rejects_ambiguous_units_before_dispatch(monkeypatch,tmp_path,change):
    params=generation_params(monkeypatch,tmp_path)
    params.update(generator=lambda _:pytest.fail('must not dispatch'),
                  generation_authorization_check=lambda b:dict(usd_admission_fixture(b),**change))
    with pytest.raises(ValueError,match='INVALID_GENERATION_ADMISSION'):prepare_and_verify(**params)


def test_usd_profile_uses_existing_openai_adapter_and_worker(monkeypatch,tmp_path):
    import httpx,json
    from central_ai.app import make_openai_generator
    from central_ai.verified_review_pipeline import make_worker_review_handler
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps(
            dict(choices=[dict(message=dict(content='```python\ndef f(): return 2\n```'))])).encode()))
    generator=make_openai_generator(enabled='YES',database=params['database'],transport=httpx.MockTransport(handle))
    worker=make_worker_review_handler(enabled='YES',database=params['database'],jobs=jobs,
        generator=generator,generator_id=generator.generator_id,generation_authorization_check=usd_admission_fixture,
        authorization_check=params['authorization_check'],verifier=params['verifier'])
    for i in range(2):
        result=run_batch(enabled='YES',database=params['database'],agent='ci-usd',max_tasks=1,
                         idle_checks=1,review_handler=worker)
        assert result['processed']==(1 if i==0 else 0)
    assert len(calls)==1
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['generation']['admission']['receipt']['schema']=='generation-admission-usd-v2'
    assert saved['verification']['phase']=='completed'


def runtime_policy_fixture(monkeypatch,tmp_path):
    import json,hashlib
    from pathlib import Path
    from central_ai.task_storage import TaskStorage
    from central_ai.verifier_gate import provision_reviewer_key
    state=tmp_path/'state'
    params,jobs,calls,build=worker_review_fixture(monkeypatch,state)
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    key=authority/'reviewer.key'
    provision_reviewer_key(enabled='YES',path=key)
    test=state/'trusted_test.py';test.write_text('from candidate import f\nassert f()==2\n');test.chmod(0o600)
    task=TaskStorage(params['database']).get(params['task_id'])
    job=dict(jobs[params['task_id']],source_file=str(state/'source/sample.py'),
        source_sha256=task['analysis']['source_sha256'],
        spec_sha256=hashlib.sha256(task['task']['task'].encode()).hexdigest(),
        trusted_test_file=str(test),trusted_test_sha256=hashlib.sha256(test.read_bytes()).hexdigest())
    core=['app.py','task_storage.py','verified_review_pipeline.py','verifier_gate.py',
          'developer_worker_coordinator.py','worker_batch.py','worker_scheduler.py','worker_supervised.py']
    root=Path(__file__).resolve().parents[1]/'central_ai'
    config=dict(schema='worker-review-runtime-v1',scope='isolated_only',execution_policy='bounded-arithmetic-v1',
        execution_authorized=True,approved=False,deployment_allowed=False,database=params['database'],
        policy_id='ci-persistent-policy',model='gpt-4.1-mini',max_output_tokens=128,
        budget=dict(currency='USD',limit_microusd=10000,reserved_microusd=1000,call_limit=1),
        authority=dict(generation_id='ci-host-generation',reviewer_id='ci-persistent-reviewer',reviewer_key_file=str(key)),
        runtime_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in core},
        jobs={params['task_id']:job})
    path=authority/'runtime.json'
    def save():path.write_text(json.dumps(config));path.chmod(0o600)
    save()
    return params,config,path,key,save


def test_runtime_policy_persistent_key_usd_and_worker_restarts(monkeypatch,tmp_path):
    import httpx,json
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    original_key=key.read_bytes();calls=[]
    real_generator=provider.make_openai_generator
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps(dict(
            choices=[dict(message=dict(content='```python\ndef f(): return 2\n```'))])).encode()))
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:real_generator(**kw,transport=httpx.MockTransport(handle)))
    real_handler=pipeline.make_worker_review_handler
    def verify(**kw):
        record_fixture_resources(kw)
        return valid_result(test_sha256=kw['expected_test_sha256'])
    monkeypatch.setattr(pipeline,'make_worker_review_handler',lambda **kw:real_handler(**kw,verifier=verify))
    for i in range(2):
        handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
        result=run_batch(enabled='YES',database=params['database'],agent='ci-configured',max_tasks=1,idle_checks=1,review_handler=handler)
        assert result['processed']==(1 if i==0 else 0)
    assert len(calls)==1 and key.read_bytes()==original_key
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert saved['verification']['phase']=='completed'
    assert saved['verification']['outcome']['reviewer_id']=='ci-persistent-reviewer'
    assert saved['generation']['admission']['receipt']['schema']=='generation-admission-usd-v2'
    assert saved['generation']['admission']['receipt']['authorization_id'].startswith('ci-host-generation:')
    assert saved['approved'] is saved['deployment_allowed'] is False
    assert original_key.hex() not in json.dumps(saved)


@pytest.mark.parametrize('bad',['review_profile','not_authorized','promotion','database','currency','calls',
                                'model','tokens','runtime','source','spec','test','state_key','public_config'])
def test_runtime_policy_invalid_host_grants_never_build_provider(monkeypatch,tmp_path,bad):
    import central_ai.app as provider
    from central_ai.verified_review_pipeline import load_worker_review_config
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not build provider'))
    grant=config['jobs'][params['task_id']]
    if bad=='review_profile':config['schema']='worker-rollout-review-v1'
    if bad=='not_authorized':config['execution_authorized']=False
    if bad=='promotion':config['approved']=True
    if bad=='database':config['database']=str(tmp_path/'different.sqlite')
    if bad=='currency':config['budget']['currency']='EUR'
    if bad=='calls':config['budget']['call_limit']=2
    if bad=='model':config['model']='unreviewed-model'
    if bad=='tokens':config['max_output_tokens']=True
    if bad=='runtime':config['runtime_sha256']['task_storage.py']='a'*64
    if bad=='source':grant['source_sha256']='a'*64
    if bad=='spec':grant['spec_sha256']='a'*64
    if bad=='test':grant['trusted_test_sha256']='a'*64
    if bad=='state_key':config['authority']['reviewer_key_file']=str(tmp_path/'state/reviewer.key')
    save()
    if bad=='public_config':path.chmod(0o644)
    with pytest.raises(ValueError):load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    assert not (tmp_path/'different.sqlite').exists()


def test_runtime_policy_duplicate_keys_rejected(monkeypatch,tmp_path):
    from central_ai.verified_review_pipeline import load_worker_review_config
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    path.write_text('{"schema":"worker-rollout-review-v1","schema":"worker-review-runtime-v1"}')
    with pytest.raises(ValueError):load_worker_review_config(enabled='YES',config_path=path,database=params['database'])


@pytest.mark.parametrize('bad',['symlink','hardlink','public_key','public_parent','oversize'])
def test_persistent_reviewer_key_protection(tmp_path,bad):
    from central_ai.verifier_gate import provision_reviewer_key,read_private_host_file
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    key=authority/'reviewer.key'
    report=provision_reviewer_key(enabled='YES',path=key)
    assert report==dict(reviewer_key_created=True,key_bytes_disclosed=False)
    original=key.read_bytes()
    assert len(original)==32
    with pytest.raises(FileExistsError):provision_reviewer_key(enabled='YES',path=key)
    assert key.read_bytes()==original
    if bad=='symlink':
        alias=authority/'alias';alias.symlink_to(key);key=alias
    if bad=='hardlink':
        import os
        os.link(key,authority/'alias')
    if bad=='public_key':key.chmod(0o644)
    if bad=='public_parent':authority.chmod(0o755)
    if bad=='oversize':key.write_bytes(b'x'*129)
    with pytest.raises(ValueError):read_private_host_file(key,max_bytes=128)


def test_runtime_policy_missing_provider_key_does_not_reserve(monkeypatch,tmp_path):
    from central_ai.verified_review_pipeline import load_worker_review_config
    from central_ai.task_storage import TaskStorage
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):
        load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    assert 'generation' not in TaskStorage(params['database']).get(params['task_id'])


def test_runtime_policy_authority_cannot_share_artifact_directory(monkeypatch,tmp_path):
    from central_ai.verified_review_pipeline import load_worker_review_config
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    config['jobs'][params['task_id']]['candidates']=str(key.parent)
    save()
    with pytest.raises(ValueError,match='AUTHORITY_INSIDE_ARTIFACTS'):
        load_worker_review_config(enabled='YES',config_path=path,database=params['database'])


def test_disabled_runtime_validation_has_no_provider_handler_or_database_write(monkeypatch,tmp_path):
    import hashlib
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    config['execution_authorized']=False;save()
    before=hashlib.sha256(__import__('pathlib').Path(params['database']).read_bytes()).hexdigest()
    key_before=key.read_bytes()
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not construct provider'))
    monkeypatch.setattr(pipeline,'make_worker_review_handler',lambda **kw:pytest.fail('must not return callable handler'))
    report=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'],validation_only=True)
    assert report==dict(config_validated=True,validation_only=True,execution_authorized=False,
        reviewer_key_loaded=True,task_grants=1,generation_started=False,worker_started=False,
        provider_key_verified=False,database_modified=False)
    assert not callable(report) and key.read_bytes()==key_before
    assert hashlib.sha256(__import__('pathlib').Path(params['database']).read_bytes()).hexdigest()==before
    with pytest.raises(ValueError):pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])


@pytest.mark.parametrize('change',[{'image':'python:latest'},{'candidates':'relative'}, {'trusted_test_sha256':'a'*64}])
def test_validation_only_keeps_live_grant_checks(monkeypatch,tmp_path,change):
    from central_ai.verified_review_pipeline import load_worker_review_config
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    config['execution_authorized']=False
    config['jobs'][params['task_id']].update(change);save()
    with pytest.raises(ValueError):load_worker_review_config(enabled='YES',config_path=path,database=params['database'],validation_only=True)


def test_runtime_preparation_reuses_key_creates_disabled_planned_state_without_dispatch(monkeypatch,tmp_path):
    import json,sqlite3
    from scripts.openai_admitted_acceptance import prepare_runtime_files
    from central_ai.verifier_gate import provision_reviewer_key
    import central_ai.app as provider
    import central_ai.worker_batch as batch
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    key=authority/'reviewer.key';provision_reviewer_key(enabled='YES',path=key)
    original=key.read_bytes()
    state=tmp_path/'state';state.mkdir(mode=0o700)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('no provider construction'))
    monkeypatch.setattr(batch,'run_batch',lambda **kw:pytest.fail('no analysis/worker'))
    report=prepare_runtime_files(state_directory=state,authority_directory=authority,
        verifier_image='python@sha256:'+'a'*64,budget_limit_microusd=1000000)
    assert report['runtime_config_prepared'] and report['runtime_config_validated'] and report['reviewer_key_loaded']
    assert report['execution_authorized'] is report['generation_started'] is report['worker_started'] is False
    assert report['planned_tasks']==1 and key.read_bytes()==original
    profile=json.loads((authority/'runtime.json').read_text())
    assert profile['execution_authorized'] is False and profile['budget']['currency']=='USD'
    with sqlite3.connect(state/'tasks.sqlite') as conn:
        rows=conn.execute('SELECT status,payload FROM tasks').fetchall()
        assert len(rows)==1 and rows[0][0]=='planned' and 'generation' not in json.loads(rows[0][1])
        assert conn.execute('SELECT status,attempt_count FROM task_queue').fetchall()==[('pending',0)]
    before=(state/'tasks.sqlite').read_bytes()
    with pytest.raises(ValueError,match='ALREADY_EXISTS'):
        prepare_runtime_files(state_directory=state,authority_directory=authority,
            verifier_image='python@sha256:'+'a'*64,budget_limit_microusd=1000000)
    assert (state/'tasks.sqlite').read_bytes()==before and key.read_bytes()==original


def test_runtime_preparation_missing_key_creates_no_task_or_policy(tmp_path):
    from scripts.openai_admitted_acceptance import prepare_runtime_files
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    state=tmp_path/'state';state.mkdir(mode=0o700)
    with pytest.raises(FileNotFoundError):prepare_runtime_files(state_directory=state,authority_directory=authority,
        verifier_image='python@sha256:'+'a'*64,budget_limit_microusd=1000000)
    assert not (state/'tasks.sqlite').exists() and not (authority/'runtime.json').exists()


def test_runtime_preparation_cli_cannot_combine_paid_modes(monkeypatch,tmp_path):
    import sys
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setattr(sys,'argv',['check','--case-directory',str(tmp_path/'state'),'--prepare-runtime','--send-once'])
    with pytest.raises(ValueError,match='MODE_AMBIGUOUS'):check.main()
    assert not (tmp_path/'state').exists()


def test_runtime_preparation_pinned_bootstrap_uses_real_child_without_dispatch(monkeypatch,tmp_path,capsys):
    import io,json,sys,hashlib
    from pathlib import Path
    from types import SimpleNamespace
    from central_ai.verifier_gate import provision_reviewer_key
    from scripts import openai_admitted_acceptance as check
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    key=authority/'reviewer.key';provision_reviewer_key(enabled='YES',path=key)
    key_before=key.read_bytes()
    root=Path(__file__).resolve().parents[1]
    # This bootstrap test serves current fixture bytes. Production bundle pins
    # still point to the previously reviewed immutable runtime, not this tree.
    monkeypatch.setattr(check,'PREPARE_FILES',{
        name:(path,hashlib.sha256((root/path).read_bytes()).hexdigest())
        for name,(path,digest) in check.PREPARE_FILES.items()})
    urls=[]
    def download(url,**kwargs):
        assert '/'+check.PREPARE_SOURCE+'/' in url
        for path,digest in check.PREPARE_FILES.values():
            if url.endswith('/'+path):
                urls.append(path)
                return io.BytesIO((root/path).read_bytes())
        pytest.fail('unexpected download')
    monkeypatch.setattr(check,'urlopen',download)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    state=tmp_path/'state'
    args=SimpleNamespace(authority_directory=str(authority),runtime_python=sys.executable,
        verifier_image='python@sha256:'+'a'*64,budget_usd=1,case_directory=str(state))
    assert check.prepare_runtime_main(args)==0
    result=json.loads((state/'preparation-report.json').read_text())
    assert result['runtime_config_validated'] and result['execution_authorized'] is False
    assert result['generation_started'] is result['worker_started'] is False
    assert len(urls)==len(check.PREPARE_FILES)
    assert key.read_bytes()==key_before
    assert 'reviewer.key' not in capsys.readouterr().out
    with pytest.raises(ValueError,match='AUTHORITY_NOT_READY'):check.prepare_runtime_main(args)


@pytest.mark.parametrize('provider_fails',[False,True])
def test_retained_pilot_one_dispatch_no_standing_grant_and_no_replay(monkeypatch,tmp_path,provider_fails):
    import json,subprocess,httpx
    from types import SimpleNamespace
    from scripts.openai_admitted_acceptance import prepare_runtime_files,run_prepared_pilot
    from central_ai.verifier_gate import provision_reviewer_key
    from central_ai.task_storage import TaskStorage
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    key=authority/'reviewer.key';provision_reviewer_key(enabled='YES',path=key)
    state=tmp_path/'state';state.mkdir(mode=0o700)
    prepare_runtime_files(state_directory=state,authority_directory=authority,
        verifier_image='python@sha256:'+'a'*64,budget_limit_microusd=20000000)
    policy_before=(authority/'runtime.json').read_bytes();key_before=key.read_bytes()
    calls=[];commands=[]
    def docker(args,**kwargs):
        commands.append(args)
        if args[:3]==['docker','image','inspect']:
            return SimpleNamespace(returncode=0,stdout='[{}]')
        assert args[:3]==['docker','exec','key-source']
        assert (state/'pilot.started').is_file()
        return SimpleNamespace(returncode=0,stdout=json.dumps('synthetic-provider-key-only'))
    monkeypatch.setattr(subprocess,'run',docker)
    real_generator=provider.make_openai_generator
    def transport(request):
        assert not list(authority.glob('pilot-grant-*.json'))
        assert (authority/'runtime.json').read_bytes()==policy_before
        calls.append(json.loads(request.content))
        return httpx.Response(503 if provider_fails else 200,stream=httpx.ByteStream(json.dumps(dict(
            choices=[dict(message=dict(content='```python\ndef f(a, b): return a * b\n```'))])).encode()))
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:real_generator(**kw,transport=httpx.MockTransport(transport)))
    real_handler=pipeline.make_worker_review_handler
    def verify(**kw):
        record_fixture_resources(kw)
        return valid_result(test_sha256=kw['expected_test_sha256'])
    monkeypatch.setattr(pipeline,'make_worker_review_handler',lambda **kw:real_handler(**kw,verifier=verify))
    monkeypatch.setenv('OPENAI_API_KEY','previous-value')
    report=run_prepared_pilot(state_directory=state,authority_directory=authority,key_container='key-source')
    assert report['acceptance']==('failed_or_uncertain' if provider_fails else 'passed')
    assert len(calls)==1 and calls[0]['max_tokens']==128
    assert report['standing_disabled_policy_and_key_unchanged'] is True
    assert report['persistent_worker_enabled'] is report['timer_modified'] is report['retry_allowed'] is False
    assert __import__('os').environ['OPENAI_API_KEY']=='previous-value'
    assert not list(authority.glob('pilot-grant-*.json'))
    assert (authority/'runtime.json').read_bytes()==policy_before and key.read_bytes()==key_before
    assert 'synthetic-provider-key-only' not in json.dumps(report)
    assert json.loads((state/'pilot-report.json').read_text())==report
    before=len(commands)
    with pytest.raises((ValueError,FileExistsError)):
        run_prepared_pilot(state_directory=state,authority_directory=authority,key_container='key-source')
    assert len(commands)==before and len(calls)==1
    saved=TaskStorage(state/'tasks.sqlite').get(next(iter(json.loads(policy_before)['jobs'])))
    assert saved['generation']['admission']['receipt']['schema']=='generation-admission-usd-v2'
    assert saved['generation']['phase']==('requested' if provider_fails else 'completed')


@pytest.mark.parametrize('flags',[[],['--end-to-end','--send-once'],['--prepare-runtime','--send-once']])
def test_retained_pilot_requires_unambiguous_explicit_single_request(monkeypatch,tmp_path,flags):
    import sys
    from scripts import openai_admitted_acceptance as check
    monkeypatch.setattr(sys,'argv',['check','--case-directory',str(tmp_path/'state'),'--run-prepared',*flags])
    with pytest.raises(ValueError,match='EXPLICIT_SINGLE_MODE_REQUIRED'):check.main()
    assert not (tmp_path/'state').exists()

@pytest.mark.parametrize('bad',['rootful','id','root','image','unavailable'])
def test_isolated_runner_daemon_rejection_and_explicit_endpoint(monkeypatch,bad):
    import json
    from types import SimpleNamespace
    import central_ai.isolated_functional_verifier as vf
    policy=dict(uid=10001,socket='/private/docker.sock',config_directory='/private/empty',
                daemon_id='fixture-daemon-id',data_root='/private/docker-data')
    monkeypatch.setattr(vf,'_checked_runner_host',lambda p:(1,2))
    image='python@sha256:'+'a'*64;commands=[]
    def docker(args,**kw):
        commands.append(args)
        assert args[:5]==['/usr/bin/docker','--host','unix:///private/docker.sock','--config','/private/empty']
        if args[5]=='info':
            data=dict(ID='other-daemon' if bad=='id' else policy['daemon_id'],
                DockerRootDir='/other' if bad=='root' else policy['data_root'],
                SecurityOptions=[] if bad=='rootful' else ['name=rootless'])
        else:data=[dict(RepoDigests=[] if bad=='image' else [image])]
        return SimpleNamespace(returncode=1 if bad=='unavailable' else 0,stdout=json.dumps(data))
    with pytest.raises(ValueError):vf.make_isolated_docker_runner(policy,[image],run=docker)
    assert commands


def test_isolated_runner_binds_all_commands_and_detects_socket_change(monkeypatch):
    import json
    from types import SimpleNamespace
    import central_ai.isolated_functional_verifier as vf
    p=dict(uid=10001,socket='/private/docker.sock',config_directory='/private/empty',
           daemon_id='fixture-daemon-id',data_root='/private/docker-data')
    identity=[(1,2)];commands=[];image='python@sha256:'+'a'*64
    monkeypatch.setattr(vf,'_checked_runner_host',lambda _:identity[0])
    def docker(args,**kwargs):
        commands.append(args)
        data=(dict(ID=p['daemon_id'],DockerRootDir=p['data_root'],SecurityOptions=['name=rootless'])
              if args[5]=='info' else [dict(RepoDigests=[image])])
        return SimpleNamespace(returncode=0,stdout=json.dumps(data))
    bound=vf.make_isolated_docker_runner(p,[image],run=docker)
    p['socket']='/mutated'  # Caller cannot redirect the captured endpoint.
    bound(['docker','container','ls'],timeout=10)
    assert commands[-1][:5]==['/usr/bin/docker','--host','unix:///private/docker.sock','--config','/private/empty']
    with pytest.raises(ValueError):bound(['docker','--host','tcp://production','info'])
    with pytest.raises(ValueError):bound(['docker','info'],env={'DOCKER_HOST':'tcp://production'})
    before=len(commands);identity[0]=(1,3)
    with pytest.raises(ValueError):bound(['docker','container','ls'])
    assert len(commands)==before


@pytest.mark.parametrize('bad',[None,'uid','override','capabilities','socket','socket_parent','config','data_root','docker_group','production_socket'])
def test_isolated_runner_host_rejections_before_docker(monkeypatch,tmp_path,bad):
    import os,grp,stat
    from types import SimpleNamespace
    from pathlib import Path
    import central_ai.isolated_functional_verifier as vf
    p=dict(uid=10001,socket='/private/docker.sock',config_directory='/private/empty',
           daemon_id='fixture-daemon-id',data_root='/private/docker-data')
    monkeypatch.setattr(os,'getuid',lambda:0 if bad=='uid' else 10001)
    monkeypatch.setattr(os,'geteuid',lambda:10001)
    monkeypatch.setattr(os,'getgid',lambda:10001);monkeypatch.setattr(os,'getegid',lambda:10001)
    monkeypatch.setattr(os,'getgroups',lambda:[123] if bad=='docker_group' else [])
    monkeypatch.setattr(os,'access',lambda *args:bad=='production_socket')
    monkeypatch.setattr(grp,'getgrnam',lambda _:SimpleNamespace(gr_gid=123))
    for key in list(os.environ):
        if key.startswith('DOCKER_'):monkeypatch.delenv(key)
    if bad=='override':monkeypatch.setenv('DOCKER_CONTEXT','production')
    monkeypatch.setattr(Path,'read_text',lambda self:'CapEff: '+('1' if bad=='capabilities' else '0')+'\nCapPrm: 0\nCapAmb: 0\n')
    monkeypatch.setattr(Path,'resolve',lambda self:self)
    def metadata(path):
        is_socket=str(path)==p['socket']
        mode=(stat.S_IFREG if bad=='socket' else stat.S_IFSOCK)|0o600 if is_socket else stat.S_IFDIR|0o700
        if (bad=='socket_parent' and str(path)=='/private') or (bad=='config' and str(path)==p['config_directory']):mode|=0o020
        return SimpleNamespace(st_uid=0 if bad=='data_root' and str(path)==p['data_root'] else 10001,st_mode=mode,st_dev=1,st_ino=2)
    monkeypatch.setattr(Path,'stat',metadata);monkeypatch.setattr(Path,'iterdir',lambda self:iter([]))
    if bad is None:
        assert vf._checked_runner_host(p)==(1,2)
    else:
        with pytest.raises(ValueError,match='ISOLATED_RUNNER_REQUIRED'):vf._checked_runner_host(p)


def test_runtime_v2_rejects_runner_before_provider_and_task_mutation(monkeypatch,tmp_path):
    import hashlib,json
    from pathlib import Path
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    config['schema']='worker-review-runtime-v2'
    config['runner']=dict(uid=0,socket='/var/run/docker.sock',config_directory='/bad',daemon_id='production',data_root='/bad')
    source=Path(pipeline.__file__).parent/'isolated_functional_verifier.py'
    config['runtime_sha256']['isolated_functional_verifier.py']=hashlib.sha256(source.read_bytes()).hexdigest()
    config['runtime_sha256']['task_queue.py']=hashlib.sha256(source.with_name('task_queue.py').read_bytes()).hexdigest();save()
    database=Path(params['database']);before=database.read_bytes();key_before=key.read_bytes()
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must reject before provider'))
    with pytest.raises(ValueError,match='ISOLATED_RUNNER_REQUIRED'):
        pipeline.load_worker_review_config(enabled='YES',config_path=path,database=str(database))
    assert database.read_bytes()==before and key.read_bytes()==key_before

@pytest.mark.parametrize('drift',[False,True])
def test_runtime_v2_synthetic_runner_full_flow_and_preadmission_drift(monkeypatch,tmp_path,drift):
    import hashlib,json,httpx
    from pathlib import Path
    from types import SimpleNamespace
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    import central_ai.isolated_functional_verifier as vf
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    config['schema']='worker-review-runtime-v2'
    config['runner']=dict(uid=10001,socket='/private/docker.sock',config_directory='/private/empty',
                         daemon_id='synthetic-daemon-id',data_root='/private/root')
    config['runtime_sha256']['isolated_functional_verifier.py']=hashlib.sha256(Path(vf.__file__).read_bytes()).hexdigest()
    config['runtime_sha256']['task_queue.py']=hashlib.sha256(Path(vf.__file__).with_name('task_queue.py').read_bytes()).hexdigest();save()
    daemon=[config['runner']['daemon_id']];commands=[];requests=[]
    monkeypatch.setattr(vf,'_checked_runner_host',lambda p:(1,2))  # Synthetic host observations, not rootless acceptance.
    def docker(args,**kwargs):
        commands.append(args)
        if args[5]=='info':data=dict(ID=daemon[0],DockerRootDir='/private/root',SecurityOptions=['name=rootless'])
        elif args[5]=='image':data=[dict(RepoDigests=[config['jobs'][params['task_id']]['image']])]
        else:data=[]
        return SimpleNamespace(returncode=0,stdout=json.dumps(data))
    factory=vf.make_isolated_docker_runner
    monkeypatch.setattr(vf,'make_isolated_docker_runner',lambda p,images:factory(p,images,run=docker))
    real_generator=provider.make_openai_generator
    def transport(request):
        requests.append(request)
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps(dict(choices=[dict(message=dict(content='```python\ndef f(): return 2\n```'))])).encode()))
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:real_generator(**kw,transport=httpx.MockTransport(transport)))
    def verify(**kwargs):
        kwargs['run'](['docker','container','ls'],capture_output=True,text=True,timeout=10)
        record_fixture_resources(kwargs)
        return valid_result(test_sha256=kwargs['expected_test_sha256'])
    monkeypatch.setattr(pipeline,'run_functional_tests',verify)
    handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    if drift:daemon[0]='changed-daemon-id'
    def execute():return run_batch(enabled='YES',database=params['database'],agent='synthetic-isolation',max_tasks=1,idle_checks=1,review_handler=handler)
    if drift:
        with pytest.raises(ValueError,match='DAEMON_MISMATCH'):execute()
    else:
        assert execute()['processed']==1
        assert execute()['processed']==0
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert len(requests)==(0 if drift else 1)
    assert ('admission' in saved['generation']) is (not drift)
    if not drift:assert saved['verification']['outcome']['tests_passed'] is True
    assert saved['approved'] is saved['deployment_allowed'] is False
    assert all(c[:5]==['/usr/bin/docker','--host','unix:///private/docker.sock','--config','/private/empty'] for c in commands)

@pytest.mark.parametrize('foreign_leased',[False,True])
def test_review_scope_mixed_queue_never_mutates_foreign_pending_or_expired(monkeypatch,tmp_path,foreign_leased):
    import sqlite3
    from central_ai.persistent_bridge import PersistentTaskBridge
    from central_ai.task_file_targets import TaskFileTargets
    from central_ai.worker_batch import run_batch
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    bridge=PersistentTaskBridge(params['database']);targets=TaskFileTargets(params['database'])
    foreign=bridge.submit('Unrelated registered analysis task')['task_id']
    granted=bridge.submit('Explicitly granted analysis task')['task_id']
    for task_id in (foreign,granted):targets.register(task_id,str(tmp_path/'source'),'sample.py')
    if foreign_leased:
        bridge.queue.acquire(foreign,'other-owner')
        with sqlite3.connect(params['database']) as db:
            db.execute("UPDATE task_queue SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",(foreign,))
    def snapshot():
        with sqlite3.connect(params['database']) as db:
            return (db.execute('SELECT * FROM task_queue WHERE task_id=?',(foreign,)).fetchall(),
                    db.execute('SELECT * FROM task_queue_audit WHERE task_id=? ORDER BY id',(foreign,)).fetchall(),
                    db.execute('SELECT payload FROM tasks WHERE task_id=?',(foreign,)).fetchone())
    before=snapshot();handler=build({granted:dict(jobs[params['task_id']])})
    def cycle():return run_batch(enabled='YES',database=params['database'],agent='scoped',max_tasks=1,idle_checks=1,review_handler=handler)
    assert cycle()['processed']==1
    assert calls==[granted] and snapshot()==before
    assert cycle()['processed']==0 and snapshot()==before
    assert TaskStorage(params['database']).get(granted)['verification']['phase']=='completed'
    # The default analysis-only worker still handles ordinary registered work.
    assert run_batch(enabled='YES',database=params['database'],agent='analysis-only',max_tasks=1,idle_checks=1)['processed']==1
    assert TaskStorage(params['database']).get(foreign)['status']=='analyzed'
    assert calls==[granted]


def test_review_scope_is_frozen_and_cannot_select_foreign_task(monkeypatch,tmp_path):
    from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    handler=build();worker=DeveloperWorkerCoordinator(params['database'],'scoped',review_handler=handler)
    handler.allowed_task_ids=('unrelated',)
    handler.next_task_id=lambda:'unrelated'
    before=__import__('pathlib').Path(params['database']).read_bytes()
    with pytest.raises(ValueError,match='OUTSIDE_SCOPE'):worker.run_once()
    assert __import__('pathlib').Path(params['database']).read_bytes()==before and calls==[]
    assert worker.review_task_ids==(params['task_id'],)


@pytest.mark.parametrize('scope',[[],(),['missing'],"one",{'one'},[None],[''],['same','same'],['x'*129],list(map(str,range(101)))])
def test_queue_scope_empty_missing_or_invalid_spends_no_attempt(tmp_path,scope):
    import sqlite3
    from central_ai.task_queue import TaskQueue
    queue=TaskQueue(tmp_path/'queue.sqlite');queue.enqueue('ordinary')
    from central_ai.task_file_targets import TaskFileTargets
    TaskFileTargets(queue.db_path).initialize()
    before=queue.status('ordinary')
    with sqlite3.connect(queue.db_path) as db:events=db.execute('SELECT * FROM task_queue_audit').fetchall()
    if scope in ([],(),['missing']):assert queue.acquire_next('scoped',allowed_task_ids=scope) is None
    else:
        with pytest.raises(ValueError,match='INVALID_TASK_SCOPE'):queue.acquire_next('scoped',allowed_task_ids=scope)
    assert queue.status('ordinary')==before
    with sqlite3.connect(queue.db_path) as db:assert db.execute('SELECT * FROM task_queue_audit').fetchall()==events


def test_queue_scope_competing_acquisitions_share_one_lease_and_attempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from central_ai.task_queue import TaskQueue
    queue=TaskQueue(tmp_path/'queue.sqlite');queue.enqueue('allowed');queue.enqueue('foreign')
    from central_ai.task_file_targets import TaskFileTargets
    TaskFileTargets(queue.db_path).initialize()
    barrier=Barrier(2)
    def acquire(agent):
        barrier.wait()
        return queue.acquire_next(agent,allowed_task_ids=['allowed'])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(acquire,['first','second']))
    assert sum(r is not None for r in results)==1
    assert queue.status('allowed')['attempt_count']==1
    assert queue.status('foreign')['attempt_count']==0

@pytest.mark.parametrize('outcome,expected',[('passed','verified'),('failed','candidate_failed'),
    ('cleanup_unconfirmed','cleanup_uncertain'),('timeout','blocked'),('provider_error','blocked')])
def test_supervisor_durable_review_states_survive_idle_or_restart(monkeypatch,tmp_path,outcome,expected):
    import json
    from pathlib import Path
    from central_ai.worker_supervised import run_supervised
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    if outcome=='provider_error':
        def generator(request):
            calls.append(request['binding']['task_id'])
            raise RuntimeError('secret-provider-detail')
        handler=build(generator=generator)
    else:
        def verify(**kwargs):
            record_fixture_resources(kwargs)
            if outcome=='cleanup_unconfirmed':
                return valid_result(status=outcome,passed=False,
                    snapshot_directory='/tmp/central-ai-input-ci-fixture',container_name='central-ai-verifier-'+'f'*32)
            return valid_result(status=outcome,passed=outcome=='passed',returncode=1 if outcome=='failed' else 0)
        params['verifier']=verify;handler=build()
    status=tmp_path/'honest-status.json'
    def cycle():return run_supervised(enabled='YES',database=params['database'],agent='status-test',
        lock_path=str(tmp_path/'status.lock'),status_path=str(status),cycles=1,interval=1,max_tasks=1,review_handler=handler)
    if outcome=='provider_error':
        with pytest.raises(RuntimeError):cycle()
    else:
        result=cycle();assert result['review_state']==expected and result['status']=='complete'
    first=json.loads(status.read_text());assert first['state']==expected
    before=Path(params['database']).read_bytes()
    summary=TaskStorage.review_status(params['database'],handler.allowed_task_ids)
    assert summary['state']==expected and Path(params['database']).read_bytes()==before
    if expected=='cleanup_uncertain':
        with pytest.raises(ValueError):cycle()
    else:
        again=cycle()
        assert again['processed']==0 and again['review_state']==('idle' if expected=='verified' else expected)
    record=json.loads(status.read_text())
    assert record['state']==('idle' if expected=='verified' else expected)
    assert len(calls)==1
    encoded=status.read_text()
    assert params['task_id'] not in encoded and 'secret-provider-detail' not in encoded
    assert 'generation-admission' not in encoded and '/tmp/' not in encoded


def test_review_status_corrupt_outcomes_fail_closed(monkeypatch,tmp_path):
    import json,sqlite3
    from pathlib import Path
    from central_ai.task_storage import TaskStorage
    from central_ai.worker_batch import run_batch
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    handler=build()
    assert run_batch(enabled='YES',database=params['database'],agent='status-good',max_tasks=1,idle_checks=1,review_handler=handler)['processed']==1
    with sqlite3.connect(params['database']) as db:
        encoded=db.execute('SELECT payload FROM tasks WHERE task_id=?',(params['task_id'],)).fetchone()[0]
        task=json.loads(encoded);task['verification']['outcome']['completion_confirmed']=False
        db.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps(task),params['task_id']))
    before=Path(params['database']).read_bytes()
    with pytest.raises(ValueError):TaskStorage.review_status(params['database'],handler.allowed_task_ids)
    assert Path(params['database']).read_bytes()==before


def test_review_status_sees_global_intent_outside_grants_without_writes(monkeypatch,tmp_path):
    from pathlib import Path
    from central_ai.task_storage import TaskStorage
    params,jobs,calls,build=worker_review_fixture(monkeypatch,tmp_path)
    foreign=add_analyzed_generation_task(params)
    TaskStorage(params['database']).begin_verification(foreign['task_id'],'a'*32)
    before=Path(params['database']).read_bytes()
    summary=build().review_status()
    assert summary['state']=='blocked' and summary['blocked']==1 and summary['pending']==1
    assert Path(params['database']).read_bytes()==before and calls==[]

@pytest.mark.parametrize('isolated',[False,True])
@pytest.mark.parametrize('outcome',['passed','failed','cleanup_unconfirmed'])
def test_completed_runtime_idle_needs_no_provider_key_or_factory(monkeypatch,tmp_path,isolated,outcome):
    import hashlib,json,httpx
    from pathlib import Path
    from central_ai.worker_supervised import run_supervised
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    import central_ai.isolated_functional_verifier as vf
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    observed=[]
    if isolated:
        config['schema']='worker-review-runtime-v2'
        config['runner']=dict(uid=10001,socket='/synthetic/docker.sock',config_directory='/synthetic/config',daemon_id='synthetic-daemon',data_root='/synthetic/data')
        for name in ('isolated_functional_verifier.py','task_queue.py'):
            config['runtime_sha256'][name]=hashlib.sha256(Path(pipeline.__file__).with_name(name).read_bytes()).hexdigest()
        save()
        monkeypatch.setattr(vf,'make_isolated_docker_runner',lambda *a,**kw:observed.append('runner') or (lambda *a,**kw:None))
    real=provider.make_openai_generator;calls=[]
    def transport(request):
        calls.append(request)
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps(dict(choices=[dict(message=dict(content='```python\ndef f(): return 2\n```'))])).encode()))
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:real(**kw,transport=httpx.MockTransport(transport)))
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-key')
    def verify(**kw):
        record_fixture_resources(kw)
        if outcome=='cleanup_unconfirmed':
            return valid_result(test_sha256=kw['expected_test_sha256'],status=outcome,passed=False,
                snapshot_directory='/tmp/central-ai-input-ci-fixture',container_name='central-ai-verifier-'+'f'*32)
        return valid_result(test_sha256=kw['expected_test_sha256'],status=outcome,passed=outcome=='passed',returncode=0 if outcome=='passed' else 1)
    if isolated:monkeypatch.setattr(pipeline,'run_functional_tests',verify)
    else:
        factory=pipeline.make_worker_review_handler
        monkeypatch.setattr(pipeline,'make_worker_review_handler',lambda **kw:factory(**kw,verifier=verify))
    handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    def cycle(handler):return run_supervised(enabled='YES',database=params['database'],agent='idle-test',
        lock_path=str(Path(params['database']).parent/'idle.lock'),status_path=str(Path(params['database']).parent/'idle-status.json'),cycles=1,interval=1,max_tasks=1,review_handler=handler)
    assert cycle(handler)['review_state']=={'passed':'verified','failed':'candidate_failed','cleanup_unconfirmed':'cleanup_uncertain'}[outcome] and len(calls)==1
    database=Path(params['database']);before=database.read_bytes();key_before=key.read_bytes()
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('idle must not construct provider'))
    if outcome!='passed':
        with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):
            pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
        assert database.read_bytes()==before and key.read_bytes()==key_before and len(calls)==1
        return
    loaded=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    for _ in range(2):
        result=cycle(loaded)
        assert result['review_state']=='idle' and result['processed']==0
    assert database.read_bytes()==before and key.read_bytes()==key_before and len(calls)==1
    if isolated:assert len(observed)>=4  # Guard checks remain present on reload.
    # An inconsistent completed-task queue must not be accepted as credential-free idle.
    import sqlite3
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE task_queue SET status='pending' WHERE task_id=?",(params['task_id'],))
    corrupted=database.read_bytes()
    with pytest.raises(ValueError,match='INVALID_VERIFICATION_AUDIT'):
        pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    assert database.read_bytes()==corrupted and len(calls)==1


@pytest.mark.parametrize('when',['load','cycle','direct'])
def test_missing_key_before_eligible_work_never_mutates_or_builds_provider(monkeypatch,tmp_path,when):
    from pathlib import Path
    from central_ai.worker_batch import run_batch
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not construct provider'))
    if when!='load':
        monkeypatch.setenv('OPENAI_API_KEY','synthetic-key')
        handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    before=Path(params['database']).read_bytes()
    with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):
        if when=='load':pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
        elif when=='cycle':run_batch(enabled='YES',database=params['database'],agent='missing-key',max_tasks=1,idle_checks=1,review_handler=handler)
        else:handler(params['task_id'])
    assert Path(params['database']).read_bytes()==before


def test_key_loss_before_admission_builds_no_provider_or_reservation(monkeypatch,tmp_path):
    from central_ai.task_storage import TaskStorage
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not construct provider'))
    handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    original=TaskStorage.begin_generation
    def begin(self,*args,**kwargs):
        request=original(self,*args,**kwargs)
        monkeypatch.delenv('OPENAI_API_KEY')
        return request
    monkeypatch.setattr(TaskStorage,'begin_generation',begin)
    with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):handler(params['task_id'])
    saved=TaskStorage(params['database']).get(params['task_id'])
    assert 'admission' not in saved['generation'] and 'dispatch' not in saved['generation']
    assert saved['verification']['phase']=='blocked'


def test_missing_key_preflight_precedes_coordinator_dependency_initialization(monkeypatch,tmp_path):
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    import central_ai.developer_worker_coordinator as coordinator
    params,config,path,key,save=runtime_policy_fixture(monkeypatch,tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not construct provider'))
    handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=params['database'])
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.setattr(coordinator,'PersistentTaskBridge',lambda *a,**kw:pytest.fail('must not initialize/migrate dependencies'))
    with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):
        coordinator.DeveloperWorkerCoordinator(params['database'],'missing-key',review_handler=handler)


def test_coordinator_freezes_key_preflight_before_pending_analysis(monkeypatch,tmp_path):
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    from central_ai.developer_worker_coordinator import DeveloperWorkerCoordinator
    from central_ai.verifier_gate import provision_reviewer_key
    from scripts.openai_admitted_acceptance import prepare_runtime_files
    authority=tmp_path/'authority';authority.mkdir(mode=0o700)
    provision_reviewer_key(enabled='YES',path=authority/'reviewer.key')
    state=tmp_path/'state';state.mkdir(mode=0o700)
    prepare_runtime_files(state_directory=state,authority_directory=authority,
        verifier_image='python@sha256:'+'a'*64,budget_limit_microusd=20000000)
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-only')
    monkeypatch.setattr(provider,'make_openai_generator',lambda **kw:pytest.fail('must not construct provider'))
    import json
    path=authority/'runtime.json';config=json.loads(path.read_text());config['execution_authorized']=True
    path.write_text(json.dumps(config));path.chmod(0o600)
    handler=pipeline.load_worker_review_config(enabled='YES',config_path=path,database=str(state/'tasks.sqlite'))
    worker=DeveloperWorkerCoordinator(state/'tasks.sqlite','frozen-preflight',review_handler=handler)
    handler.before_cycle=None
    monkeypatch.delenv('OPENAI_API_KEY')
    before=(state/'tasks.sqlite').read_bytes()
    with pytest.raises(ValueError,match='PROVIDER_NOT_CONFIGURED'):worker.run_once()
    assert (state/'tasks.sqlite').read_bytes()==before


@pytest.mark.parametrize('outcome', ['passed', 'failed', 'timeout'])
def test_real_rootless_private_runner_lifecycle(monkeypatch, tmp_path, outcome):
    """Opt-in real daemon integration; only the provider response is synthetic."""
    import os, json, hashlib, time, httpx
    from pathlib import Path
    import central_ai.app as provider
    import central_ai.verified_review_pipeline as pipeline
    from central_ai.worker_supervised import run_supervised
    from central_ai.task_storage import TaskStorage
    runner_file = os.environ.get('CENTRAL_AI_ROOTLESS_CI_POLICY')
    if not runner_file:
        pytest.skip('requires disposable nonroot/private rootless CI daemon')
    # Never replace host/daemon guards, candidate preparation or the verifier.
    prepare = pipeline.prepare_review_pipeline
    params, config, path, key, save = runtime_policy_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, 'prepare_review_pipeline', prepare)
    config['schema'] = 'worker-review-runtime-v2'
    config['runner'] = json.loads(Path(runner_file).read_text())
    image = os.environ['CENTRAL_AI_ROOTLESS_CI_IMAGE']
    job = config['jobs'][params['task_id']]
    # Match the existing no-group-write/no-world-write file trust contract.
    Path(job['source_file']).chmod(0o600)
    # The hardened loader requires private artifact directories; CI umask varies.
    for directory_name in ('handoffs', 'proposals', 'candidates'):
        Path(job[directory_name]).chmod(0o700)
    job['image'] = image
    trusted = Path(job['trusted_test_file'])
    trusted.write_text('''import sys, os
from pathlib import Path
sys.path.insert(0, '/sandbox')
from candidate import f
assert f() == 2
assert os.getuid() == os.geteuid() == 65534
status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert all(int(status[k].strip(), 16) == 0 for k in ('CapEff', 'CapPrm', 'CapAmb'))
assert status['NoNewPrivs'].strip() == '1'
assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '134217728'
assert Path('/sys/fs/cgroup/pids.max').read_text().strip() == '32'
quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
assert int(quota) * 2 == int(period)
assert not any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:])
assert not os.environ.get('OPENAI_API_KEY')
try:
    Path('/rootfs-write-probe').write_text('forbidden')
except OSError as error:
    assert error.errno == 30
else:
    raise AssertionError('root filesystem writable')
'''+({'passed':'', 'failed':"assert False, 'trusted negative fixture'\n",
      'timeout':'import time\ntime.sleep(40)\n'}[outcome]))
    job['trusted_test_sha256'] = hashlib.sha256(trusted.read_bytes()).hexdigest()
    for name in ('isolated_functional_verifier.py', 'task_queue.py'):
        config['runtime_sha256'][name] = hashlib.sha256(Path(pipeline.__file__).with_name(name).read_bytes()).hexdigest()
    save()
    source = Path(job['source_file']); source_before = source.read_bytes()
    test_before = trusted.read_bytes(); key_before = key.read_bytes(); calls = []
    original = provider.make_openai_generator
    def response(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(dict(
            choices=[dict(message=dict(content='```python\ndef f(): return 2\n```'))])).encode()))
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-ci-only')
    monkeypatch.setattr(provider, 'make_openai_generator', lambda **kw:
        original(**kw, transport=httpx.MockTransport(response)))
    # Validate the legitimate host policy first; do not mask an unrelated fixture error
    # as an expected daemon-identity rejection.
    baseline_handler = pipeline.load_worker_review_config(
        enabled='YES', config_path=path, database=params['database'])
    assert callable(baseline_handler)
    # A real endpoint with a wrong daemon identity must reject before task writes/provider.
    daemon_id = config['runner']['daemon_id']
    config['runner']['daemon_id'] = ('0' if daemon_id[0] != '0' else '1') + daemon_id[1:]
    save()
    before = Path(params['database']).read_bytes()
    with pytest.raises(ValueError, match='DAEMON_MISMATCH'):
        pipeline.load_worker_review_config(enabled='YES', config_path=path, database=params['database'])
    assert Path(params['database']).read_bytes() == before and not calls
    config['runner'] = json.loads(Path(runner_file).read_text()); save()
    handler = pipeline.load_worker_review_config(enabled='YES', config_path=path, database=params['database'])
    def cycle(loaded):
        return run_supervised(enabled='YES', database=params['database'], agent='rootless-ci',
            lock_path=str(Path(params['database']).parent/'rootless.lock'),
            status_path=str(Path(params['database']).parent/'rootless-status.json'),
            cycles=1, interval=1, max_tasks=1, review_handler=loaded)
    started = time.monotonic()
    result = cycle(handler)
    elapsed = time.monotonic() - started
    record = TaskStorage(params['database']).get(params['task_id'])
    audit = record['verification']
    assert audit['phase'] == 'completed' and audit['outcome']['test_status'] == outcome
    assert audit['outcome']['tests_passed'] is (outcome == 'passed')
    assert not Path(audit['resources']['snapshot_directory']).exists()
    from central_ai.isolated_functional_verifier import make_isolated_docker_runner
    run = make_isolated_docker_runner(config['runner'], [image])
    absent = run(['docker', 'container', 'ls', '--all', '--format', '{{.Names}}'],
                 capture_output=True, text=True, timeout=10, check=False)
    assert absent.returncode == 0 and not absent.stdout.strip()
    assert len(calls) == 1 and result['processed'] == 1 and elapsed < 90
    assert source.read_bytes() == source_before and trusted.read_bytes() == test_before and key.read_bytes() == key_before
    assert record['approved'] is record['deployment_allowed'] is False
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.setattr(provider, 'make_openai_generator', lambda **kw: pytest.fail('restart must not construct provider'))
    db_before = Path(params['database']).read_bytes()
    if outcome == 'passed':
        for _ in range(2):
            loaded = pipeline.load_worker_review_config(enabled='YES', config_path=path, database=params['database'])
            idle = cycle(loaded)
            assert idle['processed'] == 0 and idle['review_state'] == 'idle'
    else:
        with pytest.raises(ValueError, match='PROVIDER_NOT_CONFIGURED'):
            pipeline.load_worker_review_config(enabled='YES', config_path=path, database=params['database'])
    assert Path(params['database']).read_bytes() == db_before and len(calls) == 1
    print(json.dumps(dict(rootless_case=outcome, provider='mock', elapsed_seconds=round(elapsed, 3),
                         cleanup_confirmed=True, promotion_allowed=False), sort_keys=True))
