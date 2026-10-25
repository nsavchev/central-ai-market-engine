"""Read-only schema cutover compatibility check; no DDL and no account operations."""
from sqlalchemy import text

REQUIRED={
    "paper_accounts":{"cash":"numeric"},
    "paper_trades":{"quantity":"numeric","price":"numeric","fee":"numeric"},
}
SHADOW={
    "paper_accounts":("cash_numeric",),
    "paper_trades":("quantity_numeric","price_numeric","fee_numeric"),
}

def assess(engine):
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRESQL_REQUIRED")
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            rows=connection.execute(text("""
                SELECT table_name,column_name,data_type
                FROM information_schema.columns
                WHERE table_schema=current_schema()
                  AND table_name IN ('paper_accounts','paper_trades')
            """)).all()
    fields={(table,col):kind for table,col,kind in rows}
    missing_or_wrong=[
        f"{table}.{col}" for table,required in REQUIRED.items()
        for col,typ in required.items() if fields.get((table,col))!=typ
    ]
    shadows=[
        f"{table}.{col}" for table,cols in SHADOW.items()
        for col in cols if (table,col) in fields
    ]
    return {
        "ready_for_atomic_service":not missing_or_wrong,
        "blockers":missing_or_wrong,
        "shadow_fields_present":shadows,
        "note":"Structural preflight only; no permission to cut over or deploy."
    }
