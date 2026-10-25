# Alembic development-only harness

This configuration is for **disposable local PostgreSQL tests only**, not
production database migrations. It requires `A04_TEST_POSTGRES_URL` pointing
to localhost. The version file `20261025_paper_numeric_shadow.py` is
intentionally non-executable and must remain so until a reviewed real Alembic
baseline, backup/restore runbook and precision validation exist.

Do not stamp an existing production database. Do not run this configuration
against the VPS. This harness does not create a safe baseline for existing
production tables.

Run `A04_TEST_POSTGRES_URL=postgresql+psycopg://...@127.0.0.1:5432/test python -m alembic -c alembic.ini history`
to inspect revisions; `upgrade` must fail closed for the draft.
