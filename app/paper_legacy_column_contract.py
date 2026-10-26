"""Read-only paper legacy schema column contract (not a deploy permission)."""
from sqlalchemy import inspect

EXPECTED = {
    "paper_accounts": {
        "id": ("INTEGER", None, None, False),
        "cash": ("DOUBLE_PRECISION", None, None, False),
        "currency": ("VARCHAR", 8, None, False),
    },
    "paper_trades": {
        "id": ("INTEGER", None, None, False),
        "account_id": ("INTEGER", None, None, False),
        "symbol": ("VARCHAR", 32, None, False),
        "side": ("VARCHAR", 4, None, False),
        "quantity": ("DOUBLE_PRECISION", None, None, False),
        "price": ("DOUBLE_PRECISION", None, None, False),
        "fee": ("DOUBLE_PRECISION", None, None, False),
        "executed_at": ("TIMESTAMP", None, None, False),
    },
}

def inspect_legacy_paper_columns(engine):
    if engine.dialect.name != "postgresql":
        return {"ready": False, "errors": ["POSTGRES_REQUIRED"]}
    issues = []
    with engine.connect() as con:
        inspector = inspect(con)
        tables = set(inspector.get_table_names(schema="public"))
        for table, expected in EXPECTED.items():
            if table not in tables:
                issues.append("MISSING_TABLE:" + table)
                continue
            actual = {c["name"]: c for c in inspector.get_columns(table, schema="public")}
            for name, (type_name, length, unused, nullable) in expected.items():
                col = actual.get(name)
                if col is None:
                    issues.append("MISSING_COLUMN:" + table + "." + name)
                    continue
                typ = col["type"]
                # Timestamp WITH time zone may have dialect-specific class
                # names; only compare its broad family in this preflight.
                family = typ.__class__.__name__
                if family != type_name:
                    issues.append("TYPE_MISMATCH:" + table + "." + name)
                if length is not None and getattr(typ, "length", None) != length:
                    issues.append("LENGTH_MISMATCH:" + table + "." + name)
                if col["nullable"] != nullable:
                    issues.append("NULLABILITY_MISMATCH:" + table + "." + name)
    return {"ready": not issues, "errors": sorted(issues)}
