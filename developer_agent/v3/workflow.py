from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    PLAN = "plan"
    DEVELOP = "develop"
    TEST = "test"
    REVIEW = "review"
    APPROVAL = "approval"


NEXT_STAGE = {
    Stage.PLAN: Stage.DEVELOP,
    Stage.DEVELOP: Stage.TEST,
    Stage.TEST: Stage.REVIEW,
    Stage.REVIEW: Stage.APPROVAL,
}


@dataclass
class Workflow:
    stage: Stage = Stage.PLAN
    attempts: int = 0
    max_attempts: int = 3
    approved: bool = False
    deployment_allowed: bool = False

    def advance(self, checks_passed=False):
        if checks_passed is not True:
            raise ValueError("Checks must pass")

        if self.stage == Stage.APPROVAL:
            raise ValueError("Human approval required")

        self.stage = NEXT_STAGE[self.stage]
        return self.stage

    def retry(self):
        if self.stage not in (Stage.TEST, Stage.REVIEW):
            raise ValueError("Retry not allowed")

        if self.attempts >= self.max_attempts:
            raise ValueError("Retry limit reached")

        self.attempts += 1
        self.stage = Stage.DEVELOP
        return self.attempts
