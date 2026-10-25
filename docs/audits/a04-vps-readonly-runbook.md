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
