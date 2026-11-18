# Project focus and completion gates

**Living plan; created 2026-11-02, source-task pointer updated 2026-11-18.** Current statuses, decisions and evidence live in [the architecture/progress register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md). This file defines scope and ordering; historical audit snapshots do not override that register.

## Project objective

1. **Central AI:** one manager coordinating approved models and the existing Developer Agent, with durable tasks and a bounded develop/test/revise/review loop. Production promotion requires an explicit human decision.
2. **Market Engine:** authorized market/SEC/fundamental and macro/calendar inputs; benchmark relative strength; bullish/base/bearish scenarios; two daily reports; **internal paper simulator first, IBKR paper later**. No live orders.

Retain the existing VPS/Docker/PostgreSQL/queue architecture. Budget target EUR 50–150 monthly. Provider adapters in source do not prove connected accounts or successful external calls; detailed runtime/provider configuration is outside this public checkpoint.

## Current checkpoint — 2026-11-18

**Accepted P1-INSTALLED-IDLE-01, operator-reported VPS evidence:** the installed same-owner supervisor completed a real one-shot credential-free idle run (3.377 s; one cycle; zero processed tasks; idle review state). The service returned inactive with guard `NO`, installed authority false and timer disabled; temporary overrides removed, state/key/accounting preserved, and no provider request. Do not repeat the one-time acceptance. Detailed host evidence stays private. The accepted runtime is still `a1ffdd715e7f6fec343886eb812a89bf45485078`. Documentation follow-up `208ea48c01ff74b8f1964413df6c2b90f3714fcf` independently passed 33/33 CI on that exact commit; PR #130 remains draft/unmerged.

**Today's delivery decision:** provide a safe, demonstrable integrated MVP and explicit GO/NO-GO per capability, not a blanket production approval. Complete the existing combined two-report synthetic CLI acceptance on isolated inputs and retain the result; do not falsely label offline/demo reports as live market analysis. [Issue #90](https://github.com/nsavchev/central-ai-market-engine/issues/90), verified acquisition rights/freshness, complete API/PostgreSQL restore/ACL reconciliation, live two-daily report scheduling, and productive worker/credential bounds are still open. Keep paper only, no live orders, no unreviewed automation.

## Prior checkpoint — 2026-11-17 (historical; the installed idle test is now accepted)

