from app.paper_db_readiness import combine

def test_rejects_float_and_missing_baseline():
    report=combine(
        {"revision_count":0,"blockers":["ALEMBIC_BASELINE_MISSING_OR_EMPTY",
                                        "LEGACY_TYPE:paper_accounts.cash:double precision"]},
        {"schema_contract_met":False,"blockers":[{"column":"paper_accounts.cash"}]})
    assert report["status"]=="BLOCKED"
    assert "PRECISION:paper_accounts.cash" in report["blockers"]
    assert not report["deployment_authorized"]

def test_passed_structure_never_authorizes_deployment():
    report=combine(
        {"revision_count":1,"blockers":[]},
        {"schema_contract_met":True,"blockers":[]})
    assert report["status"]=="STRUCTURAL_CHECKS_PASSED"
    assert not report["deployment_authorized"]
