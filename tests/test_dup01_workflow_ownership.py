"""DUP-01: verify canonical workflow contract and document legacy differences."""
import pytest
from central_ai.workflow_controller_v03 import WorkflowController, STAGES
from developer_agent.v3.workflow import Workflow as LegacyWorkflow, Stage as LegacyStage
from developer_agent.v3.orchestrator import Stage as OrchestratorStage, DeveloperOrchestrator

def task(task_id="dup01"):
    return {
        "task_id":task_id, "status":"planned", "approved":False,
        "deployment_allowed":False,
        "task":{"stage":"plan","approved":False,"deployment_allowed":False},
    }

def test_three_stage_enums_have_same_labels():
    assert tuple(x.value for x in LegacyStage)==STAGES
    assert OrchestratorStage is LegacyStage

def test_canonical_requires_exact_true_for_transition():
    controller=WorkflowController()
    controller.register(task())
    for value in (None, False, 1, "yes", [], {}):
        with pytest.raises(ValueError,match="CHECKS_REQUIRED"):
            controller.advance("dup01",checks_passed=value)
    assert controller.status("dup01")["stage"]=="plan"

def test_canonical_bounded_retries_and_human_approval():
    controller=WorkflowController()
    controller.register(task())
    with pytest.raises(ValueError,match="RETRY_NOT_ALLOWED"):
        controller.retry("dup01")
    for expected in ("develop", "test", "review", "approval"):
        assert controller.advance("dup01",checks_passed=True)["stage"]==expected
    with pytest.raises(ValueError,match="HUMAN_APPROVAL_REQUIRED"):
        controller.advance("dup01",checks_passed=True)
    status=controller.status("dup01")
    assert status["approved"] is False
    assert status["deployment_allowed"] is False

def test_canonical_retry_limit():
    controller=WorkflowController()
    controller.register(task())
    controller.advance("dup01",True)
    for i in range(3):
        controller.advance("dup01",True)
        result=controller.retry("dup01")
        assert result["attempts"]==i+1
        assert result["stage"]=="develop"
    controller.advance("dup01",True)
    with pytest.raises(ValueError,match="RETRY_LIMIT_REACHED"):
        controller.retry("dup01")

def test_legacy_workflow_uses_same_fail_closed_validation():
    legacy=LegacyWorkflow()
    with pytest.raises(ValueError,match="Checks must pass"):
        legacy.advance(checks_passed=1)
    with pytest.raises(ValueError,match="Retry not allowed"):
        legacy.retry()
    assert legacy.advance(True)==LegacyStage.DEVELOP
    assert legacy.advance(True)==LegacyStage.TEST
    assert legacy.retry()==1
    assert legacy.approved is False and legacy.deployment_allowed is False

def test_orchestrator_is_task_factory_not_runtime_authority():
    manager=DeveloperOrchestrator()
    item=manager.create_task("  Inspect existing code  ")
    assert item.task=="Inspect existing code"
    assert item.stage.value==STAGES[0]
    assert item.approved is False and item.deployment_allowed is False


@pytest.mark.parametrize("report_name", [
    "passing.json", "../passing.json", "/tmp/passing.json", None,
])
def test_legacy_report_gate_rejects_without_file_access(monkeypatch, report_name):
    from pathlib import Path
    from developer_agent.v3.workflow_controller import verify_report

    def forbidden_read(*args, **kwargs):
        raise AssertionError("UNTRUSTED_REPORT_WAS_READ")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    with pytest.raises(ValueError, match="^UNVERIFIED_REPORT_BLOCKED$"):
        verify_report(report_name)


def test_legacy_report_cli_cannot_promote_a_passing_looking_report(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    report = tmp_path / "passing.json"
    report.write_text(json.dumps({
        "passed": True, "approved": False, "deployment_allowed": False,
        "suite": "workflow",
    }))
    script = Path(__file__).resolve().parents[1] / "developer_agent/v3/workflow_controller.py"
    result = subprocess.run(
        [sys.executable, str(script), "--report", str(report)],
        cwd=tmp_path, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode != 0
    assert "UNVERIFIED_REPORT_BLOCKED" in result.stderr
    assert result.stdout == ""
