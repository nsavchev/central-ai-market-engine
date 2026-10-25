"""Read-only PostgreSQL preflight for future Float-to-NUMERIC paper ledger migration.

Prints aggregated counts only; never dumps holdings, symbols, amounts or credentials.
Requires an explicitly supplied PostgreSQL URL, no writes, no DDL.
"""
import argparse
import json
from sqlalchemy import create_engine, text

TABLE_COLUMNS = {
    "paper_accounts": ("cash",),
    "paper_trades": ("quantity", "price", "fee"),
}

def inspect(engine):
    if engine.dialect.name != "postgresql":
        raise ValueError("POSTGRESQL_REQUIRED")
    findings = {}
    with engine.connect() as con:
        with con.begin():
            con.execute(text("SET TRANSACTION READ ONLY"))
            for table, columns in TABLE_COLUMNS.items():
                found = con.execute(text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema=current_schema()
                      AND table_name=:table_name
                """), {"table_name": table}).all()
                types = dict(found)
                if not types:
                    findings[table] = {"state": "MISSING_TABLE"}
                    continue
                details = {"state": "INSPECTED", "columns": {}}
                for col in columns:
                    if col not in types:
                        details["columns"][col] = {"state": "MISSING_COLUMN"}
                        continue
                    # Identifiers are hard-coded and not derived from user input.
                    row = con.execute(text(f"""
                        SELECT COUNT(*) FILTER (WHERE {col} IS NULL) AS null_count,
                               COUNT(*) FILTER (WHERE NOT isfinite({col})) AS nonfinite_count,
                               COUNT(*) FILTER (
                                 WHERE isfinite({col}) AND {col} < 0
                               ) AS negative_count
                        FROM {table}
                    """)).one()
                    details["columns"][col] = {
                        "type": types[col],
                        "null_count": row[0],
                        "nonfinite_count": row[1],
                        "negative_count": row[2],
                    }
                findings[table] = details
    return findings

def main():
    parser=argparse.ArgumentParser(description="Read-only paper ledger numeric migration preflight")
    parser.add_argument("--database-url", required=True, help="PostgreSQL connection URL (not printed)")
    args=parser.parse_args()
    engine=create_engine(args.database_url, pool_pre_ping=True)
    try:
        result=inspect(engine)
        print(json.dumps(result, indent=2))
    finally:
        engine.dispose()

if __name__ == "__main__":
    main()
