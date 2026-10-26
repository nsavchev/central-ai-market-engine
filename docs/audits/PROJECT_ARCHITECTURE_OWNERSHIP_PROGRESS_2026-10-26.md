# Central AI / Market Engine — Architecture, Ownership and Progress Audit
**Snapshot:** 2026-10-26. **Source:** GitHub branch `central-ai/stage2-release-readiness-gate`, commit `6b6238c8c0a487c8f9207b3ba43c73724a9fdbc6`. This is a repository/source review; no access to the running VPS, database contents, secrets, or external provider accounts. **Do not claim production readiness.**

## Inventory
GitHub recursive tree returned 197 objects, not truncated (includes directories). Source groups:
- `app/` — Market Engine, SEC ingestion/normalization, valuation, scanners, IBKR, paper-trading APIs, numeric migration and read-only readiness probes.
- `central_ai/` — multi-provider HTTP facade, task queue/storage/bridge, workflow persistence, worker coordinator, heartbeat, planning-only release evidence gate.
- `developer_agent/v2/`, `v3/` — proposal/planning/review, test orchestration, verifier lineage.
- `alembic_stage2/` and `migrations/` — **disposable-only** migration history and rehearsal code, not approved production changes.
- `tests/`, `.github/workflows/` — isolated regression and disposable PostgreSQL CI.
- `docs/audits/` — prior risk audits and runbooks. Existing release-readiness report correctly says production **NO-GO**.

PR search yielded **80 open PRs** at this snapshot; many are stacked/dependent, not independent feature deliverables. PR #81 (release evidence gate) has **26/26 CI runs successful** on the recorded commit. This proves its CI set passed on that branch, not that `main` or VPS contains these features. No merge was performed.

## Existing implementation ownership (REUSE; do not rebuild)
| Capability | Current owner | Status / limitation |
|---|---|---|
| HTTP multi-model query/compare | `central_ai/app.py` | Initial API; no validated consensus, autonomous routing or complete agent manager |
| Task request + preliminary registry | `central_ai/task_bridge.py` with `developer_agent/v3/orchestrator.py` | Planning-only, in-memory part |
| Durable task submission and transaction | `central_ai/persistent_bridge.py` | Composes storage, workflow and queue in a SQLite transaction |
| Task records | `central_ai/task_storage.py` | Keep one owner |
| Task leases, retries and claim metadata | `central_ai/task_queue.py` | Keep one owner |
| Worker coordination | `central_ai/developer_worker_coordinator.py` | Uses existing bridge, targets, runner |
| Bounded developer analysis | `central_ai/developer_task_runner.py` | Existing worker path, do not add another execution loop |
| Workflow transitions | `central_ai/workflow_controller_v03.py` | Canonical stages currently reused by persistence |
| Durable workflow | `central_ai/persistent_workflow_v05.py` | Current version; v04 retained for compatibility/recovery |
| Release readiness evidence | `central_ai/stage2_release_gate.py` | Pure reporting, always approved=False and deployment_allowed=False |
| SEC read-only retrieval/validation | `app/sec_edgar.py` + `app/sources.py` | Preserve validate_source and permission checks |
| SEC normalization | `app/sec_financials.py` + `app/fundamentals.py` | Existing converter; no independently verified production persistence job |
| Paper simulation / fence / idempotency | `app/paper_atomic_service.py`, `app/paper_pg_fence.py`, `app/paper_idempotency.py` | Prototype/isolated tests, no real broker orders |
| Paper migration | `alembic_stage2/`, `app/paper_populated_migration.py` | Strictly disposable `test` database |
| Market data, financial quality, valuation | `app/engine.py`, `app/data_quality.py`, `app/valuation.py`, `app/advanced_valuation.py`, `app/scanner.py`, `app/macro.py` | Implemented modules; integration maturity and live correctness need separate audit |

## Duplicate/overlapping responsibilities — findings, not automatic delete list
**D-01 HIGH: Three workflow models.** `developer_agent/v3/workflow.py`, `developer_agent/v3/orchestrator.py` and `central_ai/workflow_controller_v03.py` each define stages/transitions or task-stage state. Do not introduce a fourth controller. Choose `central_ai/workflow_controller_v03.py` + `persistent_workflow_v05.py` as runtime contract. Keep old models as adapters if imported elsewhere; migrate callers with tests first.

**D-02 HIGH: Multiple verifier/runner generations.** `developer_agent/v3/trusted_verifier_v2/secure_runner.py`, `secure_runner_v21.py`, `secure_runner_v22.py`, `verifier.py`, plus `developer_agent/v3/test_controller.py` and `workflow_controller.py` overlap in command/report verification. Differences in pinned trust baselines are intentional security boundaries. First build an import/CLI/reference inventory and negative tests before consolidation; never delete/alias trusted verifier versions blindly. `workflow_controller.py` currently contains unreachable code after unconditional `raise ValueError("UNVERIFIED_REPORT_BLOCKED")` — confirmed dead-path finding.

**D-03 MEDIUM: Workflow persistence v04/v05.** Methods for registration, restore and status overlap. v04 is a compatibility path, v05 is active. Preserve database upgrade compatibility; prohibit new dependencies on v04 and document a migration path.

**D-04 MEDIUM: Multiple paper schema preflights.** `paper_schema_readiness.py` checks migrated NUMERIC, `paper_migration_baseline.py` checks legacy baseline, `paper_legacy_column_contract.py` checks column width/nullability, `paper_schema_constraints.py` checks relational constraints, plus `paper_data_preflight.py` checks values. These serve different phases: **compose their results** in a single read-only operator report; do not delete them as exact duplicates. Baseline alone is insufficient for live schema equivalence.

