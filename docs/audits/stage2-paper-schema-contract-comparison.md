# Stage 2 paper schema comparison (GitHub review)

Compared:
- migrations/versions/stage2_paper_test_001.py (disposable Alembic)
- app/paper_populated_migration.py (disposable populated-data prototype)
- app/paper_pg_fence.py and app/paper_idempotency.py (writer contracts)

## Columns and constraints
Both definitions use numeric(20,2) for cash, numeric(24,6) for
quantity and numeric(20,2) for price and fee. Both use a composite
primary key on paper_request_keys(account_id,request_key), varchar(128)
request_key, varchar(64) fingerprint and nullable JSONB result.
The populated migration now includes the Alembic minimum key length
constraint (length(request_key)>=8).

## IMPORTANT: different fence bootstraps
Empty-data Alembic rehearsal creates paper_write_fence mode=LEGACY,
generation=0. Populated prototype creates mode=QUIESCED,
generation=1. This difference is intentional **fail-closed** for a
populated cutover, but it means the two migration paths are NOT
operationally equivalent. The writer's check_fence only permits LEGACY
with an expected generation. Do not unify by silently activating
LEGACY: the switch requires explicit approval and all writer paths
must first be audited.

## Remaining gaps
- The populated prototype is not an Alembic production revision.
- Real schema contains additional constraints, indexes, sequences and
  foreign keys that synthetic tests do not reproduce.
- Verify complete table definition and constraint-name equivalence
  before merging or deploying; a green CI alone does not establish it.
- Continue to prohibit production migration and VPS deployment.
