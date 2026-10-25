"""Test-only integration of transactional fence and hypothetical fill.

Not wired to FastAPI and does not access brokers.
"""
from decimal import Decimal
from sqlalchemy import text
from app.paper_pg_fence import check_fence

def fenced_buy(engine, *, generation, cost):
    amount=Decimal(str(cost))
    if not amount.is_finite() or amount<=0 or amount.as_tuple().exponent < -2:
        raise ValueError("INVALID_COST")
    with engine.begin() as con:
        # Lock fence before account, same order for every cooperating writer.
        check_fence(con,generation)
        row=con.execute(text("SELECT cash FROM paper_accounts WHERE id=1 FOR UPDATE")).first()
        if row is None or row.cash < amount:
            raise ValueError("INSUFFICIENT_CASH")
        con.execute(text("UPDATE paper_accounts SET cash=cash-:cost WHERE id=1"),{"cost":amount})
        con.execute(text("INSERT INTO paper_trades(cost) VALUES(:cost)"),{"cost":amount})
