"""Disposable PostgreSQL-only idempotency schema rehearsal.

This is deliberately NOT an Alembic production migration. Never run on VPS.
"""
from sqlalchemy import text

DDL="""CREATE TABLE IF NOT EXISTS paper_request_keys (
 account_id BIGINT NOT NULL,
 request_key VARCHAR(128) NOT NULL,
 fingerprint CHAR(64) NOT NULL,
 result JSONB,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT pk_paper_request_keys PRIMARY KEY(account_id,request_key),
 CONSTRAINT ck_paper_request_keys_request_length CHECK(length(request_key)>=8)
)"""

def create_disposable_schema(connection):
    if connection.dialect.name!="postgresql" or not connection.in_transaction():
        raise PermissionError("POSTGRES_TRANSACTION_REQUIRED")
    connection.execute(text(DDL))
