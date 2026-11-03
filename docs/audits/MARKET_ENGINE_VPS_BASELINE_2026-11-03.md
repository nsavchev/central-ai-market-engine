# Market Engine legacy baseline evidence — 2026-11-03

## Operator-provided VPS evidence

Central AI API-only promotion passed exact-image, health and retained runtime
settings checks. GET /tasks/{task_id} returned 401 without a token, 401 with an
invalid token and 503 with the configured token while Task API remained NO.
The Market Engine API and production PostgreSQL container IDs/images remained
unchanged. This is not evidence of developer-loop activation or a completed #90.

PostgreSQL 16.15 reported five public base tables and 35 columns. All five
tables had zero rows at capture. No Alembic revision was observed. The catalog
queries ran in read-only transactions using a superuser, not a least-privilege
read-only login; application-role permissions remain unverified.

A private 14,496-byte logical archive was restored in a disposable PostgreSQL
container using the exact production image, no network, ports, production
mounts or credentials. Restore succeeded; table names, column UDT/nullability
and row counts matched. The test container was removed. Roles/ACL restoration,
constraint/index/sequence equivalence and populated-data preservation were NOT
proved by that restore check.

The operator extracted an 8,040-byte schema-only script from that archive:
SHA256 `93926a2bdf58683017fa6a3b12c455c15f0f8b82fdf2fd88f69a1e489f97d48d`.
The sanitized DDL pasted by the operator is transcribed in
`tests/fixtures/vps_legacy_schema_20261103.sql`. This curated fixture is not a
byte-identical copy of the private dump and excludes roles and ACLs.

## Existing validator correction

`inspect_legacy_baseline` previously relied on its caller for transaction
read-only enforcement. It now requests a PostgreSQL READ ONLY / REPEATABLE READ
transaction before querying, with bounded statement and lock waits. Existing
minimal eligibility semantics remain unchanged. No second validator, queue,
scheduler, migration, stamp operation or production execution path is added.

Real PostgreSQL regressions use the VPS DDL fixture and check successful
inspection, read-only snapshot mode, backend rejection of accidental writes,
pool reset for subsequent writers, Numeric drift and a missing required column.
The existing baseline workflow owns these tests; no new workflow is added.

## Next release blockers

Minimal `baseline_eligible=true` is not full-schema equivalence or permission to
stamp. Review constraints, indexes, serial/default/sequence definitions,
ownership, ACLs and all writers against the captured schema. Retain the
disposable-only protections on current Stage 2 migrations. Then prepare a
separately reviewed production baseline and linked migration, rehearse upgrade
and rollback twice on restored copies with realistic data, and test consumers.
No production migration, Market Engine promotion, task activation, merge or
live trading is authorized by this evidence.
