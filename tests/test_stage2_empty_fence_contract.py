"""Regression contract: empty Stage 2 migration must start fully fenced.

Static and narrow because the full Alembic integration runs in separate CI.
"""
from pathlib import Path


def test_empty_migration_starts_quiesced():
    source = Path("migrations/versions/stage2_paper_test_001.py").read_text()
    assert "VALUES(1,'QUIESCED',1)" in source
    assert "VALUES(1,'LEGACY',0)" not in source


def test_populated_migration_starts_quiesced():
    source = Path("app/paper_populated_migration.py").read_text()
    assert "VALUES(1,'QUIESCED',1)" in source
