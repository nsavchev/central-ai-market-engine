import pytest
from central_ai.verified_review_pipeline import prepare_and_verify


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
def test_authorization_denial_never_calls_verifier(monkeypatch,change):
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
        pipeline.prepare_and_verify(enabled="YES",database="",task_id="task-1",handoffs="",
            proposals="",candidates="",recommendation="",trusted_test_file="/ci/test.py",
            trusted_test_sha256="b"*64,image="python@sha256:"+"c"*64,
            authorization_check=authorizer,verifier=forbidden)


def test_previous_receipt_cannot_authorize_new_invocation(monkeypatch):
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
        return {"passed":True,"status":"passed"}
    params=dict(enabled="YES",database="",task_id="task-1",handoffs="",proposals="",
        candidates="",recommendation="",trusted_test_file="/ci/test.py",
        trusted_test_sha256="b"*64,image="python@sha256:"+"c"*64,
        authorization_check=authorizer,verifier=verifier)
    report=pipeline.prepare_and_verify(**params)
    assert report["approved"] is False and report["deployment_allowed"] is False
    with pytest.raises(ValueError,match="REVIEW_AUTHORIZATION_DENIED"):
        pipeline.prepare_and_verify(**params)
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


def test_hmac_adapter_in_existing_pipeline(monkeypatch):
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
        return {"passed":True,"status":"passed"}
    result=pipeline.prepare_and_verify(enabled="YES",database="",task_id="ci-task",handoffs="",
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
