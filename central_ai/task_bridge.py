"""Central AI Task Bridge v0.1 - planning only."""

from dataclasses import asdict
from uuid import uuid4
from datetime import datetime, timezone

from developer_agent.v3.orchestrator import (
    DeveloperOrchestrator,
)


class TaskBridge:
    def __init__(self):
        self.manager = DeveloperOrchestrator()
        self.registry = {}

    def submit(self, description):
        if not isinstance(description, str):
            raise ValueError("INVALID_TASK")

        description = description.strip()

        if not description or len(description) > 4000:
            raise ValueError("INVALID_TASK_LENGTH")

        task = self.manager.create_task(description)
        task_id = str(uuid4())

        record = {
            "task_id": task_id,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": "planned",
            "task": asdict(task),
            "approved": False,
            "deployment_allowed": False,
        }

        self.registry[task_id] = record
        return record

    def status(self, task_id):
        if task_id not in self.registry:
            raise ValueError("TASK_NOT_FOUND")

        return self.registry[task_id]


if __name__ == "__main__":
    bridge = TaskBridge()

    result = bridge.submit(
        "Implement SEC EDGAR financial import "
        "with source validation and permissions"
    )

    import json
    print(json.dumps(result, indent=2))
