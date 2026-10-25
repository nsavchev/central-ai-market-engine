import pytest
from sqlalchemy import create_engine
from app.paper_alembic_inventory import evaluate_inventory,inspect_schema

def test_no_baseline_blocks():
    result=evaluate_inventory(revisions=[],columns={
        "paper_accounts":{"id":"integer","cash":"double precision"},
        "paper_trades":{"id":"integer","quantity":"double precision",
                        "price":"double precision","fee":"double precision"}})
    assert "ALEMBIC_BASELINE_MISSING_OR_EMPTY" in result["blockers"]
    assert any(x.startswith("LEGACY_TYPE:") for x in result["blockers"])
    assert not result["cutover_approved"]

def test_schema_numeric_not_approval():
    result=evaluate_inventory(revisions=["some_revision"],columns={
        "paper_accounts":{"id":"integer","cash":"numeric"},
        "paper_trades":{"id":"integer","quantity":"numeric",
                        "price":"numeric","fee":"numeric"}})
    assert result["blockers"]==[]
    assert not result["cutover_approved"]

def test_multiple_heads_are_blocker():
    result=evaluate_inventory(revisions=["a","b"],columns={})
    assert "ALEMBIC_MULTIPLE_HEADS" in result["blockers"]

def test_rejects_non_postgres():
    with pytest.raises(ValueError,match="POSTGRESQL_REQUIRED"):
        inspect_schema(create_engine("sqlite://"))
