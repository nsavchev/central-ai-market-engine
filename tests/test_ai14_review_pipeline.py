"""AI-14: one end-to-end integration across the existing AI-10..AI-13 stages."""
import json
from pathlib import Path

from central_ai.persistent_bridge import PersistentTaskBridge
from central_ai.task_file_targets import TaskFileTargets
from central_ai.worker_batch import run_batch
from central_ai.review_handoff import create_review_handoff
from central_ai.proposal_adapter import create_proposal_from_handoff
from central_ai.verifier_gate import check_proposal_for_verifier


def test_complete_review_only_pipeline_reopened(tmp_path):
    database = tmp_path / "tasks.sqlite"
    source = tmp_path / "source"
    source.mkdir()
    file = source / "sample.py"
    file.write_text("def invariant():\n    return 42\n")
    original = file.read_bytes()
    handoffs = tmp_path / "handoffs"
    handoffs.mkdir(mode=0o700)
    proposals = tmp_path / "proposals"
    proposals.mkdir(mode=0o700)

    task_id = PersistentTaskBridge(database).submit("Read-only sample.py analysis")["task_id"]
    targets = TaskFileTargets(database)
    targets.initialize()
    targets.register(task_id, str(source), "sample.py")
    batch = run_batch(enabled="YES", database=str(database), agent="ai14-integration",
                      max_tasks=1, idle_checks=1, sleep=lambda _: None)
    assert batch["processed"] == 1

    handoff = create_review_handoff(enabled="YES",database=str(database),
                                    task_id=task_id,output_directory=str(handoffs))
    proposal = create_proposal_from_handoff(
        enabled="YES",handoff_path=handoff["path"],
        output_directory=str(proposals),
        recommendation="Review analysis and plan tests; no source modification.",
    )
    result = check_proposal_for_verifier(enabled="YES", proposal_path=proposal["path"])
    assert result["verifier_status"] == "awaiting_isolated_candidate"
    assert result["tests_executed"] is False
    assert result["approved"] is False and result["deployment_allowed"] is False
    assert file.read_bytes() == original
    assert PersistentTaskBridge(database).status(task_id)["status"] == "analyzed"
    assert list(source.iterdir()) == [file]
    record = json.loads(Path(proposal["path"]).read_text())
    assert record["patch"] is None and record["target"] is None
    assert record["review_status"] == "pending"
