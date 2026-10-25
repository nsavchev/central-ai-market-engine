"""Stage 2 rehearsal only: no production Alembic chain or automatic execution."""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision="stage2_paper_test_001"
down_revision=None
branch_labels=None
depends_on=None

def _guard():
    bind=op.get_bind()
    if bind.dialect.name!="postgresql" or os.getenv("STAGE2_DISPOSABLE_DB")!="YES":
        raise RuntimeError("DISPOSABLE_POSTGRES_REQUIRED")
    db=bind.exec_driver_sql("SELECT current_database()").scalar()
    if db!="test":
        raise RuntimeError("REFUSE_NON_TEST_DATABASE")
    for name in ("paper_accounts","paper_trades"):
        if bind.exec_driver_sql("SELECT to_regclass(:name)",{"name":"public."+name}).scalar() is None:
            raise RuntimeError("MISSING_LEGACY_TABLE:"+name)
    if bind.exec_driver_sql("SELECT EXISTS(SELECT 1 FROM public.paper_accounts)").scalar() or bind.exec_driver_sql("SELECT EXISTS(SELECT 1 FROM public.paper_trades)").scalar():
        raise RuntimeError("PAPER_TABLES_NOT_EMPTY")

def upgrade():
    _guard()
    op.alter_column("paper_accounts","cash",type_=sa.Numeric(20,2),
                    existing_type=sa.Float(),schema="public",
                    postgresql_using="cash::numeric(20,2)")
    for col,precision,scale in (("quantity",24,6),("price",20,2),("fee",20,2)):
        op.alter_column("paper_trades",col,type_=sa.Numeric(precision,scale),
                        existing_type=sa.Float(),schema="public",
                        postgresql_using=f"{col}::numeric({precision},{scale})")
    op.create_table("paper_write_fence",
        sa.Column("id",sa.Integer,primary_key=True),
        sa.Column("mode",sa.Text,nullable=False),
        sa.Column("generation",sa.BigInteger,nullable=False),
        sa.CheckConstraint("id=1"),sa.CheckConstraint("mode IN ('LEGACY','QUIESCED')"),
        sa.CheckConstraint("generation>=0"),schema="public")
    op.execute("INSERT INTO public.paper_write_fence(id,mode,generation) VALUES(1,'LEGACY',0)")
    op.create_table("paper_request_keys",
        sa.Column("account_id",sa.BigInteger,nullable=False),
        sa.Column("request_key",sa.String(128),nullable=False),
        sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("result",JSONB),
        sa.PrimaryKeyConstraint("account_id","request_key"),
        sa.CheckConstraint("length(request_key)>=8"),schema="public")

def downgrade():
    _guard()
    op.drop_table("paper_request_keys",schema="public")
    op.drop_table("paper_write_fence",schema="public")
    for col in ("quantity","price","fee"):
        op.alter_column("paper_trades",col,type_=sa.Float(),existing_type=sa.Numeric(),schema="public",
                        postgresql_using=f"{col}::double precision")
    op.alter_column("paper_accounts","cash",type_=sa.Float(),existing_type=sa.Numeric(),schema="public",
                    postgresql_using="cash::double precision")
