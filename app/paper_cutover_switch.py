"""Fail-closed pure state gate for paper ledger cutover. No live switching."""
from dataclasses import dataclass
from enum import Enum

class Phase(str, Enum):
    LEGACY = "LEGACY"
    QUIESCED = "QUIESCED"
    NUMERIC_READY = "NUMERIC_READY"

@dataclass(frozen=True)
class Evidence:
    backup_restored: bool = False
    all_rows_reconciled: bool = False
    legacy_writers_stopped: bool = False
    schema_verified: bool = False
    http_tests_pass: bool = False
    approved: bool = False

def transition(current: Phase, desired: Phase, evidence: Evidence) -> Phase:
    """Plan allowed state only. Never invokes database or API operations."""
    if current == desired:
        return current
    if current == Phase.LEGACY and desired == Phase.QUIESCED:
        if not evidence.legacy_writers_stopped or not evidence.backup_restored:
            raise PermissionError("QUIESCE_REQUIRES_EVIDENCE")
        return desired
    if current == Phase.QUIESCED and desired == Phase.NUMERIC_READY:
        if not all((evidence.backup_restored,evidence.all_rows_reconciled,
                    evidence.legacy_writers_stopped,evidence.schema_verified,
                    evidence.http_tests_pass,evidence.approved)):
            raise PermissionError("CUTOVER_NOT_AUTHORIZED")
        return desired
    raise PermissionError("INVALID_PHASE_TRANSITION")
