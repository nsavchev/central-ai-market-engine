"""Disposable PostgreSQL test-only shadow-column migration.

Never part of the production revision chain. Deliberately requires a private
test schema and an explicit environment opt-in before any DDL.
"""
import os
from alembic import op
import sqlalchemy as sa

revision = "a04_shadow_test_01"
down_revision = "20261025_paper_numeric_shadow"
branch_labels = None
depends_on = None

def _guard():
    if os.environ.get("A04_DISPOSABLE_MIGRATION") != "YES":
        raise RuntimeError("DISPOSABLE_MIGRATION_ONLY")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("POSTGRES_REQUIRED")
    if os.environ.get("A04_TEST_SCHEMA") != "a04_migration_test":
        raise RuntimeError("TEST_SCHEMA_REQUIRED")

def upgrade():
    _guard()
    op.add_column("paper_accounts", sa.Column("cash_numeric", sa.Numeric(20,2)), schema="a04_migration_test")
    op.add_column("paper_trades", sa.Column("quantity_numeric", sa.Numeric(24,6)), schema="a04_migration_test")
    op.add_column("paper_trades", sa.Column("price_numeric", sa.Numeric(20,2)), schema="a04_migration_test")
    op.add_column("paper_trades", sa.Column("fee_numeric", sa.Numeric(20,2)), schema="a04_migration_test")

def downgrade():
    _guard()
    for name in ("fee_numeric","price_numeric","quantity_numeric"):
        op.drop_column("paper_trades", name, schema="a04_migration_test")
    op.drop_column("paper_accounts", "cash_numeric", schema="a04_migration_test")
