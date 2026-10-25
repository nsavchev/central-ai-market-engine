# A-04 executable migration rehearsal — isolation rules

This revision is intentionally stacked after the **blocked** draft revision, so normal `alembic upgrade head` continues to fail closed. To rehearse only this revision, tests must invoke its `upgrade()` / `downgrade()` functions with an Alembic Operations context bound to a disposable PostgreSQL instance. Those tests must explicitly set `A04_DISPOSABLE_MIGRATION=YES` and `A04_TEST_SCHEMA=a04_migration_test`.

The revision only adds nullable shadow columns to tables in that isolated schema. It does **not** backfill existing float values, change the application ORM, or provide a production migration baseline. Production cutover is explicitly out of scope.
