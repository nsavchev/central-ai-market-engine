# A04 request-key migration rehearsal

This isolated Alembic revision creates and removes paper_request_keys in
a04_keys_test ONLY. It has no connection to the production revision history;
the file has down_revision=None for test use and MUST NOT be included in a
production Alembic upgrade path.

CI invokes the upgrade and downgrade functions through Alembic Operations
against a disposable PostgreSQL 16 service; it does not run `alembic upgrade head`.
This tests DDL and a rollback only, not the deployed database's baseline.
No claim of production readiness; migration chain, role permissions, backups,
retention of request keys, and deployment rollback remain to be reviewed.
