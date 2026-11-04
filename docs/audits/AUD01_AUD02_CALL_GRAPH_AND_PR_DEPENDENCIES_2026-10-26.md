# AUD-01 / AUD-02 — canonical dependencies

**Updated 2026-11-04**, source `7fd9c850f73edea70988b017d8dda2a4b70f3fc3` (PR #129). This is a static source map. Current task states and evidence live only in [the architecture/progress register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md).

## Existing source paths

| Entry / function | Calls or owns | Boundary |
|---|---|---|
| `central_ai.app.ask` | `call_provider` | Authenticated provider requests; no task execution |
| `central_ai.app.submit_task` | `_task_bridge` → `PersistentTaskBridge.submit` | Task API is opt-in in source; no runtime state is asserted here |
| `PersistentTaskBridge.submit` | `TaskBridge.submit`, storage save, workflow registration and queue enqueue | Atomic durable submission; v3 orchestrator supplies initial planning representation |
| `DeveloperWorkerCoordinator.run_once` | Queue acquire, TaskFileTargets lookup, `DeveloperTaskRunner.run_acquired_and_complete` | One coordinator and one queue |
| `DeveloperTaskRunner.run_acquired_and_complete` | HeartbeatWorker, ReadOnlyAnalyzer, `PersistentTaskBridge.complete_analysis` | AST analysis and durable completion, not generated-code repair |
| `prepare_review_pipeline` | review_handoff → proposal_adapter → verifier_gate → isolated_candidate | Supplied recommendation; opt-in candidate preparation |
| `prepare_and_verify` | prepare_review_pipeline, trusted authorization callback, isolated_functional_verifier | Supplied independent tests, verify-only authorization; transient result not persisted repair lifecycle |
| Market `app.main` | engine/scanner, fundamentals/history, macro, valuation, paper services and PostgreSQL | Separate API/DB; no production promotion from this audit |

The function names and import edges for all 89 inspected source modules are in [project-architecture-inventory.json](project-architecture-inventory.json), generated using the existing `tools/audit_python_ownership.py`. It records 275 definitions, 72 local import entries, 16 same-name groups and no parse failures. These are not dynamically resolved callers, and do not prove equivalent semantics.

## Compatibility / trust review

- Canonical runtime workflow transitions: v03; persistence: v05. Keep v04 restore compatibility until caller/data migration evidence permits removal.
- v3 workflow/orchestrator state models are planning/legacy responsibilities; no fourth controller.
- Trusted verifier generations have distinct pinned trust baselines. Do not automatically alias/delete them.
- Phase-specific paper schema probes check different contracts; aggregate findings without dropping guards.
- `developer_agent/v3/workflow_controller.py` rejects unverified reports unconditionally. Do not enable unreachable code as cleanup.
- **ME-API-01:** `app/main.py` imports two functions as `analyze` (lines 9 and 186); the later valuation binding shadows the engine binding used at line 76. This source-confirmed conflict needs one separate alias fix and route regressions. No runtime code changed in this audit.

## PR dependencies

The source snapshot includes 127 open PRs with exact base/head metadata in the JSON inventory. The recent chain is **#126 → #127 → #128 → #129 → documentation checkpoint**, with earlier ancestry still relevant. They remain unmerged; main is `d987387…`. Source checkpoint #129 is 293 commits ahead of that main, with 187 changed files. Do not use historical counts such as “80 PRs” as current status or merge the chain as independent features.

## Before changing a function

Read the canonical register and [DUP matrix](AUD01_DUPLICATION_TRIAGE_AND_REFACTOR_GATES.md); search definitions, actual imports/calls, CLI consumers and tests; assign one owner; record the task, acceptance, code SHA and result. Adapter/migration tests precede deletion. No new queue, scheduler, autonomous executor or production change follows from this map.
