# Proposed paper NUMERIC migration — draft revision

This intentionally non-executable Alembic revision documents the intended versioned migration while preventing accidental application. It is not a substitute for an approved Alembic baseline.

Before any executable upgrade:
1. Create/version the repository Alembic baseline and confirm live schema lineage.
2. Verify backups and restore to an isolated PostgreSQL instance.
3. Inventory NULL, NaN, infinity, fractional precision and out-of-range Float data.
4. Add nullable shadow columns, backfill without silent rounding, verify record-by-record and reconcile totals.
5. Use row locks and atomic transactions for hypothetical fills; prevent writes from legacy code during cutover.
6. Define rollback of both schema and application, with confirmed restore.
7. Run migrations, downgradability and concurrent ledger integration tests against disposable PostgreSQL only.

The existing API still uses Float columns. No live execution, data migration, approval or real order placement is enabled by this draft.
