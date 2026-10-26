import pytest
from central_ai.stage2_release_gate import (
    REQUIRED_EVIDENCE, assess_stage2_release,
)

def test_missing_evidence_blocks_review_and_deployment():
    result = assess_stage2_release({"ci_green": True})
    assert not result.ready_for_human_review
    assert "fresh_backup_restored" in result.missing
    assert result.approved is False
    assert result.deployment_allowed is False

def test_all_evidence_never_grants_approval():
    result = assess_stage2_release({key: True for key in REQUIRED_EVIDENCE})
    assert result.ready_for_human_review
    assert result.missing == ()
    assert result.approved is False
    assert result.deployment_allowed is False

@pytest.mark.parametrize("value", [False, None, 1, "YES", "true", []])
def test_only_exact_boolean_true_counts(value):
    result = assess_stage2_release({key: value for key in REQUIRED_EVIDENCE})
    assert not result.ready_for_human_review

def test_unknown_keys_rejected():
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE"):
        assess_stage2_release({"deployment_allowed": True})
