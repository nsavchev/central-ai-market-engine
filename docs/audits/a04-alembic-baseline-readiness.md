# A04 deployed baseline readiness audit

**Read-only inventory only.** No production database inspected. A successful
local test does not authorize migrations.

The source branch contains a draft migration
`20261025_paper_numeric_shadow` with `down_revision=None`, and it
deliberately raises `DRAFT_MIGRATION_NOT_APPROVED`. This is not an
established baseline for the deployed database.

`app.paper_alembic_inventory.inspect_schema(engine)` is an opt-in
metadata-only check requiring a caller-supplied PostgreSQL engine. It issues
`SET TRANSACTION READ ONLY` and returns presence/version information and
column data types, not values from balances, holdings, or customer records.

Before designing a production revision chain, a human operator must confirm
with a read-only database role: database identity, current migration version(s),
whether `alembic_version` exists, all active services writing paper tables,
constraints, schema, current app commit, backup recovery test and permissions.

This report does not infer the runtime database state from a GitHub branch.
An unknown or missing Alembic baseline must block automatic deployment.
