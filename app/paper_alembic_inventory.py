"""Read-only Alembic/schema metadata report, never applies migrations.

Caller supplies a PostgreSQL SQLAlchemy Engine with read-only credentials.
No production connection is configured here.
"""
from sqlalchemy import text

EXPECTED={"paper_accounts":{"id","cash"},"paper_trades":{"id","quantity","price","fee"}}

def evaluate_inventory(*, revisions, columns):
    problems=[]
    if not revisions:
        problems.append("ALEMBIC_BASELINE_MISSING_OR_EMPTY")
    elif len(revisions)!=1:
        problems.append("ALEMBIC_MULTIPLE_HEADS")
    for table,required in EXPECTED.items():
        missing=required-set(columns.get(table,{}))
        problems.extend(f"MISSING:{table}.{c}" for c in sorted(missing))
    for table,c in (("paper_accounts","cash"),("paper_trades","quantity"),
                    ("paper_trades","price"),("paper_trades","fee")):
        kind=columns.get(table,{}).get(c)
        if kind is not None and kind!="numeric":
            problems.append(f"LEGACY_TYPE:{table}.{c}:{kind}")
    return {"revision_count":len(revisions),"table_types":columns,
            "blockers":problems,"cutover_approved":False}

def inspect_schema(engine):
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRESQL_REQUIRED")
    with engine.connect() as con:
        with con.begin():
            con.execute(text("SET TRANSACTION READ ONLY"))
            names=set(con.scalars(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema=current_schema()
                  AND table_name IN ('alembic_version','paper_accounts','paper_trades')
            """)))
            revisions=[]
            if "alembic_version" in names:
                revisions=list(con.scalars(text("SELECT version_num FROM alembic_version")))
            rows=con.execute(text("""
                SELECT table_name,column_name,data_type FROM information_schema.columns
                WHERE table_schema=current_schema()
                  AND table_name IN ('paper_accounts','paper_trades')
            """)).all()
    cols={k:{} for k in EXPECTED}
    for table,name,kind in rows:
        cols[table][name]=kind
    return evaluate_inventory(revisions=revisions,columns=cols)
