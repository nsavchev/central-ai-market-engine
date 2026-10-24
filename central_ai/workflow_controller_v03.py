"""Central AI Workflow Controller v0.3.

Planning-only. No deployment or external execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

STAGES = ("plan", "develop", "test", "review", "approval")


@dataclass
class WorkflowState:
    task_id: str
    stage: str = "plan"
    attempts: int = 0
    max_attempts: int = 3
    approved: bool = False
    deployment_allowed: bool = False
    history: list = field(default_factory=list)


class WorkflowController:
    def __init__(self):
        self.tasks = {}

    def register(self, task):
        if not isinstance(task, dict):
            raise ValueError("INVALID_TASK")

        task_id = task.get("task_id")
        nested = task.get("task")

        if not isinstance(task_id, str) or not task_id:
            raise ValueError("INVALID_TASK_ID")

        if task_id in self.tasks:
            raise ValueError("DUPLICATE_TASK")

        if task.get("status") != "planned":
            raise ValueError("INVALID_INITIAL_STATUS")

        if not isinstance(nested, dict):
            raise ValueError("INVALID_TASK_PAYLOAD")

        if nested.get("stage") != "plan":
            raise ValueError("INVALID_INITIAL_STAGE")

        if (task.get("approved") is not False
                or task.get("deployment_allowed") is not False
                or nested.get("approved") is not False
                or nested.get("deployment_allowed") is not False):
            raise ValueError("SECURITY_BLOCK")

        state = WorkflowState(task_id=task_id)
        self.tasks[task_id] = state
        return self.status(task_id)

    def status(self, task_id):
        state = self.tasks.get(task_id)
        if state is None:
            raise ValueError("TASK_NOT_FOUND")

        return {
            "task_id": state.task_id,
            "stage": state.stage,
            "attempts": state.attempts,
            "approved": False,
            "deployment_allowed": False,
            "history": list(state.history),
        }

    def advance(self, task_id, checks_passed=False):
        state = self.tasks.get(task_id)
        if state is None:
            raise ValueError("TASK_NOT_FOUND")

        if checks_passed is not True:
            raise ValueError("CHECKS_REQUIRED")

        if state.stage == "approval":
            raise ValueError("HUMAN_APPROVAL_REQUIRED")

        index = STAGES.index(state.stage)
        previous = state.stage
        state.stage = STAGES[index + 1]

        state.history.append({
            "from": previous,
            "to": state.stage,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        })

        return self.status(task_id)

    def retry(self, task_id):
        state = self.tasks.get(task_id)
        if state is None:
            raise ValueError("TASK_NOT_FOUND")

        if state.stage not in ("test", "review"):
            raise ValueError("RETRY_NOT_ALLOWED")

        if state.attempts >= state.max_attempts:
            raise ValueError("RETRY_LIMIT_REACHED")

        previous = state.stage
        state.attempts += 1
        state.stage = "develop"

        state.history.append({
            "from": previous,
            "to": "develop",
            "reason": "retry",
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        })

        return self.status(task_id)
