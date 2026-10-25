# VPS PostgreSQL inventory — operator runbook (read only)

Status: NOT EXECUTED. No VPS connectivity or read-only account confirmed.

**Prerequisites:** an operator identifies the actual PostgreSQL database, schema,
service deployment commit, all active writer services and an independently
verified restore-capable backup. Use a purpose-created SELECT-only database
role with no CREATE, INSERT, UPDATE, DELETE, ALTER or DROP rights.

1. Connect using an approved database client. Keep credentials out of chat,
   shell history, logs and GitHub. Do not expose the PostgreSQL server publicly.
2. Run `docs/audits/sql/a04_inventory_readonly.sql`. It explicitly begins a
   read-only transaction. Copy only the resulting *metadata* (database/schema
   name may be redacted); do not upload row contents or secrets.
3. If the Alembic version table exists, run the separately noted SELECT from
   `alembic_version` in a new read-only transaction. Never infer the version
   from GitHub migration files.
4. Review `paper_accounts` and `paper_trades` canonical data types,
   numeric scale/precision, nullability, and constraints. Presence of
   `paper_request_keys` and `paper_write_fence` must be verified independently.
5. Cross-check these facts against PR #45. A successful structure report does
   NOT authorize deployment. Backfill/data reconciliation, concurrent writer
   gates and a restore drill remain mandatory.

Safety limitations: no DDL/DML, no migrations, no application restart,
no manual DB writes or real orders. If an accurate role/schema cannot be
established, STOP. Do not guess which database is production.

## SuperHosting VPS / Docker Compose — one-shot metadata check

The previously observed deployment path is `/opt/central-ai/release-v1/market_engine_v0_9`
with Compose service `db`, PostgreSQL user `market` and database `market`.
**Verify these details locally before running**; they are historical observations,
not a current connection validation.

From the existing VPS SSH session, run this read-only query (no passwords
included; do not paste credentials). This command does not change schemas:

```sh
cd /opt/central-ai/release-v1/market_engine_v0_9
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U market -d market <<'SQL'
BEGIN READ ONLY;
SELECT current_database() AS db, current_schema() AS schema,
       current_user AS db_role, current_setting('server_version') AS pg_version;
SELECT to_regclass('public.alembic_version') AS alembic_version_table;
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('paper_accounts','paper_trades',
                     'paper_request_keys','paper_write_fence')
ORDER BY table_name, ordinal_position;
ROLLBACK;
SQL
```

If `alembic_version_table` returned `public.alembic_version`, run this
second command to read the existing migration revision; otherwise skip it:

```sh
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U market -d market \
  -c "BEGIN READ ONLY; SELECT version_num FROM public.alembic_version; ROLLBACK;"
```

**Do not execute Alembic upgrade, migrate, schema changes, or service restarts.**
The application user `market` may have write permissions; the explicit
`BEGIN READ ONLY` protects these SELECT statements but is not a replacement
for a dedicated read-only role. Verify that this is the intended environment
and database first. Share only the table/column/version output, redacting
identifying details as necessary.
