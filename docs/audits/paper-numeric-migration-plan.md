# Paper ledger NUMERIC migration — preflight only (A-03)

**Status: review required. No production migration or DDL in this PR.**

Current `app/db.py` stores paper-account cash and hypothetical trade quantity, price and fees using Float. The new isolated Decimal arithmetic in draft PR #17 is not yet wired to the FastAPI ledger.

## Recommended design
- Proposed precision: cash/price/fee `NUMERIC(20,2)`; trade quantity `NUMERIC(24,6)`. Review whether sub-cent execution prices are needed before choosing scale; a strict two-decimal price is a deliberate constraint, not a universal market convention.
- Change Python ORM types to `Decimal` via SQLAlchemy `Numeric` only after migration and API review.
- Never cast or round existing float rows silently. Preflight each row for representation, bounds and rounding deltas; require explicit remediation of outliers.
- Use Alembic versioned, reversible migrations. Prefer additive shadow columns plus verification and a reviewed cutover over an in-place ALTER of live columns.
- Preserve a restorable PostgreSQL backup and verify restore on a separate environment.
- At cutover, pause writes or enforce database serialization; check aggregate balances and row-count parity. Implement row-level locking for paper account updates to prevent lost updates and overspending.
- Run integration tests on a throwaway PostgreSQL instance with concurrency, retries, rollback and crash recovery.
- Paper ledger remains SIMULATION_ONLY, not a backtest or broker execution system.

## Read-only helper
`python -m app.paper_numeric_preflight --database-url 'postgresql+psycopg://...'`

**Do not use the helper on production before review.** It reports aggregate counts only and validates metadata; it does not modify data. URL arguments may appear in shell process lists, so use securely injected credentials when operationalized.

## Release blockers
No installed Alembic migration structure, historical data precision audit, dual-write/cutover plan, confirmed rollback, concurrent transaction locking, or real VPS schema inspection is included here.
