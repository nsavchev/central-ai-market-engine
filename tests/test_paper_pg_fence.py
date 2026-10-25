import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, text
from app.paper_pg_fence import check_fence, quiesce

URL=os.getenv("TEST_POSTGRES_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable PostgreSQL only")

@pytest.fixture
def engine():
    db=create_engine(URL,pool_size=4)
    with db.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS paper_write_fence"))
        con.execute(text("""CREATE TABLE paper_write_fence (
            id int primary key CHECK(id=1), mode text NOT NULL
            CHECK(mode IN ('LEGACY','QUIESCED')), generation bigint NOT NULL)"""))
        con.execute(text("INSERT INTO paper_write_fence VALUES(1,'LEGACY',0)"))
    yield db
    with db.begin() as con:
        con.execute(text("DROP TABLE paper_write_fence"))
    db.dispose()

def test_denies_unapproved_quiescence(engine):
    with engine.begin() as con:
        with pytest.raises(PermissionError, match="APPROVAL_REQUIRED"):
            quiesce(con,generation=0)
    with engine.begin() as con:
        check_fence(con,0)

def test_quiescence_persists_and_rejects_stale_writes(engine):
    with engine.begin() as con:
        assert quiesce(con,generation=0,approved=True)==1
    with engine.begin() as con:
        with pytest.raises(PermissionError,match="PAPER_WRITES_FENCED"):
            check_fence(con,0)
    with engine.connect() as con:
        assert con.scalar(text("SELECT generation FROM paper_write_fence WHERE id=1"))==1

def test_fence_and_write_are_serialized(engine):
    def write():
        with engine.begin() as con:
            check_fence(con,0)
            return True
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert pool.submit(write).result()
    with engine.begin() as con:
        quiesce(con,generation=0,approved=True)
    with pytest.raises(PermissionError,match="PAPER_WRITES_FENCED"):
        write()
