# Project focus and completion gates

**Living plan; created 2026-11-02, updated 2026-11-04.** Current statuses, decisions and evidence live in [the architecture/progress register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md). This file defines scope and ordering; historical audit snapshots do not override that register.

## Project objective

1. **Central AI:** one manager coordinating approved models and the existing Developer Agent, with durable tasks and a bounded develop/test/revise/review loop. Production promotion requires an explicit human decision.
2. **Market Engine:** authorized market/SEC/fundamental and macro/calendar inputs; benchmark relative strength; bullish/base/bearish scenarios; two daily reports; **internal paper simulator first, IBKR paper later**. No live orders.

Retain the existing VPS/Docker/PostgreSQL/queue architecture. Budget target EUR 50–150 monthly. Provider adapters in source do not prove connected accounts or successful external calls; detailed runtime/provider configuration is outside this public checkpoint.

## Current checkpoint — facts rather than completion percentages

- Source inspected: PR #130, `a2aee7b81dc44e9ad0e566d215c38daa74dffee1`, **298 commits / 194 changed files** ahead of main `d987387f45dbe25940502ea25542e7ad99673359`. All 128 open PRs are draft/unmerged: 87 heads in candidate ancestry, 41 outside; all bases are ancestors of their own heads. No mass merge or branch closure.
- PR #128 source `c38f12b9f7b1d6d61ab469c90c9ce2af8068ac1b`: **33/33 CI runs successful**. Public build evidence is not permission to activate the developer loop.
- VPS/DB acceptance evidence is a separate protected operator record. This public source snapshot does not reproduce deployment, image, volume, database or backup metadata. Full #90 reconciliation remains open.
- Repository became public on 2026-11-04 after the documented limited secret review. The operator confirms the included Actions allowance was exhausted; this is not recorded as an account suspension.
- PR #129 baseline [run 41725530297](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41725530297), job `126385986276`: **7 passed** after publication. The other **32** old failed workflow runs remain unchanged. The next source-equivalent checkpoint `3555fa5cc3199230d12ae56461bce25b90f811a8` passed **33/33**; cleanup source `b67b288f56d310a8bfea8ad16667b641039a377f` also passed **33/33**. OPS-02 / CI-COV-01 source `cfdce9591ebf3e4668f42a28402119c25c4ecf02`: **33/33 CI successful**.
- The updated static inventory covers **89 source modules / 276 definitions / 72 import records**. It is not a complete runtime call graph or closure of Issue #90.
- **ME-API-01** is corrected in the cleanup candidate using explicit market/valuation aliases and real HTTP regression tests. **DUP-07** unreachable report parsing/output was removed while retaining unconditional rejection. No runtime module was added.
- P0-RECON found missing safeguards from #15/#16: raw IBKR exception text and unsafe legacy float inputs. Narrow corrections now live in existing owners, with **49 targeted / 325 aggregate local passed**, 43 PostgreSQL skips and **33/33 CI** on `a2aee7b…`. #14 financial quality/units compatibility remains open. Old conflicting #20/#105 alternatives stay on hold.
- P0-LEASE-01: disposable source probe reproduced direct `TaskQueue.acquire` reacquisition after three exhausted scheduled leases; `acquire_next` correctly refuses. Review/repair this existing boundary before new P1 functionality; do not create another retry engine.
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

**Next: P0-LEASE-01.** Reconcile and fix the existing direct-acquire retry boundary with compatibility, expired-lease, restart and concurrency tests. P0-RECON completed the source/PR classification and ported two missing safeguards on source `a2aee7b81dc44e9ad0e566d215c38daa74dffee1` (33/33 CI). P0/#90 remain open for the protected VPS/runtime/schema/ACL/reviewer/restore evidence mapped in the canonical register. FIN-QUALITY-01 remains an explicit metadata/consumer gap. No new P1/P2 feature module or production operation follows from source/CI success.

For every change record TASK_ID, objective, existing owner/functions, files, PR/base/head, exact test SHA and result, GitHub/CI versus VPS evidence, blockers and one next action in the canonical register. The Git commit/diff preserves exact edits; the register explains why. Refresh the generated inventory on source-review checkpoints. No new dated master register, duplicated runtime module or percentage-based readiness claim.
