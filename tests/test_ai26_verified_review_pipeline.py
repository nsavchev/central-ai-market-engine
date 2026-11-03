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
