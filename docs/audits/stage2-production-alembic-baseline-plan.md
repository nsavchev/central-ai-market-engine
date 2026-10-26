# Production Alembic baseline — plan only

Observed existing VPS `market`: five empty tables, Float paper columns and
no `alembic_version` table at the prior inspection. This must be
revalidated immediately before approval.

**No production baseline revision, `alembic stamp`, schema write, or
migration is authorized or performed by this PR.** It adds a read-only
legacy schema preflight only.

A truthful migration history must be reviewed separately:
1. Freeze all writers and check active transactions across API replicas.
2. Verify fresh pg_dump with test restore and compute source-schema hash.
3. Compare actual column types, defaults, constraints, indexes, FKs,
   identity/serial sequences, ownership and all five tables against an
   independently curated baseline. The minimal preflight in this PR is
   insufficient to prove full equivalence.
4. Create a proper Alembic env.py and baseline revision representing the
   unmodified legacy schema; stamp only under explicit operator approval.
5. Link a new reviewed migration with down_revision to that baseline;
   do NOT reuse the disposable `stage2_paper_test_001` revision
   (down_revision=None) as a production revision.
6. Restore and rehearse twice in *separate* isolated DBs with realistic
   existing data, balances and request-key collisions.
7. Test all consumers with Decimal response strings, migrations,
   rollback and explicit cutover stop conditions.

Do not change VPS `market`, `market_restore_test`, docker-compose,
or merge PRs without explicit approval.
