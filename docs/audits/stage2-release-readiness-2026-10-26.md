# Stage 2 audit — release readiness (2026-10-26)

**Verdict: NO-GO for production.** This document summarizes verified source-code
findings, not a review or change of the running VPS. Do not merge the stacked
draft PRs or migrate `market` based only on green CI.

## Verified test coverage
- Linked disposable Alembic revisions baseline -> NUMERIC.
- Populated-account conversion, strict decimal representability and DDL rollback.
- PostgreSQL foreign keys and unique constraints (synthetic schema).
- ORM Decimal reads and authenticated account API response.
- Legacy route 409 while explicitly disabled; V2 QUIESCED 409.
- V2 simulated fill, key replay, conflict and stale generation; replay using
  a fresh HTTP client and Python process, retaining PostgreSQL state.

## Blocking findings

**P0: NO deployable production Alembic chain.**
`alembic_stage2/env.py` requires `STAGE2_DISPOSABLE_DB=YES`,
`TEST_POSTGRES_URL` ending in `/test`, and checks the connected database name.
The baseline and populated conversion also refuse non-test databases.
Building a reviewed production-specific chain is still required.

**P0: Existing writer cutover is not fail-closed by default.**
`app/main.py` legacy `/paper/trades` defaults
`PAPER_LEGACY_WRITES_ENABLED` to `YES`, and its float-based implementation
does not lock `paper_write_fence`. Every legacy writer and deployment replica
must be disabled and independently verified before converting live columns.
An operator changing `PAPER_V2_ENABLED` does not prove all writer processes
are quiesced.

**P0: Live-schema equivalence has NOT been proven.**
`app/paper_migration_baseline.py` checks required column names and four Float
types, not exact definitions, nullability, indexes, sequences, defaults,
identity behavior, permissions, all foreign keys and constraints.
`app/paper_schema_constraints.py` is a separate, read-only partial check;
it is not enforced by the Alembic baseline. Synthetic fixtures are not a
complete clone of the running `market` schema.

**P0: Verified fresh backup and restore needed.**
A prior snapshot check is not sufficient. A new backup plus isolated restore,
checksums/counts/financial comparison, and recovery drill are mandatory.

**P1: Migration/activation semantics require an explicit runbook.**
The empty-paper rehearsal initializes `paper_write_fence` as
`LEGACY, generation=0`; the populated prototype initializes
`QUIESCED, generation=1`. `check_fence()` permits writes only in `LEGACY`
mode. The latter label is therefore also used for opt-in V2 paper writes;
this naming and activation must be reviewed and verified across all writers.
No automatic promotion to `LEGACY` may occur during deployment.

**P1: Startup can create schema implicitly.**
`app/main.py` lifespan calls `init_db()`, which invokes
`Base.metadata.create_all(engine)`. Production rollout must be governed by
Alembic instead; first ensure that application startup cannot silently
create/alter the expected deployment contract.

**P1: Numeric/API compatibility and sequence contract.**
The legacy account reader now emits decimal strings, not prior JSON numbers.
All downstream clients must be checked. The V2 fill inserts trade rows without
supplying `id`; production `paper_trades.id` identity/sequence/default
must be validated and any restored sequence advanced safely.

**P1: Financial values and concurrency.**
Test with populated realistic restores, NULLs, nonfinite values, precision
boundaries, active writes and concurrent duplicate keys. Validate the exact
PostgreSQL locks, lock timeout and user privileges.

## Exit gates, in order
1. Inventory the actual deployed `market` read-only; full schema diff.
2. Trace every writer and API deployment, then design quiescence switch and
   rollback procedures; do not enable V2 by default.
3. Fresh encrypted backup with verified separate restore and integrity checks.
4. Author production-reviewed Alembic baseline and value-preserving upgrade;
   make it fail closed for any schema mismatch or active writers.
5. Rehearse with populated restored data twice, including concurrency, crash,
   lock-timeout and recovery scenarios.
6. Verify cross-version ORM/API consumers, sequencing, indexes and constraints.
7. Security/code review and explicit human approval of a maintenance window.
8. Only then staged VPS deployment and paper-only smoke tests, with written
   stop/restore criteria. Real brokerage orders remain out of scope.

## Operational restrictions
No merge of the stacked PRs, no VPS command, no schema stamp, no production
migration, and no external trading is authorized by this audit.