**D-05 MEDIUM: Two task representations.** `TaskBridge` holds in-memory registry while `PersistentTaskBridge` stores durable records. Durable storage should be authoritative; in-memory registry only as transient adapter. Test restart/recovery and prevent divergent approval flags.

**D-06 MEDIUM: Test/CI proliferation.** Many one-test GitHub Actions workflows and stacked PRs repeat Python install and PostgreSQL provisioning. After preserving existing security coverage, consolidate CI workflows by domain (core, Central AI, disposable migration, paper integration, safety), with comparable check protections.

**D-07 LOW: CLI wrappers.** `app/*_cli.py` wrappers near engine/fundamentals/valuation are not evidence of duplicate business algorithms; inspect implementation imports before merging.

## Functionality and gaps
- Paper V2: substantial isolated coverage including replay after fresh Python process, stale generation and conflict checks. Production cutover, real `market` schema equality, writer quiescence, backup restore and supervised activation are **not done**.
- SEC EDGAR: read-only client + converter exist. Required safe scheduled ingestion into PostgreSQL with provenance/as-of, error handling and permissions remains to be verified/finished. No bypass of `validate_source`.
- Central AI: authenticated multi-provider comparison exists. TaskQueue/PersistentTaskBridge/DeveloperWorkerCoordinator exist. **Not yet proven:** one connected end-to-end multi-agent manager that diagnoses, plans, isolates a candidate repair, runs allowlisted checks, records evidence, retries within bounded budget and escalates, while preventing autonomous deploy.
- Quant/market: analysis, valuations, scanners, macro and historical data modules exist. User goals still include global-market relative strength, macro surprises, optimistic/base/pessimistic valuations, paper-first IBKR integration, periodic reports and extensible approved sources. Do not mark real-time feeds, schedules or live integrations complete without data/CI evidence.
- Security: release assessment gate does not authorize deployment. No real brokerage orders. Starlette/httpx TestClient deprecation warning remains a separate low-risk cleanup **after** release-blocking tasks.

## Canonical no-duplication architecture
`central_ai/app.py` (authenticated request edge)
 -> `persistent_bridge.py` (atomic task submission and projection)
 -> `task_storage.py` + `task_queue.py` + `persistent_workflow_v05.py`
 -> `developer_worker_coordinator.py`
 -> `developer_task_runner.py` (only allowlisted execution)
 -> `developer_agent/v3/` (plan/propose/review within constraints)
 -> trusted verifier + evidence record -> outcome [solved/tested OR escalated].
Use `stage2_release_gate.py` only to summarize missing approval evidence. It MUST NEVER merge, deploy, authorize broker orders or mutate production DB.

## Prioritized task register
| ID | Priority | Task | State / next acceptance criterion |
|---|---|---|
| AUD-01 | P0 | Freeze changes and map overlapping API/function imports | OPEN; machine-readable caller/import map, owner per behavior, no deletions before tests |
| AUD-02 | P0 | Triage stacked PRs and reconcile with `main` | OPEN; sequential dependency map, exact merge diff and regression plan; none merged here |
| DB-01 | P0 | Real `market` inventory | BLOCKED on read-only VPS evidence; compare full DDL, indexes, identity, constraints, data |
| DB-02 | P0 | Backup and restore drill | BLOCKED on verified operator backup, separate restore and reconciliation |
| DB-03 | P0 | Reviewed production Alembic/runbook and all-writer cutover | OPEN; fail-closed on deviations, rehearse with sanitized restore, explicit human approval |
| AI-01 | P0 | One orchestration ownership contract | OPEN; reuse persistent bridge/queue/runner, no new parallel engines |
| AI-02 | P1 | End-to-end failure-to-repair-to-escalation evidence | OPEN; bounded retries, restart, negative security and persistence tests |
| DATA-01 | P1 | SEC Company Facts safe importer | PARTIAL: read client/normalizer; complete permission-aware PostgreSQL import |
| DATA-02 | P1 | Market sources and relative strength scanner | PARTIAL: verify reports, macro and data-source correctness |
| MODEL-01 | P1 | 3-scenario valuation and backtest quality | PARTIAL: verify existing advanced valuation versus requested uncertainty model |
| OPS-01 | P1 | Central AI worker/Market Engine deployment integration | BLOCKED until DB/CI review; paper-only, no broker executions |
| OPS-02 | P2 | TestClient Starlette deprecation | DEFER until P0 risks resolved |

## Progress bookkeeping rules — MUST USE
1. Before developing any new function: search tree, existing definitions, call sites, tests, PRs and this register; assign **one canonical owner**.
2. For each change: record TASK_ID, objective, existing reusable functions, files changed, PR/base/head, CI commit/checks, current state, blockers and next action.
3. Do not equate green CI in a stacked draft PR with merged `main` or running VPS.
4. Resolve a task only after executable evidence and regressions, else mark `blocked`, `partial`, or `escalated`. Do not say finished for planning-only code.
5. At each conversation handoff: reread this document, update task register in a follow-up audit PR, and inspect GitHub current branches.
6. Security flags `approved`/`deployment_allowed` remain False in automated planning. Deployment and production database writes need explicit human authorization.

## Immediate next work (no duplicated module)
First produce a function/caller dependency matrix for `central_ai/` + `developer_agent/` and reconcile A11.15.x PR line with the Stage 2 PR line. Then test/refactor one canonical runtime orchestration path. Independently collect read-only production schema evidence before writing a deployable Alembic migration.

**Decision:** Source audit is useful but **not a full runtime/security audit**: no SSH/VPS telemetry, database queries, provider API calls or locally executed complete test suite were performed here. Existing CI for PR #81 was 26/26 successful on its branch.
