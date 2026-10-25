"""Read-only combined database readiness report. Never grants deployment approval."""
from app.paper_alembic_inventory import inspect_schema
from app.paper_numeric_schema_gate import inspect as inspect_precision

def combine(baseline, precision):
    blockers=list(baseline["blockers"])
    blockers.extend("PRECISION:"+row["column"] for row in precision["blockers"])
    return {
        "status":"BLOCKED" if blockers else "STRUCTURAL_CHECKS_PASSED",
        "revision_count":baseline["revision_count"],
        "blockers":sorted(set(blockers)),
        "numeric_contract_met":precision["schema_contract_met"],
        "deployment_authorized":False,
        "notes":"Read-only metadata checks; no data reconciliation, backups or production approval."
    }

def inspect(engine):
    return combine(inspect_schema(engine),inspect_precision(engine))
