"""Read-only readiness probe for Paper V2 PostgreSQL schema.

Never performs DDL, writes, migration, or account initialization.
"""
from sqlalchemy import text

EXPECTED = {
    ("paper_accounts","cash"):("numeric",20,2),
    ("paper_trades","quantity"):("numeric",24,6),
    ("paper_trades","price"):("numeric",20,2),
    ("paper_trades","fee"):("numeric",20,2),
}

def inspect_paper_v2_schema(engine):
    if engine.dialect.name!="postgresql":
        return {"ready":False,"errors":["POSTGRES_REQUIRED"]}
    errors=[]
    with engine.connect() as con:
        rows=con.execute(text("""
          SELECT table_name,column_name,data_type,numeric_precision,numeric_scale
          FROM information_schema.columns
          WHERE table_schema='public' AND table_name IN
            ('paper_accounts','paper_trades','paper_write_fence','paper_request_keys')
        """)).all()
        columns={(r.table_name,r.column_name):(r.data_type,r.numeric_precision,r.numeric_scale) for r in rows}
        for key,expected in EXPECTED.items():
            if columns.get(key)!=expected:
                errors.append("MISMATCH:"+key[0]+"."+key[1])
        for key in (("paper_write_fence","mode"),("paper_write_fence","generation"),
                    ("paper_request_keys","account_id"),("paper_request_keys","request_key"),
                    ("paper_request_keys","fingerprint"),("paper_request_keys","result")):
            if key not in columns:
                errors.append("MISSING:"+key[0]+"."+key[1])
        if not errors:
            fence=con.execute(text("SELECT mode,generation FROM public.paper_write_fence WHERE id=1")).first()
            if fence is None or fence.mode!="LEGACY" or fence.generation<0:
                errors.append("INVALID_FENCE_STATE")
    return {"ready":not errors,"errors":errors}
