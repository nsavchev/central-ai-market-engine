# Stage 2 production migration release gates

Status: **NOT APPROVED; DO NOT DEPLOY**

The disposable-only migration prototype is not an Alembic production revision.
Its tests verify example rows, a precision-loss refusal, and NaN refusal;
these are necessary but insufficient for a production cutover.

## Mandatory gates
1. Fresh read-only inventory of actual `market` schema, constraints,
   indexes, defaults, row counts, ownership, connected clients and all writers.
2. Verified `pg_dump -Fc` plus an independent restore and exact-value comparison.
3. Full approval-controlled Alembic baseline & data-preserving revision,
   not reusable disposable `test`-only code.
4. Validate existing data types, finite values, exact precision/scale,
   NULLs, collisions, orphan keys and schema differences before locking.
5. Use a transaction, bounded lock timeout, and tested rollback-on-error.
   Confirm schemas, balances and row checksums after migration.
6. Cut off ALL legacy writer paths before data conversion, including
   background workers, replicas, API endpoints and automation.
7. Rehearse on two separate restored snapshots with populated records;
   test compatibility with the exact deployed API/ORM versions.
8. Confirm idempotency, fence semantics and constraints match the actual
   paper atomic service models. Compare DDL exactly, not by table name.
9. Have explicit operator-approved deploy, maintenance window,
   stop conditions and a verified restore plan.
10. Re-enable trading only in paper mode after monitoring confirms safety.

## Existing critical blockers
- The prototype adds request-keys/fence using independently authored
  DDL, which may differ from the established migration/schema contract.
- The disposable prototype has no Alembic version integration.
- The original `market` schema and real data must be inspected anew.
- Legacy APIs and Decimal response compatibility need cutover audit.

Never run CI's DROP/CREATE TABLE tests against `market`, `market_restore_test`,
or any database outside disposable `test`.
