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
    assert tuple(x.value for x in OrchestratorStage)==STAGES

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

def test_legacy_differences_are_explicit_not_silently_merged():
    # Legacy accepts a truthy non-bool and retries from PLAN. Unlike the
    # canonical controller, it must not become an authorization source.
    legacy=LegacyWorkflow()
    assert legacy.advance(checks_passed=1)==LegacyStage.DEVELOP
    legacy=LegacyWorkflow()
    assert legacy.retry()==1
    assert legacy.stage==LegacyStage.DEVELOP
    assert legacy.approved is False and legacy.deployment_allowed is False

def test_orchestrator_is_task_factory_not_runtime_authority():
    manager=DeveloperOrchestrator()
    item=manager.create_task("  Inspect existing code  ")
    assert item.task=="Inspect existing code"
    assert item.stage.value==STAGES[0]
    assert item.approved is False and item.deployment_allowed is False
