# P0 release inventory and scope disposition — 2026-11-02

Reference: branch `audit/focus-freeze-central-ai-market-engine-20261102`; compare against `main`.

## Inventory (GitHub compare)

- 250 commits ahead, 159 changed files.
- By leading path: .github 32; tests 58; docs 22; central_ai 17; app 14; developer_agent 3; deploy 3; alembic_stage2 3; tools 2; scripts 1; migrations 1; two Compose files and one alembic config.
- These are **change counts in the comparison**, not the full repository file inventory.
- Last observed CI of project-focus PR #127: 30 success and 2 running; do not call it completely green without a final run check.

## Release units — keep separate

| Area | Important files | P0 disposition |
|---|---|---|
| Central AI HTTP API | `central_ai/app.py`, `central_ai/Dockerfile`, `docker-compose.central.yml` | Already deployed older candidate; do not silently change live service |
| Persistent task ownership | `persistent_workflow_v05.py`, `worker_once.py`, `worker_batch.py`, `worker_scheduler.py`, `worker_supervised.py` | Keep one queue and a single scheduling chain; audit startup and state boundaries |
| Reviewed code pipeline | `review_handoff.py`, `proposal_adapter.py`, `verifier_gate.py`, `review_pipeline.py`, `isolated_candidate.py`, `verified_review_pipeline.py` | Development-only; integration results not persisted atomically; manual recommendations/tests |
| Candidate verification | `isolated_verifier.py`, `isolated_functional_verifier.py` | Do not enable untrusted execution on production Docker host |
| Market Engine paper | `app/paper_atomic_service.py`, `app/paper_idempotency.py`, `app/paper_pg_fence.py`, `app/paper_account_bootstrap.py`, `app/main.py` | Independent paper-only acceptance; do not run migrations on production |
| Migration safety | `app/paper_populated_migration.py`, `app/paper_schema_constraints.py`, `migrations/versions/stage2_paper_test_001.py` | Needs isolated restored DB and rollback evidence |
| CI and release | 32 changed .github files, 58 test files, `scripts/ai24_vps_readonly_preflight.sh` | Consolidate gates and immutable SHA evidence; avoid redundant workflows |

## Mandatory release split

1. **Central AI API-only**: existing production release configuration with Task API NO and external SQLite volume; no code-runner activation.
2. **Central AI developer loop**: sandbox-only acceptance with explicit approved fixtures and bounded retry; not production-ready.
3. **Market Engine paper trading**: independent release after DB migration and ledger consistency gates; keep paper mode.
4. **SEC EDGAR fundamentals, relative-strength monitoring and scenario reporting**: measure against concrete evidence and missing functionality, not inferred from paper API test coverage.

## Explicit stop conditions

- CI success on a draft PR is not a merge or deployment.
- P0 cannot close without reviewing *all* release files, security-sensitive GitHub workflows, and exact target SHA.
- No all-in-one deployment involving PostgreSQL and Central AI together.
- No new workflow controller, task queue, scheduler or Docker verifier merely to increment AI task numbers.
- No autonomous patch merge, production deployment or real trading.
