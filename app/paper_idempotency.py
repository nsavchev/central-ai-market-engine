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
    # Advisory lock is scoped to the session transaction; serializes same-key
    # requests before the nested record_paper_fill transaction begins.
    # All key reservation + ledger mutations MUST share the SAME DB transaction.
    # The existing record_paper_fill opens its own transaction; therefore
    # this adapter fails closed until it can accept a connection.
    raise RuntimeError("ATOMIC_IDEMPOTENCY_CONNECTION_REQUIRED")
