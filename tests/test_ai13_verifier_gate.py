import json
import pytest
from central_ai.verifier_gate import check_proposal_for_verifier


def test_gate_accepts_review_only_draft(tmp_path):
    p=tmp_path/"proposal.json"
    base={"id":"sample","status":"draft","approved":False,"deployment_allowed":False,
          "production_modified":False,"patch":None,"target":None,"test_status":"not_run",
          "review_status":"pending","tests":[],"ai_recommendations":["Review safely"]}
    p.write_text(json.dumps(base))
    result=check_proposal_for_verifier(enabled="YES", proposal_path=str(p))
    assert result["tests_executed"] is False
    assert result["deployment_allowed"] is False
    for change in ({"approved":True},{"deployment_allowed":True},{"patch":"diff"},{"target":"app/main.py"}):
        invalid=dict(base,**change)
        p.write_text(json.dumps(invalid))
        with pytest.raises(ValueError,match="VERIFIER_GATE_BLOCKED"):
            check_proposal_for_verifier(enabled="YES",proposal_path=str(p))


def test_gate_default_off(tmp_path):
    with pytest.raises(ValueError,match="VERIFIER_GATE_DISABLED"):
        check_proposal_for_verifier(enabled="",proposal_path=str(tmp_path/"missing"))
