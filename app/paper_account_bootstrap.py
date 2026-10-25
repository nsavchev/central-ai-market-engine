"""Explicit, transaction-safe bootstrap for an empty simulation account.

This module never runs on import or application startup. Operator must call
it explicitly after schema validation, using a PostgreSQL engine.
"""
from decimal import Decimal
from sqlalchemy import text
from .paper_atomic_service import precise, CENT

def bootstrap_paper_account(engine, *, account_id=1, initial_cash="100000.00"):
    if engine.dialect.name != "postgresql" or type(account_id) is not int or account_id < 1:
        raise ValueError("POSTGRES_ACCOUNT_REQUIRED")
    balance=precise(initial_cash,CENT,"INVALID_INITIAL_CASH")
    if balance<=0:
        raise ValueError("INVALID_INITIAL_CASH")
    # Database constraints and conflict check prevent a double-funded account.
    with engine.begin() as con:
        schema=con.execute(text("""
            SELECT data_type,numeric_precision,numeric_scale
            FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name='paper_accounts' AND column_name='cash'
        """)).first()
        if schema is None or tuple(schema)!=("numeric",20,2):
            raise ValueError("NUMERIC_ACCOUNT_SCHEMA_REQUIRED")
        result=con.execute(text("""
            INSERT INTO paper_accounts(id,cash,currency)
            VALUES (:id,:cash,'USD')
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """),{"id":account_id,"cash":balance}).first()
        if result is None:
            raise ValueError("ACCOUNT_ALREADY_EXISTS")
    return {"account_id":account_id,"initial_cash":str(balance),"created":True}
