"""Read-only guard for a legacy Alembic baseline. Never stamps databases."""
from sqlalchemy import inspect, text

REQUIRED = {
    "instruments": {"id", "symbol", "exchange", "currency", "sec_type", "primary_exchange"},
    "daily_bars": {"id", "instrument_id", "day", "open", "high", "low", "close", "volume", "source", "fetched_at"},
    "financial_snapshots": {"id", "symbol", "period_end", "period_type", "currency", "source", "payload", "imported_at"},
    "paper_accounts": {"id", "cash", "currency"},
    "paper_trades": {"id", "account_id", "symbol", "side", "quantity", "price", "fee", "executed_at"},
}
FLOAT_PAPER = {("paper_accounts","cash"),("paper_trades","quantity"),("paper_trades","price"),("paper_trades","fee")}

def inspect_legacy_baseline(engine):
    if engine.dialect.name != "postgresql":
        return {"baseline_eligible": False, "errors": ["POSTGRES_REQUIRED"]}
    problems=[]
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True
    ) as con:
        con.execute(text("SET LOCAL statement_timeout = '10s'"))
        con.execute(text("SET LOCAL lock_timeout = '2s'"))
        inspector=inspect(con)
        names=set(inspector.get_table_names(schema="public"))
        for table,columns in REQUIRED.items():
            if table not in names:
                problems.append("MISSING_TABLE:"+table)
                continue
            actual={c["name"]:c for c in inspector.get_columns(table,schema="public")}
            for col in columns:
                if col not in actual:
                    problems.append("MISSING_COLUMN:"+table+"."+col)
                elif (table,col) in FLOAT_PAPER and actual[col]["type"].__class__.__name__ != "DOUBLE_PRECISION":
                    problems.append("UNEXPECTED_LEGACY_TYPE:"+table+"."+col)
        for forbidden in ("alembic_version","paper_request_keys","paper_write_fence"):
            if forbidden in names:
                problems.append("ALREADY_VERSIONED_OR_MIGRATED:"+forbidden)
        # Only a read-only snapshot is reported. The baseline must never
        # be stamped merely because this minimal check passes.
        counts={}
        for table in ("paper_accounts","paper_trades"):
            if table in names:
                counts[table]=con.execute(text("SELECT count(*) FROM public."+table)).scalar()
    return {"baseline_eligible":not problems,"errors":sorted(problems),"paper_counts":counts}

