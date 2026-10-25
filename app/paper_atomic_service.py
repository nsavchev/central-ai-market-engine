"""Opt-in PostgreSQL-only transactional simulation service.

Requires pre-migrated NUMERIC columns and a pre-existing paper account.
Not wired to the HTTP endpoint. Never places broker orders or creates schemas.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from contextlib import nullcontext
from sqlalchemy import text
from .paper_pg_fence import check_fence

CENT=Decimal("0.01")
SHARE=Decimal("0.000001")

def precise(value, scale, label):
    try:
        if isinstance(value,bool):
            raise ValueError(label)
        number=Decimal(str(value))
        if not number.is_finite() or number!=number.quantize(scale):
            raise ValueError(label)
        return number
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(label) from None

def record_paper_fill(engine, *, account_id, symbol, side, quantity, price, fee, expected_generation, connection=None):
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRES_REQUIRED")
    if type(account_id) is not int or account_id < 1:
        raise ValueError("INVALID_ACCOUNT")
    if not isinstance(symbol,str) or not symbol.isascii() or not (1<=len(symbol)<=32) or not all(ch.isalnum() or ch in "._-" for ch in symbol):
        raise ValueError("INVALID_SYMBOL")
    if side not in ("BUY","SELL"):
        raise ValueError("INVALID_SIDE")
    qty=precise(quantity,SHARE,"INVALID_QUANTITY")
    px=precise(price,CENT,"INVALID_PRICE")
    charge=precise(fee,CENT,"INVALID_FEE")
    if qty<=0 or px<=0 or charge<0:
        raise ValueError("INVALID_FILL")
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError('INVALID_GENERATION')
    if connection is not None and (connection.engine is not engine or not connection.in_transaction()):
        raise ValueError('INVALID_TRANSACTION_CONNECTION')
    with (nullcontext(connection) if connection is not None else engine.begin()) as con:
        check_fence(con, expected_generation)
        columns=con.execute(text("""
            SELECT table_name,column_name,data_type FROM information_schema.columns
            WHERE table_schema=current_schema()
            AND ((table_name='paper_accounts' AND column_name='cash')
              OR (table_name='paper_trades' AND column_name IN ('quantity','price','fee')))
        """)).all()
        found={(r[0],r[1]):r[2] for r in columns}
        expected={('paper_accounts','cash'),('paper_trades','quantity'),('paper_trades','price'),('paper_trades','fee')}
        if any(found.get(k)!="numeric" for k in expected):
            raise ValueError("NUMERIC_SCHEMA_REQUIRED")
        row=con.execute(text("SELECT cash FROM paper_accounts WHERE id=:id FOR UPDATE"),{"id":account_id}).first()
        if row is None:
            raise ValueError("ACCOUNT_NOT_FOUND")
        cash=precise(row[0],CENT,"INVALID_CASH")
        held=con.scalar(text("""
            SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN quantity ELSE -quantity END),0)
            FROM paper_trades WHERE account_id=:id AND symbol=:symbol
        """),{"id":account_id,"symbol":symbol})
        held=precise(held,SHARE,"INVALID_HOLDINGS")
        gross=(qty*px).quantize(CENT,rounding=ROUND_HALF_EVEN)
        if side=="BUY":
            delta=-(gross+charge)
            if cash+delta<0:
                raise ValueError("INSUFFICIENT_CASH")
            next_shares=held+qty
        else:
            if held<qty:
                raise ValueError("INSUFFICIENT_SHARES")
            if charge>gross:
                raise ValueError("FEE_EXCEEDS_PROCEEDS")
            delta=gross-charge
            next_shares=held-qty
        con.execute(text("UPDATE paper_accounts SET cash=:cash WHERE id=:id"),{"cash":cash+delta,"id":account_id})
        con.execute(text("""
            INSERT INTO paper_trades(account_id,symbol,side,quantity,price,fee)
            VALUES (:id,:symbol,:side,:quantity,:price,:fee)
        """),{"id":account_id,"symbol":symbol,"side":side,"quantity":qty,"price":px,"fee":charge})
        return {"cash":str(cash+delta),"position_shares":str(next_shares),
                "mode":"SIMULATION_ONLY","db_transaction":"COMMITTED"}
