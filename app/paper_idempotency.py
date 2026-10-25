"""Disposable-only idempotent paper fill adapter.

Assumes the caller provisioned paper_request_keys on disposable PostgreSQL.
The unique (account_id, request_key) constraint is the concurrency arbiter.
Never use with an unmigrated database.
"""
import hashlib
import json
import re
from decimal import Decimal
from sqlalchemy import text
from app.paper_atomic_service import precise, CENT, SHARE, record_paper_fill

def request_fingerprint(*, account_id, symbol, side, quantity, price, fee, generation):
    data={"account":account_id,"symbol":symbol,"side":side,
          "quantity":format(precise(quantity,SHARE,"INVALID_QUANTITY").quantize(SHARE),"f"),
          "price":format(precise(price,CENT,"INVALID_PRICE").quantize(CENT),"f"),
          "fee":format(precise(fee,CENT,"INVALID_FEE").quantize(CENT),"f"),"generation":generation}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def idempotent_fill(engine, *, request_key, account_id, symbol, side, quantity, price, fee, expected_generation):
    if not isinstance(request_key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",request_key):
        raise ValueError("INVALID_REQUEST_KEY")
    if engine.dialect.name!="postgresql":
        raise ValueError("POSTGRES_REQUIRED")
    fingerprint=request_fingerprint(account_id=account_id,symbol=symbol,side=side,
        quantity=quantity,price=price,fee=fee,generation=expected_generation)
    with engine.begin() as con:
        inserted=con.execute(text("""
            INSERT INTO paper_request_keys(account_id,request_key,fingerprint,result)
            VALUES (:account,:key,:fingerprint,NULL)
            ON CONFLICT(account_id,request_key) DO NOTHING
            RETURNING request_key
        """),{"account":account_id,"key":request_key,"fingerprint":fingerprint}).first()
        if inserted is None:
            previous=con.execute(text("""
                SELECT fingerprint,result FROM paper_request_keys
                WHERE account_id=:account AND request_key=:key FOR UPDATE
            """),{"account":account_id,"key":request_key}).first()
            if previous is None or previous.fingerprint!=fingerprint:
                raise ValueError("IDEMPOTENCY_KEY_CONFLICT")
            if previous.result is None:
                raise RuntimeError("INCOMPLETE_IDEMPOTENCY_RECORD")
            return previous.result
        result=record_paper_fill(engine,account_id=account_id,symbol=symbol,side=side,
            quantity=quantity,price=price,fee=fee,
            expected_generation=expected_generation,connection=con)
        con.execute(text("""
            UPDATE paper_request_keys SET result=CAST(:result AS jsonb)
            WHERE account_id=:account AND request_key=:key
        """),{"result":json.dumps(result),"account":account_id,"key":request_key})
        return result
