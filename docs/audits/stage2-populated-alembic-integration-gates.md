# Stage 2: populated data → Alembic bridge design (no execution)

**Status: blocked for production.** PR #60 validated PostgreSQL transactional
rollback in disposable DB `test`. The populated-data prototype is currently a
standalone function, NOT an Alembic revision.

## Critical integration issue

The current disposable Alembic chain is:

`stage2_baseline_001` → `stage2_numeric_002`

`stage2_numeric_002` calls the empty-only rehearsal upgrade and explicitly
rejects non-empty paper tables. It cannot be reused for populated data.

**Do not** append the populated migration as revision 003: revision 002 must
succeed before 003 runs, and therefore pre-existing data remains blocked.

**Do not** call `migrate_populated_paper(engine)` from an Alembic revision using
a second engine/connection: that could open a second transaction, deadlock
against Alembic locks, or leave revision tracking inconsistent with the DDL.

## Required implementation

1. Move the DDL/conversion logic to
   `migrate_populated_paper_on_connection(connection)`, which MUST use the
   exact Alembic `op.get_bind()` connection and MUST NOT commit, begin a new
   transaction, dispose, or use another engine. Keep a separate, disposable-only
   harness which opens a transaction for direct tests.
2. Introduce an isolated alternate Alembic revision chain from a reviewed
   baseline for populated records, e.g.
   `stage2_populated_baseline_001` →
   `stage2_populated_numeric_002`, in a distinct script location. Do not put
   both 002 revisions under the same version directory (multiple heads).
3. Before DDL, verify actual schema, request-key/fence table absence, exact
   precision, check constraints, and quiesced legacy writers. Refuse any
   source data that would be rounded, truncated, or overflowed.
4. Assert the intended post-migration fence starts in `QUIESCED` generation
   1 and cannot be silently enabled by Alembic.
5. CI: create legacy schema + representative populated rows in fresh
   ephemeral PostgreSQL `test`, run `alembic upgrade head`, verify
   `alembic_version`, row counts, values, constraints, and fail-closed fence.
6. CI: inject DDL collision and precision-loss scenarios; assert rollback
   leaves no `alembic_version` stamp or schema changes.
7. Build a **separate** production-specific migration only after fresh
   schema audit, verified backup restore and explicit human approval.

Never merge, stamp, migrate or deploy to VPS/market as part of this PR.
