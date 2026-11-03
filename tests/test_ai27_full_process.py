"""AI-27 integrated review -> candidate -> verifier; no Docker in unit test."""
import json
import pytest
from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch
from central_ai.verified_review_pipeline import prepare_and_verify


@pytest.mark.parametrize("passed", [True, False])
def test_full_process_preserves_source_and_refuses_deploy(tmp_path, passed):
    db=tmp_path/"tasks.sqlite"
    source=tmp_path/"source"
    source.mkdir()
    file=source/"original.py"
    file.write_text("def original():\n    return 2\n")
    untouched=file.read_bytes()
    bridge=PersistentTaskBridge(db)
    task=bridge.submit("Inspect original.py")
    registry=TaskFileTargets(db)
    registry.initialize()
    registry.register(task["task_id"],str(source),"original.py")
    assert run_batch(enabled="YES",database=str(db),agent="ai27-test",max_tasks=1,idle_checks=1,sleep=lambda _:None)["processed"]==1
    paths=[]
    for name in ("handoffs","proposals","candidates"):
        directory=tmp_path/name
        directory.mkdir(mode=0o700)
        paths.append(str(directory))
    def verifier(**kwargs):
        assert kwargs["enabled"]=="YES"
        assert kwargs["candidate"].endswith(".py")
        assert kwargs["expected_test_sha256"]=="b"*64
        assert kwargs["expected_sha256"]
        return {"passed": passed, "status":"passed" if passed else "failed"}
    def authorize(binding):
        assert binding["task_id"]==task["task_id"]
        assert binding["scope"]=="verify_only"
        return {"verification_authorized":True,"binding":binding,
                "reviewer_id":"ci-trusted-review-fixture","authorization_id":"ci-only",
                "approved":False,"deployment_allowed":False}
    report=prepare_and_verify(
        enabled="YES",database=str(db),task_id=task["task_id"],
        handoffs=paths[0],proposals=paths[1],candidates=paths[2],
        recommendation="```python\ndef candidate():\n    return 3\n```",
        trusted_test_file="/isolated/operator_test.py",trusted_test_sha256="b"*64,
        image="python@sha256:"+"a"*64,authorization_check=authorize,verifier=verifier)
    assert report["tests_passed"] is passed
    assert report["approved"] is False and report["deployment_allowed"] is False
    assert file.read_bytes()==untouched
    assert PersistentTaskBridge(db).status(task["task_id"])["status"]=="analyzed"
