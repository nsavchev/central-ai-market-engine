from dataclasses import dataclass, asdict
from enum import Enum
import json


class Stage(str, Enum):
    PLAN = "plan"
    DEVELOP = "develop"
    TEST = "test"
    REVIEW = "review"
    APPROVAL = "approval"


@dataclass
class DevelopmentTask:
    task: str
    stage: Stage = Stage.PLAN
    attempts: int = 0
    max_attempts: int = 3
    approved: bool = False
    deployment_allowed: bool = False


class DeveloperOrchestrator:
    def __init__(self):
        self.tasks = []

    def create_task(self, description):
        if not isinstance(description, str):
            raise ValueError("Invalid task")
        description = description.strip()
        if not description or len(description) > 4000:
            raise ValueError("Invalid task length")
        task = DevelopmentTask(task=description)
        self.tasks.append(task)
        return task

    def status(self, task):
        return asdict(task)


if __name__ == "__main__":
    manager = DeveloperOrchestrator()
    task = manager.create_task(
        "Implement SEC EDGAR financial import"
    )
    print(json.dumps(
        manager.status(task), indent=2
    ))