**P1-INSTALLED-IDLE-01 is the active task.** PR [#130](https://github.com/nsavchev/central-ai-market-engine/pull/130) remains open, draft and unmerged. Accepted source `a1ffdd715e7f6fec343886eb812a89bf45485078`, base `7fd9c850f73edea70988b017d8dda2a4b70f3fc3`, has **33/33 successful CI workflows**, freshly confirmed on that exact SHA, including [AI-19 run 44078874638](https://github.com/nsavchev/central-ai-market-engine/actions/runs/44078874638) and [DUP-01 run 44078874641](https://github.com/nsavchev/central-ai-market-engine/actions/runs/44078874641). These checks accept the source/template checkpoint; they are not evidence that the new documentation contract has executed on a host.

The operator separately confirms that the replacement of the **same `central-ai-staging.service`** is installed and accepted in its disabled state. The service is inactive, its guard is `NO`, installed execution authority is false, and the timer is disabled/inactive. Retained state, reviewer authority and accounting are preserved; the worker has not been activated and no new provider request was sent. This is a sanitized operator-reported disposition. Its receipts, installed identities and detailed host checks remain private.

The next contract is [one installed credential-free idle invocation](worker-review-rollout-runbook.md#single-installed-credential-free-idle-invocation--p1-installed-idle-01). It retains the installed unit/config/location bytes, existing nonroot owner, source/runtime, database, key, scheduler lock, current status, agent and one-cycle/one-task bounds. A private temporary config changes only `execution_authorized` to true; a temporary runtime override sets the service guard to `YES`, selects that config, removes `OPENAI_API_KEY` from the process environment and consumes a one-start ticket through a plain nonroot `ExecCondition`. A root-owned once marker prevents controller reruns. No task, grant, credential source, policy migration, budget or recurring schedule is added. Preparation is not execution; deliberate operator execution of the complete private block is the disclosed single activation decision.

## Historical checkpoints — 2026-11-04 source snapshot

The following dated results retain their original scope; later entries in the canonical register supersede their pending/next-task statements.

- Source inspected: PR #130, `a2aee7b81dc44e9ad0e566d215c38daa74dffee1`, **298 commits / 194 changed files** ahead of main `d987387f45dbe25940502ea25542e7ad99673359`. All 128 open PRs are draft/unmerged: 87 heads in candidate ancestry, 41 outside; all bases are ancestors of their own heads. No mass merge or branch closure.
- PR #128 source `c38f12b9f7b1d6d61ab469c90c9ce2af8068ac1b`: **33/33 CI runs successful**. Public build evidence is not permission to activate the developer loop.
- VPS/DB acceptance evidence is a separate protected operator record. This public source snapshot does not reproduce deployment, image, volume, database or backup metadata. Full #90 reconciliation remains open.
- Repository became public on 2026-11-04 after the documented limited secret review. The operator confirms the included Actions allowance was exhausted; this is not recorded as an account suspension.
- PR #129 baseline [run 41725530297](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41725530297), job `126385986276`: **7 passed** after publication. The other **32** old failed workflow runs remain unchanged. The next source-equivalent checkpoint `3555fa5cc3199230d12ae56461bce25b90f811a8` passed **33/33**; cleanup source `b67b288f56d310a8bfea8ad16667b641039a377f` also passed **33/33**. OPS-02 / CI-COV-01 source `cfdce9591ebf3e4668f42a28402119c25c4ecf02`: **33/33 CI successful**.
- The updated static inventory covers **89 source modules / 276 definitions / 72 import records**. It is not a complete runtime call graph or closure of Issue #90.
- **ME-API-01** is corrected in the cleanup candidate using explicit market/valuation aliases and real HTTP regression tests. **DUP-07** unreachable report parsing/output was removed while retaining unconditional rejection. No runtime module was added.
- P0-RECON found missing safeguards from #15/#16: raw IBKR exception text and unsafe legacy float inputs. Narrow corrections now live in existing owners, with **49 targeted / 325 aggregate local passed**, 43 PostgreSQL skips and **33/33 CI** on `a2aee7b…`. #14 financial quality/units gap is corrected by FIN-QUALITY-01 below; scaled units are deliberately not accepted without normalization. Old conflicting #20/#105 alternatives stay on hold.
- P0-LEASE-01 corrected at `cf13d4c18038875e0b4fc07f0bbeb0348edcd504`: direct/scheduled acquisitions share one durable three-attempt budget. Final active lease heartbeat/completion and legacy queue compatibility are preserved; 30 targeted / 342 local passed, 43 PG skipped; **33/33 CI successful**. No new retry engine or schema.
- FIN-QUALITY-01 source `af585fd9a33585782ac2854cc59552ea00e16f67` requires explicit ones, runs existing permission/quality checks before history writes/metrics and preserves legacy rows without backfill; local 373 passed / 44 PG skipped, **33/33 CI successful**. Only existing owners and JSON metadata change.
- P0-REVIEW-01 / P0-AUDIT-01 source `4d5c3417872fdf27aa0d7a4b62bc62a46e8495c8` now validate result consistency and persist verification intent/binding/outcome/quarantine in existing TaskStorage. 100 targeted / 408 aggregate local passed, 44 PG skipped; **33/33 CI successful**. No new module/schema/queue.
- AI-25–27 still accept supplied recommendations/tests. One-shot durable verification is not autonomous generation/revision, real reviewer provisioning, independent harness completion proof or hardened runner acceptance.
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

**Active delivery task: P0-OPS-RECON-01 / Market combined-demo acceptance.** Do not rerun the accepted installed idle cycle. Reuse the existing combined-market report CLI and synthetic, isolated fixtures, pin the exact current source and capture two independently bounded offline report outputs with unavailable inputs marked explicitly. Assemble the private release receipt and distinguish what the VPS confirmed from source-only CI, the synthetic demonstration and missing operational permissions. Keep the service/timer disabled. Productive CAI task dispatch and any recurring market schedule require new controlled gates.

**P1-SCHEDULED-SERVICE-BOUND-01 remains OPEN.** Accepted private disabled-install, actual SIGTERM/systemd and one-shot idle evidence are now recorded; productive workload assessment is still pending. The single-job JSON command-timeout sum is **205 seconds before overhead**; the 300/60-second limits remain interruption budgets, not proof that all work completes within them. An idle success proves no new generated work or external-provider path. Productive work requires a separate concrete bounded task, grant and credential scope; recurring operation is a separate decision. **P0-OPS-RECON-01 / Issue #90 remains OPEN** for deployment provenance, database/permissions, restore and remaining stack reconciliation. An interrupted controller may leave the runtime override present until reconciled; do not claim disabled restoration without its final receipt. Reconciliation preserves the actual database, reviewer key, accounting and unresolved journals rather than restoring an earlier ledger. Preserve paper-only operation and false promotion flags.

For every change record TASK_ID, objective, existing owner/functions, files, PR/base/head, exact test SHA and result, GitHub/CI versus VPS evidence, blockers and one next action in the canonical register. The Git commit/diff preserves exact edits; the register explains why. Refresh the generated inventory on source-review checkpoints. No new dated master register, duplicated runtime module or percentage-based readiness claim.

## Day plan — 2026-11-04 (Europe/Sofia)

PLAN-DAY-01 is a target schedule, not evidence of completed work. Starting source: FIN-QUALITY-01 `af585fd9a33585782ac2854cc59552ea00e16f67` (373 local passed / 44 PostgreSQL-dependent skipped; 33/33 CI), documentation checkpoint `e4ed9610667ba28ce2e546697e6c85872fd5a3bf`. The canonical register owns actual progress. These starting task names are historical; the Next active task section and latest canonical entry define the current task.

| Local time | Work package | Acceptance for the block |
|---|---|---|
| 10:00–11:00 | P0-REVIEW-01: existing authorization, verifier, storage and cleanup boundaries | Evidence-backed caller/state map, concrete gaps, minimal corrections in existing owners; no invented reviewer authority |
| 11:00–12:00 | Durable verification result and restart behavior | Atomic stored outcome bound to exact task/candidate/tests/image/authorization; restart tests and approval/deployment flags remain false |
| 12:00–13:00 | Cleanup uncertainty and quarantine | Unconfirmed cleanup blocks retry/continuation; inspect cancellation/failure paths and preserve one queue |
| 13:00–14:00 | One bounded isolated Central AI scenario, if source gates permit | Existing task → proposal → authorized fixture verification → durable result; source unchanged except reviewed candidate; no production secrets/mounts |
| 14:00–15:00 | Negative integration and recovery | Denied/stale/mismatched authorization, failure, replay, restart/cancel and retry exhaustion have measured outcomes; synthetic identity is labelled synthetic |
| 15:00–16:00 | Exact-candidate CI and focused integration review | Relevant new regressions and required checks on exact SHA; no unrelated module growth or repeat of unchanged full PR inventory |
| 16:00–17:00 | Existing Market Engine paper/data/API acceptance or catch-up | Existing relative strength/scenarios/history/paper regressions; no new data-source integration. This entire block becomes Central AI catch-up if required |
| 17:00–18:00 | Reserve, evidence reconciliation and release handoff | Fix critical regressions, preserve one exact candidate/rollback description, update actual done/blocked/next states and produce one go/no-go summary |

Catch-up rule: compare actual accepted outcomes against this schedule at each work checkpoint. Start the next dependency as soon as the previous one passes. If a core block slips by 45–60 minutes, consume the 16:00–17:00 optional acceptance block and then the final reserve; defer optional Market Engine work. Do not skip authorization, fail-closed behavior, required tests or #90 evidence to recover time. On a hard blocker, record the evidence and continue independent authorized work; do not repeat the same stalled action.

The day target is a reviewed, tested Central AI candidate with one bounded isolated lifecycle and explicit remaining gates. The complete Central AI + Market Engine project is finished only after all declared acceptance criteria, authorized integrations, operational evidence, restore/rehearsal and separately approved rollout pass. A clock deadline or green source CI cannot mark those complete. An operator evidence/acceptance session is a separate follow-up when the operator is available; production merge, deployment, worker activation, database migration and real trades remain unauthorized by this plan.
