"""Read-only aggregate conversion risk report for PostgreSQL FLOAT paper tables.

No row values, credentials or personal holdings are emitted. No changes made.
"""
from sqlalchemy import text
FIELDS={"paper_accounts":{"cash":2},"paper_trades":{"quantity":6,"price":2,"fee":2}}
def report(engine):
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRES_REQUIRED")
    findings={}
    with engine.connect() as con:
        with con.begin():
            con.execute(text("SET TRANSACTION READ ONLY"))
            for table,cols in FIELDS.items():
                field_results={}
                for col,scale in cols.items():
                    # All identifiers fixed by code.
                    result=con.execute(text(f"""
                        SELECT COUNT(*) AS total,
                          COUNT(*) FILTER(WHERE {col} IS NULL) AS missing,
                          COUNT(*) FILTER(WHERE {col} IS NOT NULL AND NOT isfinite({col})) AS nonfinite,
                          COUNT(*) FILTER(WHERE isfinite({col})
                            AND {col}::numeric <> round({col}::numeric, {scale})) AS precision_loss
                        FROM {table}
                    """)).one()
                    field_results[col]={"total":result[0],"null":result[1],
                                        "nonfinite":result[2],"precision_loss":result[3]}
                findings[table]=field_results
    return {"read_only":True,"checks":findings,"warning":"Review original Float provenance; this does not authorize migration."}
