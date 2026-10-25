# Stage 2 migration review

This Alembic revision is a disposable **rehearsal**, not an approved production migration.
It operates only when STAGE2_DISPOSABLE_DB=YES AND current_database()='test',
with empty paper tables. It must not be wired into the production Alembic
revision graph. Production `market` has no alembic_version baseline and
the current API still uses Float.

The existing migration rehearsal has verified an empty PostgreSQL database
restored from the VPS archive. Before any actual cutover require:
- verified isolated backup and restore;
- a reviewed baseline and version chain;
- write quiescence for every old API writer and no in-flight transactions;
- precise schema and invariants checked after migration;
- app compatibility, disabled-by-default v2, manual bootstrap;
- independent restoration procedure and human authorization.

Downgrade in this rehearsal is destructive for request-key history, so it is
only permitted with empty paper tables and is NOT a production rollback plan.
Production rollback should restore a verified backup and compatible app version.
