"""Read-only preflight for a future data-preserving NUMERIC migration.

This checks numeric representability; it never writes or casts data.
"""
from decimal import Decimal, InvalidOperation
from sqlalchemy import text

LIMITS = {
    "cash": (20, 2),
    "quantity": (24, 6),
    "price": (20, 2),
    "fee": (20, 2),
}

def _fits(value, precision, scale):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d!=d.quantize(Decimal(1).scaleb(-scale)):
            return False
        return abs(d) < Decimal(10) ** (precision-scale)
    except (InvalidOperation, ValueError, TypeError):
        return False

def inspect_existing_paper_values(engine):
    if engine.dialect.name!="postgresql":
        return {"ready":False,"errors":["POSTGRES_REQUIRED"]}
    errors=[]
    counts={}
    with engine.connect() as con:
        for table,columns in (("paper_accounts",("id","cash")),("paper_trades",("id","quantity","price","fee"))):
            rows=con.execute(text("SELECT "+",".join(columns)+" FROM public."+table)).all()
            counts[table]=len(rows)
            for row in rows:
                for col in columns[1:]:
                    precision,scale=LIMITS[col]
                    if not _fits(getattr(row,col),precision,scale):
                        errors.append("NOT_EXACTLY_REPRESENTABLE:"+table+"."+col+":id="+str(row.id))
    return {"ready":not errors,"errors":errors,"counts":counts}
