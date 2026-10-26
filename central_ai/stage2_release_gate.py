"""Read-only release evidence assessment. Never grants deployment permission.

The Central AI controller may summarize evidence, but may not approve,
merge, deploy, migrate databases, or trade.
"""
from dataclasses import dataclass

REQUIRED_EVIDENCE = (
    "ci_green",
    "production_schema_reviewed",
    "all_writers_inventoried",
    "fresh_backup_restored",
    "migration_rehearsed",
    "rollback_rehearsed",
    "security_reviewed",
    "human_approval_recorded",
)

@dataclass(frozen=True)
class ReleaseAssessment:
    ready_for_human_review: bool
    missing: tuple[str, ...]
    approved: bool = False
    deployment_allowed: bool = False

def assess_stage2_release(evidence: dict) -> ReleaseAssessment:
    if not isinstance(evidence, dict):
        raise TypeError("INVALID_EVIDENCE")
    unknown = set(evidence) - set(REQUIRED_EVIDENCE)
    if unknown:
        raise ValueError("UNKNOWN_EVIDENCE")
    missing = tuple(name for name in REQUIRED_EVIDENCE if evidence.get(name) is not True)
    return ReleaseAssessment(ready_for_human_review=not missing, missing=missing)
