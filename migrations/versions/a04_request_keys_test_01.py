"""Isolated Alembic migration REHEARSAL, not a production revision chain.

Only operations against a dedicated disposable schema with an explicit opt-in.
"""
import os
import sqlalchemy as sa
from alembic import op

revision="a04_request_keys_test_01"
down_revision=None
branch_labels=None
depends_on=None
SCHEMA="a04_keys_test"

def guard():
    bind=op.get_bind()
    if (os.environ.get("A04_KEYS_DISPOSABLE")!="YES"
            or os.environ.get("A04_KEYS_SCHEMA")!=SCHEMA
            or bind.dialect.name!="postgresql"):
        raise RuntimeError("DISPOSABLE_TEST_SCHEMA_REQUIRED")
    # Refuse any database unless the connection reports the dedicated schema.
    if not bind.exec_driver_sql(
        "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='a04_keys_test')"
    ).scalar():
        raise RuntimeError("TEST_SCHEMA_MISSING")

def upgrade():
    guard()
    op.create_table(
        "paper_request_keys",
        sa.Column("account_id",sa.BigInteger(),nullable=False),
        sa.Column("request_key",sa.String(128),nullable=False),
        sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("result",sa.dialects.postgresql.JSONB(),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),
                  server_default=sa.text("now()"),nullable=False),
        sa.PrimaryKeyConstraint("account_id","request_key"),
        sa.CheckConstraint("length(request_key)>=8",name="ck_request_key_length"),
        schema=SCHEMA,
    )

def downgrade():
    guard()
    op.drop_table("paper_request_keys",schema=SCHEMA)
