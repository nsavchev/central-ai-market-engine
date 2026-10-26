# Stage 2 production read-only inventory — operator runbook

**This PR does not connect to, inspect or modify the VPS.** The SQL in
`docs/audits/stage2-production-inventory.sql` is a reviewable, read-only
inventory. It is intended for an operator to execute under a read-only
PostgreSQL role, after verifying the database target. It does not collect
financial rows or secrets; it includes counts, column definitions, indexes,
constraints and identity/default metadata.

## Next required steps

1. Verify the running deployment and identify the actual PostgreSQL target
   without exposing credentials or changing the stack.
2. Obtain the schema inventory from a read-only session; keep results private.
3. Compare it with the original deployed ORM, migrated ORM and full Alembic
   DDL. In particular confirm `id` sequences/defaults and the differences
   between `LEGACY` and `QUIESCED` writer fences.
4. Verify fresh, independent backup and restore before any write or stamp.
5. Prepare a separate production migration with preflight, lock timeout,
   explicit approval and rollback plan. Never run CI fixture tests on VPS.

**Unresolved:** Current Alembic environment and migrations are deliberately
restricted to the disposable DB named `test`. Passing tests is not release
approval. The user has not granted authorization for schema updates on
`market`, deployment, or merges.
