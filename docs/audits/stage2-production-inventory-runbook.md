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


## Generic restricted-runtime rehearsal (DB-ACL-REHEARSAL-01)

This is a source-derived proposal, not a record of any current deployment's
roles or configuration. Do not execute role-creating fixture tests on the VPS.
The existing `tests/test_stage2_baseline_postgres.py` and existing baseline CI
job own this rehearsal, restricted to an explicitly enabled disposable local
PostgreSQL database named `test` with an initially empty public schema.

The test creates a random, independent LOGIN with no memberships and
NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS/NOINHERIT.
It grants CONNECT, schema USAGE, USAGE on the five known serial sequences,
and the following table permissions, without object ownership or grant option:

| Existing table | Proposed permissions | Source owner requiring writes |
|---|---|---|
| instruments | SELECT, INSERT | main.ingest instrument creation |
| daily_bars | SELECT, INSERT, UPDATE | main.ingest insert/update existing bars |
| financial_snapshots | SELECT, INSERT, UPDATE | fundamentals_history.store_snapshot |
| paper_accounts | SELECT, INSERT, UPDATE | legacy paper handler / explicit account bootstrap |
| paper_trades | SELECT, INSERT | paper ledger append |

A fresh authenticated connection commits synthetic inserts with serial IDs,
FKs and updates, then independently reads them back. Other cases require
PostgreSQL insufficient_privilege (42501) for DELETE on each table, TRUNCATE,
unneeded instrument/trade UPDATE, persistent public-schema CREATE/ALTER/DROP,
sequence ALTER/setval, role creation, self-promotion and SET ROLE to the
provisioner. This does not use SET ROLE from a superuser session to simulate
isolation. Test roles/connections/grants and fixture objects are cleaned up.

Scope limits: this exercises a curated legacy schema and SQL operation shapes,
not exact deployed API HTTP behavior, RLS/tenant isolation, all inherited PUBLIC
rights, network/HBA policy or a future migrated schema. PostgreSQL PUBLIC TEMP
rights are not globally revoked by this test. It grants no privileges on future
objects and provisions no production credential. Current runtime modules,
Compose and migrations are unchanged; application bootstrap is not invoked.

### Separate acceptance and rollback before an API credential change

1. Resolve exact deployed source/image identity privately and compare its DB
   callers, startup DDL and flags against the reviewed candidate. In candidate
   source, PostgreSQL lifespan refuses startup without the explicit managed-schema
   setting and does not call create_all. Do not set that flag merely to bypass a
   legacy schema/migration gate or infer that the deployed image has this behavior.
2. Rehearse the exact approved image against a separate restored-copy schema with
   an independent runtime login; test health, auth/negative cases and authorized
   DB consumers. Use synthetic data and no production mounts or provider keys.
   Existing source permissions and paper-mode gates continue to apply.
3. Review schema/function/PUBLIC privileges, role memberships, effective grants,
   sequence access and all actual writers. Keep object ownership and migration
   administration on a separate role. Do not demote an existing shared admin or
   add broad ALL/default grants to silence errors. Missing access fails closed.
4. Prepare an exact API-only credential cutover and protected previous
   configuration/image reference. Obtain separate production authorization after
   the role setup, grants and rollback procedure are concrete and reviewed.
5. After an approved cutover, check health and DB identity/privileges from the API
   connection. If it fails, restore only the previous approved API configuration;
   do not alter schema, restore DB data, drop shared roles or activate workers as
   an improvised rollback. Previous admin credentials remain protected, not
   published in scripts, shell history or GitHub artifacts.

No production role/grant SQL or runnable deployment command is provided by this
rehearsal. Operational findings stay outside public source documentation.
