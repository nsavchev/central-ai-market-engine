# Project focus and completion gates — 2026-11-02

## Non-negotiable project objective

Build **two collaborating systems**, not an endless sequence of AI-XX gates:

1. **Central AI manager** coordinating approved models and a Developer Agent, persisting tasks, producing reviewed code changes with a bounded develop/test/revise loop. Production promotion always needs an explicit human decision.
2. **Market Engine** ingesting authorized market/SEC/fundamental and macro/calendar data, benchmarking US equity relative strength, providing bullish/base/bearish scenarios and two reports per period, and operating **paper-only** via the internal simulator first, IBKR paper connector later. No live trades.

VPS Ubuntu, Docker, PostgreSQL, and the existing agent/queue must be retained. Budget target EUR 50–150 monthly. Security/provenance and evidence take precedence over autonomy.

## Verified evidence and limits

- Operator ran read-only **AI24_VPS_ACCEPTANCE_PASSED** against the **older deployed** Central AI; production Task API explicitly NO, volume mounted, health and backup checks passed. This does **not** validate the new GitHub release stack on VPS.
- Latest AI-27 integration commit df4a20f0fede80617696e34b88e50a549217ac5a: **32/32 CI success**. AI-27 injects a fake verifier. Real Docker syntax, functional and timeout smoke were tested independently in CI.
- GitHub comparison with main: **249 commits ahead, 158 changed files**; stacked draft PRs are **not merged**. Green CI does not imply deployment.
- AI-25..27 require an externally supplied code recommendation and separately supplied tests. They do **not** automatically synthesize a candidate, generate trusted tests, persist an execution/review result or repair a failing candidate.
- Current `central_ai/app.py` provides model access and opt-in task endpoints, but not a verified end-to-end development run. `central_ai/verified_review_pipeline.py` invokes verification and returns a transient dictionary; it does not persist post-test state.
- Existing `TaskQueue` and persisted workflow already limit attempts; avoid creating a second retry engine or queue.
- Docker with host daemon access is **not** a high-assurance boundary for hostile generated code. Dedicated isolated runner and artifact integrity must be designed before automatic execution.
- SEC EDGAR Company Facts import is **not complete**: must pass source validation/permissions, audit and Financials schema contracts before enabling.

## Freeze: disallowed scope growth

Do not add new AI-XX wrappers, extra queues, alternate workflow controllers or second container verifiers unless a documented failing requirement proves necessity. Do not make opportunistic Ubuntu upgrades, broker live execution, deploy to production, enable task API or run arbitrary model code on the production VPS.

## Work packages, in strict priority

**P0 — Stabilize release**: review 249-commit diff and dependency/entrypoint map; consolidate reviewed patches into one immutable test candidate with reproducible full CI; account for every stacked draft PR; rollback provenance; review secrets and CI permissions. Acceptance: exact SHA and manifest, no unresolved safety/merge conflicts.

**P1 — Finish Central AI developer loop**: use existing persistent TaskBridge -> queue -> DeveloperWorkerCoordinator; integrate existing proposal/candidate/verifier modules into an explicitly opted-in executor for an **allowlisted task**; persist test results and state transitions atomically. Only a vetted generator may supply candidate patches; independent trusted test source; limit three attempts, cancellation/cleanup and review artifact. Acceptance: single isolated scenario, successful and failing branches, restart/recovery, no writes to production, approval required.

**P2 — Finish Market Engine MVP**: inspect current paper-trading APIs and PostgreSQL migrations; isolate restore/migration tests; implement authorized data sourcing and validation; quantitative benchmark relative-strength signals; macro/calendar and catalysts; valuation scenarios with assumptions; two daily reports and no trades other than internal paper simulator. Acceptance: deterministic historical fixtures, report evidence/risks, simulator and DB consistency, no real orders.

**P3 — Isolated VPS acceptance**: separate project, disposable networks and test volumes, no production mounts or secrets; immutable image build/digest and rollback validation. Production API/database identities unchanged. Task API NO and live trading off throughout.

**P4 — Controlled rollout**: explicit human sign-off, one service change at a time, health/negative security smoke, restore test and rollback. IBKR paper connector only after internal simulator is validated.

## Decision rule

For each task record: exact code ref, original objective, owner, acceptance tests, status (not started / blocked / CI passed / VPS passed / deployed), dependencies and next blocker. No labels such as COMPLETE unless the acceptance evidence exists. Prefer one consolidated release PR over another numbered PR. Progress is measured by P0–P4 acceptance, not PR count.
