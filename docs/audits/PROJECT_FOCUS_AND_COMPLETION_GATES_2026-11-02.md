# Project focus and completion gates

**Living plan; created 2026-11-02, updated 2026-11-04.** Current statuses, decisions and evidence live in [the architecture/progress register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md). This file defines scope and ordering; historical audit snapshots do not override that register.

## Project objective

1. **Central AI:** one manager coordinating approved models and the existing Developer Agent, with durable tasks and a bounded develop/test/revise/review loop. Production promotion requires an explicit human decision.
2. **Market Engine:** authorized market/SEC/fundamental and macro/calendar inputs; benchmark relative strength; bullish/base/bearish scenarios; two daily reports; **internal paper simulator first, IBKR paper later**. No live orders.

Retain the existing VPS/Docker/PostgreSQL/queue architecture. Budget target EUR 50–150 monthly. Provider adapters in source do not prove connected accounts or successful external calls; detailed runtime/provider configuration is outside this public checkpoint.

## Current checkpoint — facts rather than completion percentages

- Source inspected: PR #129, `7fd9c850f73edea70988b017d8dda2a4b70f3fc3`, **293 commits / 187 changed files** ahead of main `d987387f45dbe25940502ea25542e7ad99673359`. PR #126–129 remain draft/unmerged.
- PR #128 source `c38f12b9f7b1d6d61ab469c90c9ce2af8068ac1b`: **33/33 CI runs successful**. Public build evidence is not permission to activate the developer loop.
- VPS/DB acceptance evidence is a separate protected operator record. This public source snapshot does not reproduce deployment, image, volume, database or backup metadata. Full #90 reconciliation remains open.
- Repository became public on 2026-11-04 after the documented limited secret review. The operator confirms the included Actions allowance was exhausted; this is not recorded as an account suspension.
- PR #129 baseline [run 41725530297](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41725530297), job `126385986276`: **7 passed** after publication. The other **32** old failed workflow runs remain unchanged. The next source-equivalent checkpoint `3555fa5cc3199230d12ae56461bce25b90f811a8` passed **33/33**; cleanup source `b67b288f56d310a8bfea8ad16667b641039a377f` also passed **33/33**. OPS-02 / CI-COV-01 source `cfdce9591ebf3e4668f42a28402119c25c4ecf02`: **33/33 CI successful**.
- The updated static inventory covers **89 source modules / 275 definitions / 72 import records**. It is not a complete runtime call graph or closure of Issue #90.
- **ME-API-01** is corrected in the cleanup candidate using explicit market/valuation aliases and real HTTP regression tests. **DUP-07** unreachable report parsing/output was removed while retaining unconditional rejection. No runtime module was added.
- AI-25–27 accept supplied recommendations/tests; `prepare_and_verify` returns a transient result. A persisted autonomous repair lifecycle and independently provisioned test/authorization source are still incomplete.
- Dedicated isolation for untrusted candidate execution, cleanup uncertainty handling, SEC safe automatic persistence, verified report scheduling remain pending. TestClient warning is fixed and CI-verified in OPS-02 using separate test dependencies and a narrow warning-as-error rule; runtime provider httpx and the pinned release lock remain unchanged.

## Freeze on unnecessary growth

Use existing TaskQueue, PersistentTaskBridge, DeveloperWorkerCoordinator, DeveloperTaskRunner, review pipeline and verifiers. Add no parallel AI manager, queue, retry engine, workflow controller, scheduler or verifier without a documented failing requirement and ownership decision. Similar names alone are not evidence that modules can be deleted.

No opportunistic OS upgrade, live trading, production migration, arbitrary generated-code execution on the production VPS, task activation or automatic merge/deploy. API-only approval did not authorize these operations.

## Priority and acceptance

| Package | Work and reuse boundary | Acceptance / current disposition |
|---|---|---|
| **P0 — Stabilize and reconcile** | Complete exact-source CI; review stack/main drift, ownership/callers, entrypoints and remaining #90 evidence | Public source/CI and protected operational evidence must be reconciled before P0 closure. No new feature module until unresolved safety/dependency gaps are assessed |
| **P1 — Finish Central AI developer loop** | Existing bridge/queue/coordinator + opt-in proposal/candidate/verifier path; trusted tests/authorization, atomic post-test results, max three attempts, recovery/cancel/cleanup | One allowlisted isolated scenario, success/failure/restart evidence, review artifact and no production writes. No new parallel engine |
| **P2 — Finish Market Engine MVP** | Repair existing analysis binding; audit current paper/data/migration/consumer paths; safe sources, relative strength, macro/catalysts, scenarios, two daily reports | Deterministic fixtures, provenance/assumptions/risks, internal simulator/DB consistency; SEC import obeys validate_source/permissions. Production schema changes require separate reviewed baseline/runbook and two restored-copy rehearsals |
| **P3 — Isolated VPS acceptance per release** | Disposable project/network/storage, exact image, no production mounts/secrets, cleanup verification | Central AI API-only acceptance already passed. Developer-loop and Market Engine acceptance remain pending |
| **P4 — Controlled rollout per release** | Explicit sign-off for one service at a time, health/negative security checks and rollback | Central AI API-only cutover completed in its approved scope. No general permission for worker activation, Market DB migration or IBKR integration |

P0/P1 precede new P2 features. DB inventory/restore work is prerequisite evidence, not permission to jump to a production migration. P3/P4 are repeated for each reviewed release, not globally marked complete by one source/CI result.

## Next active task and handoff rule

**Next: P0-RECON.** Exact-source checks finished for `cfdce9591ebf3e4668f42a28402119c25c4ecf02` (**33/33 CI successful**). The preceding cleanup source `b67b288…` passed 33/33. OPS-02 / CI-COV-01 install httpx2 only through test requirements, fail on the specific deprecated TestClient fallback and add 12 previously omitted test files to five existing workflow commands. Local aggregate: **300 passed, 43 skipped, 0 warnings**; PostgreSQL-only skips remain distinct from passed cases. Reconcile the remaining P0/#90 PR stack, ownership and protected VPS evidence before bounded P1 work. No merge or deployment is authorized by this source cleanup.

For every change record TASK_ID, objective, existing owner/functions, files, PR/base/head, exact test SHA and result, GitHub/CI versus VPS evidence, blockers and one next action in the canonical register. The Git commit/diff preserves exact edits; the register explains why. Refresh the generated inventory on source-review checkpoints. No new dated master register, duplicated runtime module or percentage-based readiness claim.
