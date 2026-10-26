# Linked Alembic history — disposable proof, NOT production rollout

Two linked revisions in a separately configured Alembic environment:
stage2_baseline_001 -> stage2_numeric_002. The baseline does not create
tables; it checks an existing legacy schema. The second revision reuses
the guarded disposable migration, which refuses a database other than
`test` and refuses populated paper tables.

This is **NOT** a deployable migration for market, regardless of CI.
No production stamp / downgrade / migration is permitted. The original
`migrations/versions/stage2_paper_test_001.py` remains isolated.

Before any production migration, independently validate full-schema
equivalence and write quiescence, build a production-specific reviewed
revision with handling for existing data, and prove a backup restore.
