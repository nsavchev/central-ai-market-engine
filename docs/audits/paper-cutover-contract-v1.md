# Paper ledger cutover contract v1 — review gate

Status: DESIGN ONLY / NO EXECUTION. This document reconciles PR #20 with #21–#27.

## Decision

Use a **staged, additive migration**. Keep `paper_accounts.cash` and
`paper_trades.{quantity,price,fee}` as legacy FLOAT until backfill and audit
are complete. New shadow columns are `cash_numeric`, `quantity_numeric`,
`price_numeric` and `fee_numeric`.

The proposed atomic service in PR #20 checks canonical column types and
therefore **must remain disabled** while columns have shadow names.
Do not adapt the service merely to accept shadows while legacy writers remain
active: it would split the accounting source of truth.

## Migration phases / entry conditions

| Phase | Change | Verifiable exit gate |
|---|---|---|
| 0 | Inventory live schema and running API version (read-only) | Backup + restore test; current writers identified |
| 1 | Add nullable numeric shadow columns | Alembic migration and downgrade tests in disposable PostgreSQL |
| 2 | Backfill in controlled batches | All rows accounted for; zero unapproved rounding, nonfinite or overflow |
| 3 | Stop **all** legacy float writers | Enforced maintenance/feature flag; prove no concurrent writers |
| 4 | Cut over inside reviewed transaction | Canonical NUMERIC columns; atomically switch ORM/service; constraints and data parity |
| 5 | Re-enable simulation-only API | Real HTTP integration tests, row locks, retries, invariant checks |
| 6 | Observe and retire old columns | Approved rollback window ended; audited backups and production sign-off |

## Exact service invariants

- `paper_accounts.cash NUMERIC(20,2)`
- `paper_trades.quantity NUMERIC(24,6)`
- `paper_trades.price NUMERIC(20,2)`
- `paper_trades.fee NUMERIC(20,2)`
- Single authoritative account row locked with `SELECT ... FOR UPDATE`
  before reading cash and holdings for each mutation.
- Failed transaction must not change cash or trade history.
- No automatic account creation in the new service until a separately
  reviewed bootstrap contract handles concurrent first writes.
- Do not use the draft service with legacy ORM FLOAT mappings.
- Real HTTP authentication, idempotency keys and safe retry behavior are
  required before endpoint cutover; tests of a standalone service are not enough.
- No broker orders, market execution, valuation or FX assumptions.

## Review blockers

The current PRs are independent/stacked drafts, not a merged compatible system.
The protected Alembic revision intentionally cannot run. Existing PostgreSQL
data have not been inspected, migrated or reconciled. These facts **block**
claims of production readiness. PR #27 covers schema-only readiness; it does
not establish a successful cutover.

## Required integration PR before cutover

Create one reviewed branch based on the approved merge state that includes:
(1) true Alembic baseline and migrations, (2) Decimal ORM, (3) atomic service,
(4) HTTP wiring, (5) version/feature flag, (6) migration rehearsal and
rollback, (7) concurrent and restart/idempotency tests. Keep it draft until
all production approvals and backup/restore evidence are available.
