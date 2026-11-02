import json
import pytest
from central_ai.isolated_candidate import prepare_candidate


def test_ast_candidate_is_created_without_execution(tmp_path):
    proposals=tmp_path/"proposals"
    proposals.mkdir(mode=0o700)
    candidates=tmp_path/"candidates"
    candidates.mkdir(mode=0o700)
    task_id="12345678-1234-4234-8234-123456789abc"
    source=proposals/"proposal.json"
    proposal={"id":task_id,"status":"draft","approved":False,"deployment_allowed":False,
              "production_modified":False,"target":None,"patch":None,
              "review_status":"pending","test_status":"not_run",
              "ai_recommendations":["```python\ndef example():\n    return 1\n```"]}
    source.write_text(json.dumps(proposal))
    result=prepare_candidate(enabled="YES",proposal_path=str(source),candidate_directory=str(candidates))
    assert result["executed"] is False
    assert result["deployment_allowed"] is False
    assert (candidates/("candidate_"+task_id+".py")).read_text()=="def example():\n    return 1\n"
    with pytest.raises(FileExistsError):
        prepare_candidate(enabled="YES",proposal_path=str(source),candidate_directory=str(candidates))


def test_candidate_guards(tmp_path):
    with pytest.raises(ValueError, match="CANDIDATE_DISABLED"):
        prepare_candidate(enabled="",proposal_path="",candidate_directory="")
