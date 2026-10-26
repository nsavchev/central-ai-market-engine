"""Opt-in disposable PostgreSQL migration preserving existing paper rows.

NOT a production migration. Execute only inside a caller-controlled transaction
against an isolated database literally named 'test'. No live cutover.
"""
import os
from decimal import Decimal
from sqlalchemy import text
from .paper_data_preflight import inspect_existing_paper_values

def migrate_populated_paper(engine):
    if os.getenv("STAGE2_DISPOSABLE_DB")!="YES" or engine.dialect.name!="postgresql":
        raise PermissionError("DISPOSABLE_ONLY")
    if engine.url.database!="test":
        raise PermissionError("REFUSE_NON_TEST_DATABASE")
    # Exclusive lock prevents writes between validation and conversion.
    with engine.begin() as con:
        if con.scalar(text("SELECT current_database()"))!="test":
            raise PermissionError("REFUSE_NON_TEST_DATABASE")
        con.execute(text("LOCK TABLE public.paper_accounts, public.paper_trades IN ACCESS EXCLUSIVE MODE"))
        for table,col,precision,scale in (
            ("paper_accounts","cash",20,2),
            ("paper_trades","quantity",24,6),
            ("paper_trades","price",20,2),
            ("paper_trades","fee",20,2),
        ):
            info=con.execute(text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table AND column_name=:col
            """),{"table":table,"col":col}).scalar()
            if info!="double precision":
                raise ValueError("UNEXPECTED_LEGACY_TYPE:"+table+"."+col)
            # Database-native numeric conversion check is evaluated under lock.
            # Strict inequality after roundtrip catches loss of precision.
            rejected=con.scalar(text(f"""
                SELECT EXISTS(SELECT 1 FROM public.{table}
                WHERE {col} IS NULL OR NOT isfinite({col})
                   OR {col}::numeric != round({col}::numeric, {scale})
                   OR abs({col}::numeric) >= power(10::numeric,{precision-scale}))
            """))
            if rejected:
                raise ValueError("LOSSY_OR_INVALID_DATA:"+table+"."+col)
        before={
            "accounts":con.scalar(text("SELECT count(*) FROM public.paper_accounts")),
            "trades":con.scalar(text("SELECT count(*) FROM public.paper_trades")),
        }
        for table,col,p,s in (
            ("paper_accounts","cash",20,2),
            ("paper_trades","quantity",24,6),
            ("paper_trades","price",20,2),
            ("paper_trades","fee",20,2),
        ):
            con.execute(text(f"ALTER TABLE public.{table} ALTER COLUMN {col} TYPE numeric({p},{s}) USING {col}::numeric({p},{s})"))
        con.execute(text("""CREATE TABLE public.paper_write_fence(
            id integer primary key CHECK(id=1), mode text NOT NULL
            CHECK(mode IN ('LEGACY','QUIESCED')), generation bigint NOT NULL CHECK(generation>=0))"""))
        con.execute(text("INSERT INTO public.paper_write_fence VALUES(1,'QUIESCED',1)"))
        con.execute(text("""CREATE TABLE public.paper_request_keys(
            account_id bigint NOT NULL,request_key varchar(128) NOT NULL,
            fingerprint varchar(64) NOT NULL,result jsonb,
            PRIMARY KEY(account_id,request_key))"""))
        assert con.scalar(text("SELECT count(*) FROM public.paper_accounts"))==before["accounts"]
        assert con.scalar(text("SELECT count(*) FROM public.paper_trades"))==before["trades"]
        return before
