# Central AI — Paper Trading integration readiness (2026-10-25)

## Verified CI and development topology
- PR #32 commit f1cfef942f54de282177ade3fc0547a2fb6cc105: **2/2** GitHub Actions passed (PostgreSQL fence and fenced atomic test integration).
- Relevant PRs #17, #18, #20, #21, #23, #24, #26–#32 remain **open drafts** and are NOT a unified merge candidate.
- PR #17 and #20 are separate branches off main. PR #31/#32 are a separate branch stack. PR #21–#26 form a separate migration/test stack. PR #27–#30 form a design/fence stack, while PR #31/#32 do not inherit it.
- Therefore CI success on each branch does not prove combined compatibility.

## Architectural issues requiring resolution BEFORE integrating API
| Priority | Issue | Required evidence |
| --- | --- | --- |
| Blocker | Production API still persists FLOAT and does not call transactional service or PostgreSQL fence | One integrated HTTP test showing authentication, transactional write and fence refusal |
| Blocker | PR #20 expects canonical column names with NUMERIC, while draft migration creates shadow NUMERIC names | Approved, versioned cutover contract and matching ORM/service |
| Blocker | PR #21 revision intentionally raises; Alembic baseline for existing deployed DB unverified | Verified baseline, reversible migration and throwaway PostgreSQL rehearsal |
| Blocker | SQLite persistence in PR #30 is separate from PostgreSQL transaction | Do not use it as production write fence; use same PostgreSQL lock transaction |
| Blocker | Both legacy and new writers could mutate balances without common lock | Prove legacy writers disabled and in-flight writes drained before cutover |
| High | Float to NUMERIC precision, nonfinite values, nulls and overflows | Reconcile every row and monetary aggregate before/after; do not silently round |
| High | Concurrent first account creation and retry/idempotency behavior not fully addressed | Explicit account bootstrap, idempotency keys and crash/replay tests |
| High | PR #32 is intentionally a test-only simplified BUY flow, not full Paper Trading API | Real BUY/SELL HTTP integration and authorization tests |
| High | Rollback requires both schema and deployed app version compatibility | Backup/restore rehearsal, revert plan and monitoring |

## Integration sequence
1. Freeze and review the current production schema/read-write behavior, without making changes.
2. Select precise schema contract and create genuine Alembic baseline appropriate to deployed state.
3. Merge only independently approved non-overlapping changes, or rebase into ONE integration branch with a reviewed diff and CI on the combined head.
4. Add versioned, additive schema change with precision preflight, staged verified backfill and rollback.
5. Enforce a **single PostgreSQL fence** within all writers and account-row locking.
6. Wire an opt-in Paper Trading endpoint behind disabled-by-default feature flag only after compatibility and rollback checks.
7. Test actual authenticated endpoint with concurrent trades, restart/replay and fail-closed migration state.
8. Require explicit human approval to merge/deploy; remain paper-only.

## Important scope boundaries
No live VPS schema inspected. No deployed commits, backups or transaction logs verified. All status claims concern GitHub branches and CI only. Do not activate brokerage orders.
