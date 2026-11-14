import json
import pytest
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch
from central_ai.review_pipeline import prepare_review_pipeline

def test_single_path_after_analyzed_task(tmp_path):
    db=tmp_path/"tasks.sqlite"
    src=tmp_path/"src"
    src.mkdir()
    file=src/"module.py"
    file.write_text("def original():\n    return 3\n")
    original=file.read_bytes()
    task=PersistentTaskBridge(db).submit("Analyze module.py")
    targets=TaskFileTargets(db)
    targets.initialize()
    targets.register(task["task_id"],str(src),"module.py")
    assert run_batch(enabled="YES",database=str(db),agent="ai25-test",max_tasks=1,idle_checks=1,sleep=lambda _:None)["processed"]==1
    dirs=[]
    for name in ("handoffs","proposals","candidates"):
        p=tmp_path/name
        p.mkdir(mode=0o700)
        dirs.append(str(p))
    result=prepare_review_pipeline(enabled="YES",database=str(db),task_id=task["task_id"],
       handoffs=dirs[0],proposals=dirs[1],candidates=dirs[2],
       recommendation="```python\ndef reviewed():\n    return 5\n```")
    assert result["deployment_allowed"] is False
    assert result["executed"] is False
    assert (tmp_path/"candidates"/("candidate_"+task["task_id"]+".py")).exists()
    assert file.read_bytes()==original

def test_disabled_fails_without_side_effects(tmp_path):
    with pytest.raises(ValueError,match="PIPELINE_DISABLED"):
        prepare_review_pipeline(enabled="",database="",task_id="",handoffs="",
                                proposals="",candidates="",recommendation="")


def test_candidate_rejects_proposal_text_changed_after_gate(monkeypatch,tmp_path):
    import central_ai.review_pipeline as pipeline
    original=pipeline.check_proposal_for_verifier
    def corrupt_after_check(**kwargs):
        result=original(**kwargs)
        from pathlib import Path
        path=Path(kwargs['proposal_path']);data=json.loads(path.read_text())
        data['ai_recommendations']=['```python\ndef substituted(): return 999\n```']
        path.write_text(json.dumps(data))
        return result
    monkeypatch.setattr(pipeline,'check_proposal_for_verifier',corrupt_after_check)
    with pytest.raises(ValueError,match='PROPOSAL_RECOMMENDATION_CHANGED'):
        test_single_path_after_analyzed_task(tmp_path)
    assert list((tmp_path/"candidates").iterdir()) == []
    assert (tmp_path/"src"/"module.py").read_text() == "def original():\n    return 3\n"
