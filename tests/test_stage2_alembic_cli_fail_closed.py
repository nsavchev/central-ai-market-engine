"""Fail-closed Stage 2 Alembic CLI guard, without connecting to any database."""
import os
import subprocess
import pytest

@pytest.mark.parametrize("url,flag,expected", [
    ("postgresql+psycopg://invalid:invalid@127.0.0.1:1/market", "YES", "DISPOSABLE_URL_REQUIRED"),
    ("postgresql+psycopg://invalid:invalid@127.0.0.1:1/test", "NO", "DISPOSABLE_ONLY"),
    ("postgresql+psycopg://invalid:invalid@127.0.0.1:1/market", "NO", "DISPOSABLE_ONLY"),
    ("sqlite:///./market.db", "YES", "DISPOSABLE_URL_REQUIRED"),
])
def test_alembic_cli_refuses_non_disposable_target_without_connection(url, flag, expected):
    env = {**os.environ, "TEST_POSTGRES_URL": url, "STAGE2_DISPOSABLE_DB": flag}
    result = subprocess.run(
        ["alembic", "-c", "alembic-stage2.ini", "upgrade", "head"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert result.returncode != 0
    assert expected in (result.stdout + result.stderr)

def test_alembic_offline_mode_never_emits_sql():
    result = subprocess.run(
        ["alembic", "-c", "alembic-stage2.ini", "upgrade", "head", "--sql"],
        env={**os.environ, "STAGE2_DISPOSABLE_DB": "YES",
             "TEST_POSTGRES_URL": "postgresql+psycopg://x:y@127.0.0.1:1/test"},
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert result.returncode != 0
    assert "OFFLINE_MIGRATIONS_DISABLED" in (result.stdout + result.stderr)
