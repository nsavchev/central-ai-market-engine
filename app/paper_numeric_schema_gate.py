"""Read-only PostgreSQL precision/scale gate; never mutates schema or data."""
from sqlalchemy import text

EXPECTED = {
    ("paper_accounts","cash"):(20,2),
    ("paper_trades","quantity"):(24,6),
    ("paper_trades","price"):(20,2),
    ("paper_trades","fee"):(20,2),
}

def evaluate(rows):
    seen={(table,col):(type_name,precision,scale)
          for table,col,type_name,precision,scale in rows}
    blockers=[]
    for name,(precision,scale) in EXPECTED.items():
        actual=seen.get(name)
        if actual != ("numeric",precision,scale):
            blockers.append({"column":".".join(name),
                             "expected":f"numeric({precision},{scale})",
                             "observed":None if actual is None else str(actual)})
    return {"schema_contract_met":not blockers,
            "blockers":blockers,
            "deployment_authorized":False}

def inspect(engine):
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRESQL_REQUIRED")
    with engine.connect() as con:
        with con.begin():
            con.execute(text("SET TRANSACTION READ ONLY"))
            rows=con.execute(text("""
                SELECT table_name,column_name,data_type,
                       numeric_precision,numeric_scale
                FROM information_schema.columns
                WHERE table_schema=current_schema()
                  AND table_name IN ('paper_accounts','paper_trades')
            """)).all()
    return evaluate(rows)
