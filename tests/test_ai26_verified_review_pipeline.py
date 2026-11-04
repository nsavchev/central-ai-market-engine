import pytest
from central_ai.verified_review_pipeline import prepare_and_verify


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
    return dict(enabled='YES', database=database, task_id=task_id, handoffs='', proposals='',
                candidates='', recommendation='', trusted_test_file='/ci/test.py',
                trusted_test_sha256='b'*64, image='python@sha256:'+'c'*64,
                authorization_check=authorize, verifier=lambda **kwargs: result)


def valid_result(**changes):
    result = dict(passed=True, status='passed', executed_candidate=True,
                  test_sha256='b'*64, returncode=0)
    result.update(changes)
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
