import json
import pytest
from central_ai.proposal_adapter import create_proposal_from_handoff


def test_existing_proposal_schema_without_patch(tmp_path):
    source_dir = tmp_path / "handoffs"
    source_dir.mkdir(mode=0o700)
    dest = tmp_path / "proposals"
    dest.mkdir(mode=0o700)
    task_id = "12345678-1234-4234-8234-123456789abc"
    source = source_dir / ("handoff_" + task_id + ".json")
    source.write_text(json.dumps({
        "schema":"ai11-review-handoff-v1",
        "task_id":task_id,
        "source_status":"analyzed",
        "proposal_status":"review_required",
        "approved":False,
        "deployment_allowed":False,
        "production_modified":False,
        "patch":None,
        "test_status":"not_run"
    }))
    result = create_proposal_from_handoff(enabled="YES",handoff_path=str(source),
                                         output_directory=str(dest),recommendation="Propose tests, no deployment")
    proposal = json.loads((dest / ("proposal_" + task_id + ".json")).read_text())
    assert result["review_status"] == "pending"
    assert proposal["target"] is None and proposal["patch"] is None
    assert proposal["approved"] is False and proposal["deployment_allowed"] is False
    assert proposal["ai_recommendations"] == ["Propose tests, no deployment"]
    with pytest.raises(FileExistsError):
        create_proposal_from_handoff(enabled="YES",handoff_path=str(source),output_directory=str(dest),recommendation="duplicate")


def test_disabled_and_unsafe_handoff(tmp_path):
    with pytest.raises(ValueError, match="PROPOSAL_DISABLED"):
        create_proposal_from_handoff(enabled="",handoff_path="",output_directory="",recommendation="")
    source = tmp_path / "handoff_invalid.json"
    source.write_text('{"approved":true}')
    with pytest.raises(ValueError):
        create_proposal_from_handoff(enabled="YES",handoff_path=str(source),output_directory=str(tmp_path),recommendation="test")
