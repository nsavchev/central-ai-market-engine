import pytest
from sqlalchemy import create_engine
from app.paper_numeric_schema_gate import EXPECTED,evaluate,inspect

def valid_rows():
    return [(table,col,"numeric",precision,scale)
            for (table,col),(precision,scale) in EXPECTED.items()]

def test_valid_schema_is_still_not_deployment_authorization():
    result=evaluate(valid_rows())
    assert result["schema_contract_met"]
    assert not result["deployment_authorized"]

def test_generic_numeric_and_wrong_scale_are_rejected():
    rows=valid_rows()
    rows[0]=("paper_accounts","cash","numeric",None,None)
    rows[1]=("paper_trades","quantity","numeric",24,2)
    result=evaluate(rows)
    assert not result["schema_contract_met"]
    assert {x["column"] for x in result["blockers"]}=={
        "paper_accounts.cash","paper_trades.quantity"}

def test_missing_and_legacy_float_rejected():
    result=evaluate([("paper_accounts","cash","double precision",53,None)])
    assert len(result["blockers"])==4

def test_non_postgresql_cannot_be_inspected():
    with pytest.raises(ValueError,match="POSTGRESQL_REQUIRED"):
        inspect(create_engine("sqlite://"))
