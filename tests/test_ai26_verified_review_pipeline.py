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
