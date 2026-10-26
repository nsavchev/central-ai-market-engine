"""Linked disposable-only Paper v2 migration; never on VPS market."""
from alembic import op
from migrations.versions.stage2_paper_test_001 import upgrade as test_upgrade

revision="stage2_numeric_002"
down_revision="stage2_baseline_001"
branch_labels=None
depends_on=None

def upgrade():
    test_upgrade()

def downgrade():
    raise RuntimeError("RESTORE_FROM_VERIFIED_BACKUP_REQUIRED")
