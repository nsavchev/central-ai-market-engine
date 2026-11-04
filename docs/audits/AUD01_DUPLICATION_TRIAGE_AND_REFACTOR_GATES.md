# AUD-01: duplication triage and refactor gates

Updated 2026-11-04 for source `7fd9c850f73edea70988b017d8dda2a4b70f3fc3`. The [living architecture register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md) owns current task states and decisions. The existing AST scanner found 89 source modules, 275 definitions, 72 local import entries and 16 same-name groups, with no parse failures. The [JSON inventory](project-architecture-inventory.json) is a source snapshot, not a runtime trace; matching names do not prove equivalent behavior.

| ID | Candidate overlap | Canonical owner | Required evidence before change | Decision |
|---|---|---|---|---|
| DUP-01 | Stage models in developer_agent/v3/workflow.py, orchestrator.py and central_ai/workflow_controller_v03.py | v03 transitions + persistent v05 | Actual callers, persisted-state compatibility and legacy/v3 contract tests | Adapter-first; no fourth controller or automatic deletion |
| DUP-02 | Persistent workflow v04/v05 | central_ai/persistent_workflow_v05.py | Legacy SQLite restore fixtures and schema compatibility | Keep v04 compatibility until removal is proved safe |
| DUP-03 | trusted_verifier / trusted_verifier_v2 and secure_runner generations | Distinct pinned baseline entrypoints | Signature/CLI callers, security regression and trust provenance | Do not automatically merge or alias trusted baselines |
| DUP-04 | TaskBridge.registry and durable TaskStorage | TaskStorage via PersistentTaskBridge | Restart, duplicate-task and approval-flag consistency | Runtime durable storage authoritative; planning registry transient |
| DUP-05 | Paper schema preflight modules | Phase-specific owners | Legacy/numeric/constraint/value coverage and consumer contracts | Compose results; retain specialized guards |
| DUP-06 | Many CI workflows | Eventual domain grouping | Required-check parity, coverage, isolated DB permissions | Defer consolidation until release checks are green and reviewed |
| DUP-07 | Code after unconditional rejection in v3/workflow_controller.py | Trusted verifier lifecycle | Invocation review and fail-closed tests | Dead-path candidate; do not enable as cleanup |
| ME-API-01 | Two different analyze imports in app/main.py | engine.analyze for relative strength; advanced_valuation.analyze for DCF | Source conflict confirmed; route regression with isolated data for both contracts | Separate minimal alias correction; no new algorithm/module; not fixed by this documentation change |

## Controls

1. Search and record original callers, CLI consumers and tests before modification; AST names alone are insufficient.
2. Preserve automated `approved=False` / `deployment_allowed=False`, bounded retries, independent trusted tests and verifier allowlists.
3. Run relevant regressions and required checks around any isolated behavior refactor. Do not create another runtime mechanism to maintain bookkeeping.
4. Never remove a legacy persisted version or trusted baseline without migration/compatibility and negative-case proofs.
5. Record task ID, objective, existing owner/functions, changed files, PR/base/head, exact CI SHA/result, blockers and next action in the living register.
6. No production migration, worker activation, live trading or automatic merge/deploy from an audit result.

The next active task is **P0-CI**, as recorded in the canonical register: retry the 32 remaining previously blocked workflows at PR #129's unchanged source. Consolidation and ME-API-01 are tracked work, not permission to change unrelated runtime behavior in this checkpoint.
