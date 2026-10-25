# Paper trading cutover integration blockers

Reviewed source: current `main` `app/main.py`, `app/db.py`; draft PR #20 `app/paper_atomic_service.py`; draft PR #21 and PR #24 Alembic plans.

## Verified incompatibilities

1. The planned additive migration introduces `cash_numeric`, `quantity_numeric`, `price_numeric`, `fee_numeric`, while draft PR #20 explicitly checks for `numeric` on the legacy names `cash`, `quantity`, `price`, `fee`. **A shadow-only migration does not enable the transactional service.**
2. The active API continues to write float-typed ORM fields and does not invoke the new service. It initializes the account if missing; the draft service requires an existing account.
3. Schema-type readiness does not prove data correctness, backfill completeness, or safe concurrency with legacy API writers.
4. Migration plans and the atomic service currently live in separate draft branches. A reviewed integration branch must reconcile both, with a single tested contract.

## Required cutover gates

- Read-only inventory and per-row precision/scale audit, with remediation for every rejected row.
- Tested additive backfill, dual-read comparison and full reconciliation of balances/positions.
- Verified absence of legacy writers at cutover; rollback and restore runbook.
- One reviewed schema contract (whether canonical columns are switched or service reads new shadow names).
- Concurrent integration tests through the *actual* HTTP endpoint against migrated PostgreSQL schema.
- Deployment only after explicit approval. No live brokerage operations.

This PR adds structural preflight only; it intentionally does not change the API, schema, or database.
