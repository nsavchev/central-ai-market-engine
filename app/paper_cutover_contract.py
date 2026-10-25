"""Static, fail-closed paper contract for integration planning.

No database access or execution capability.
"""
from dataclasses import dataclass

EXPECTED = {
    "paper_accounts.cash": "NUMERIC(20,2)",
    "paper_trades.quantity": "NUMERIC(24,6)",
    "paper_trades.price": "NUMERIC(20,2)",
    "paper_trades.fee": "NUMERIC(20,2)",
}
SHADOW = {
    "paper_accounts.cash_numeric",
    "paper_trades.quantity_numeric",
    "paper_trades.price_numeric",
    "paper_trades.fee_numeric",
}

@dataclass(frozen=True)
class CutoverEvidence:
    canonical_columns: dict[str, str]
    shadow_columns_present: frozenset[str]
    backup_restored: bool = False
    all_rows_reconciled: bool = False
    legacy_writers_stopped: bool = False
    http_concurrency_tests_pass: bool = False
    approved: bool = False

def check(e: CutoverEvidence):
    blockers = []
    for name, expected_type in EXPECTED.items():
        if e.canonical_columns.get(name) != expected_type:
            blockers.append("CANONICAL_SCHEMA:" + name)
    for key, ok in (
        ("BACKUP_RESTORE", e.backup_restored),
        ("DATA_RECONCILIATION", e.all_rows_reconciled),
        ("LEGACY_WRITERS", e.legacy_writers_stopped),
        ("HTTP_CONCURRENCY", e.http_concurrency_tests_pass),
        ("MANUAL_APPROVAL", e.approved),
    ):
        if not ok:
            blockers.append(key)
    return {"ready_for_reviewed_cutover": not blockers,
            "blockers": blockers,
            "shadow_fields_present": sorted(e.shadow_columns_present & SHADOW)}
