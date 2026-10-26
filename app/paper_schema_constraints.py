"""Read-only strict inventory for an eventual production schema review.

Never stamps or migrates a database; reports missing relational constraints.
"""
from sqlalchemy import inspect

EXPECTED_FKS = {
    "daily_bars": {("instrument_id", "instruments", "id")},
    "paper_trades": {("account_id", "paper_accounts", "id")},
}
EXPECTED_UNIQUES = {
    "instruments": {("symbol", "exchange", "currency", "sec_type", "primary_exchange")},
    "daily_bars": {("instrument_id", "day", "source")},
    "financial_snapshots": {("symbol", "period_end", "period_type", "currency", "source")},
}

def inspect_relational_constraints(engine):
    if engine.dialect.name != "postgresql":
        return {"ready": False, "errors": ["POSTGRES_REQUIRED"]}
    errors = []
    with engine.connect() as con:
        inspector = inspect(con)
        tables = set(inspector.get_table_names(schema="public"))
        for table, expected in EXPECTED_FKS.items():
            if table not in tables:
                errors.append("MISSING_TABLE:" + table)
                continue
            actual = set()
            for fk in inspector.get_foreign_keys(table, schema="public"):
                if len(fk["constrained_columns"]) == 1 and len(fk["referred_columns"]) == 1:
                    actual.add((fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0]))
            for item in expected - actual:
                errors.append("MISSING_FOREIGN_KEY:" + table + ":" + ",".join(item))
        for table, expected in EXPECTED_UNIQUES.items():
            if table not in tables:
                errors.append("MISSING_TABLE:" + table)
                continue
            actual = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table, schema="public")}
            for item in expected - actual:
                errors.append("MISSING_UNIQUE:" + table + ":" + ",".join(item))
    return {"ready": not errors, "errors": sorted(set(errors))}
