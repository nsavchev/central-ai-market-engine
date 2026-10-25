"""A-04 review-only, additive Alembic revision.

DO NOT APPLY TO PRODUCTION without backups, migration baseline verification and
validated historical rows. Creates nullable shadow NUMERIC columns only; does
not silently round Float data or change the running paper API.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_paper_numeric_shadow"
down_revision = None  # Standalone draft: replace with approved baseline revision.
branch_labels = ("paper_numeric_draft",)
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("POSTGRES_REQUIRED")
    # Fail closed: a missing established Alembic baseline must be resolved
    # before running this revision. Explicit operator acknowledgement required.
    raise RuntimeError("DRAFT_MIGRATION_NOT_APPROVED")
    # Planned additive columns, not executed until a separate reviewed revision:
    # op.add_column("paper_accounts", sa.Column("cash_numeric", sa.Numeric(20,2)))
    # op.add_column("paper_trades", sa.Column("quantity_numeric", sa.Numeric(24,6)))
    # op.add_column("paper_trades", sa.Column("price_numeric", sa.Numeric(20,2)))
    # op.add_column("paper_trades", sa.Column("fee_numeric", sa.Numeric(20,2)))

def downgrade():
    raise RuntimeError("DRAFT_MIGRATION_NOT_APPROVED")
