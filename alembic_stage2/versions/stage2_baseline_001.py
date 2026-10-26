"""No-op version stamp for existing legacy schema. Disposable only."""
import os
from alembic import op
from sqlalchemy import text
from app.paper_migration_baseline import inspect_legacy_baseline

revision="stage2_baseline_001"
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    if os.getenv("STAGE2_DISPOSABLE_DB")!="YES":
        raise RuntimeError("DISPOSABLE_ONLY")
    con=op.get_bind()
    if con.execute(text("SELECT current_database()")).scalar()!="test":
        raise RuntimeError("DISPOSABLE_ONLY")
    result=inspect_legacy_baseline(con.engine)
    if not result["baseline_eligible"]:
        raise RuntimeError("LEGACY_BASELINE_MISMATCH:"+",".join(result["errors"]))

def downgrade():
    raise RuntimeError("BASELINE_DOWNGRADE_UNSUPPORTED")
