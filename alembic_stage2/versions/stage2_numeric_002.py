"""Linked disposable-only Paper migration supporting existing records.

The populated path participates in Alembic's connection and transaction.
Never execute on VPS or on a database other than disposable 'test'.
"""
from alembic import op
from sqlalchemy import text
from migrations.versions.stage2_paper_test_001 import upgrade as test_upgrade
from app.paper_populated_migration import migrate_populated_paper

revision="stage2_numeric_002"
down_revision="stage2_baseline_001"
branch_labels=None
depends_on=None

def upgrade():
    con=op.get_bind()
    populated=con.scalar(text("""SELECT
        EXISTS(SELECT 1 FROM public.paper_accounts)
        OR EXISTS(SELECT 1 FROM public.paper_trades)"""))
    if populated:
        migrate_populated_paper(con.engine, connection=con)
    else:
        test_upgrade()

def downgrade():
    raise RuntimeError("RESTORE_FROM_VERIFIED_BACKUP_REQUIRED")
