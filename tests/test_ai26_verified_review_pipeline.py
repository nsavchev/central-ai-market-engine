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
