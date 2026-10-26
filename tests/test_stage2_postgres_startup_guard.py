import pytest
from unittest.mock import patch
from app import main

@pytest.mark.asyncio
async def test_postgres_startup_requires_schema_approval(monkeypatch):
    fake=type("Engine",(),{"dialect":type("Dialect",(),{"name":"postgresql"})()})()
    monkeypatch.delenv("MARKET_SCHEMA_MANAGED_BY_ALEMBIC",raising=False)
    with patch("app.db.engine",fake),patch.object(main,"init_db",side_effect=AssertionError("DDL_CALLED")):
        with pytest.raises(RuntimeError,match="POSTGRES_SCHEMA_APPROVAL_REQUIRED"):
            async with main.lifespan(main.app):
                pass

@pytest.mark.asyncio
async def test_postgres_approved_startup_does_not_create_tables(monkeypatch):
    fake=type("Engine",(),{"dialect":type("Dialect",(),{"name":"postgresql"})()})()
    monkeypatch.setenv("MARKET_SCHEMA_MANAGED_BY_ALEMBIC","YES")
    with patch("app.db.engine",fake),patch.object(main,"init_db",side_effect=AssertionError("DDL_CALLED")):
        async with main.lifespan(main.app):
            pass
