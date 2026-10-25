# Stage 2 readiness gap

The successful disposable Alembic test does **not** approve production cutover.

Current `app/db.py` still models PaperAccount.cash and PaperTrade quantity,
price, fee as Float; `app/main.py` still has the float-based legacy account
reader and `init_db()` on startup. These should be changed together as part
of the reviewed cutover, **not** independently on an active VPS.

This PR adds a read-only database-schema probe. It must not be executed as
an application-startup initializer, and a positive result is necessary but
not sufficient for approval: checks still needed include account data,
unique constraints, writer fencing, idempotency concurrency, schema version,
authorization, archived backup integrity, and full rollback runbook.

The disposable-only migration has `down_revision=None`. It must NOT be
mistaken for a real production Alembic history; production has no version
tracking yet and needs an explicitly reviewed baseline. Do not apply to
`market` or `market_restore_test`.
