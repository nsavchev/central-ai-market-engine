import json
import uuid
from pathlib import Path

from developer_agent.v3.orchestrator import DeveloperOrchestrator

BASE = Path("developer_agent/v3")
PLANS = BASE / "plans"
TASKS = BASE / "tasks"


def main():
    source = PLANS / "sec_edgar_plan.json"

    if source.is_symlink() or not source.is_file():
        raise RuntimeError("Invalid plan source")

    data = json.loads(source.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise RuntimeError("Invalid plan structure")

    task_text = data.get("task")
    plan_text = data.get("plan")

    if not isinstance(task_text, str) or not task_text.strip():
        raise RuntimeError("Invalid task")

    if not isinstance(plan_text, str) or not plan_text.strip():
        raise RuntimeError("Invalid plan")

    if (
        data.get("stage") != "plan"
        or data.get("approved") is not False
        or data.get("deployment_allowed") is not False
    ):
        raise RuntimeError("Unsafe plan state")

    manager = DeveloperOrchestrator()
    task = manager.create_task(task_text)

    result = {
        "id": uuid.uuid4().hex,
        "task": manager.status(task),
        "plan_source": source.name,
        "stage": "plan",
        "approved": False,
        "deployment_allowed": False,
        "execution_allowed": False,
    }

    if TASKS.is_symlink():
        raise RuntimeError("Invalid tasks directory")

    TASKS.mkdir(parents=True, exist_ok=True, mode=0o700)

    output = TASKS / f"{result['id']}.json"

    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("PLAN_BRIDGE_SUCCESS")
    print("TASK_ID:", result["id"])
    print("STAGE: plan")
    print("EXECUTION_ALLOWED: False")
    print("DEPLOYMENT_ALLOWED: False")


if __name__ == "__main__":
    main()
