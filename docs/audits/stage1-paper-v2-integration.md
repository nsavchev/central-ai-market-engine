# Stage 1: integration branch (draft only)

The existing `/paper/trades` remains unchanged by default. If
`PAPER_V2_ENABLED=YES`, it refuses new legacy fills (409).
The new authenticated `/paper/v2/trades` fails closed unless the same flag
is enabled and `PAPER_V2_DATABASE_NAME` matches the active SQLAlchemy
database. It requires an `Idempotency-Key` header and delegates to the
transactional idempotency/fence service; it never places broker orders.

**NOT DEPLOYABLE YET:** No live migration was run; `market` lacks the
NUMERIC schema and idempotency/fence tables. The paper account bootstrap,
old account reader, concurrent bootstrap, decimal ORM, schema precision
check, permissions, and safe rollback remain integration blockers. A flag
and database name comparison are not sufficient database isolation: actual
test execution must use the isolated test database and role. All writer
paths and runtime configuration must be inventoried before any enablement.

Next: test against disposable PostgreSQL in CI with an authenticated HTTP
request and preseeded account; require successful BUY/SELL/replay/fence tests.
No merge, VPS deployment or production DB modifications.
