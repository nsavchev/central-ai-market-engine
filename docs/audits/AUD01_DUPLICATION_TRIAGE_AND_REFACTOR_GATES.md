# AUD-01: duplication triage and refactor gates

Source snapshot: branch `audit/aud01-static-import-definition-inventory`. Automated AST inventory CI: **27/27 successful** on commit `dba9e63ed6a72d719ef84317c496f3364935a0be`. The scanner identifies names/imports; same names do NOT prove equivalent semantics.

| ID | Candidate overlap | Canonical owner | Required evidence before change | Decision |
|---|---|---|---|---|
| DUP-01 | Stage enum in developer_agent/v3/workflow.py, developer_agent/v3/orchestrator.py, central_ai/workflow_controller_v03.py | central_ai/workflow_controller_v03.py | Full caller map, persisted-state compatibility, old v3 unit tests | Adapter-first, no deletion |
| DUP-02 | Persistent workflow v04/v05 | central_ai/persistent_workflow_v05.py | Legacy SQLite restore fixture and old schema migration tests | Keep v04 compatibility |
| DUP-03 | trusted_verifier_v2 secure_runner, secure_runner_v21, secure_runner_v22 | Distinct pinned baseline entrypoints | Signature checks, CLI use, security regression and trust provenance | Do NOT merge automatically |
| DUP-04 | TaskBridge.registry and durable TaskStorage | TaskStorage via PersistentTaskBridge | restart and duplicate-task tests, fail-closed flags | Runtime storage authoritative |
| DUP-05 | schema preflight modules | Phase-specific modules, aggregate report only | Legacy / numeric / relational / value coverage | Not equivalent; retain |
| DUP-06 | numerous CI workflows | Domain-grouped workflows eventually | Branch protection status parity, isolated DB permissions | Defer |
| DUP-07 | code after unconditional rejection in developer_agent/v3/workflow_controller.py | Trusted verifier lifecycle | Invocation review and fail-closed tests | Dead path candidate; do not enable |

## Controls
1. For each DUP item, record original callers before modifications; a matching AST name is insufficient.
2. Preserve `approved=False`, `deployment_allowed=False`, bounded retries, trusted allowlist and independent verifier.
3. Run full regression suite and the relevant GitHub Actions workflows before and after an isolated refactor.
4. Never remove a trusted baseline or legacy persisted version without migration and negative-case proofs.
5. Track task ID, owner, PR, commit, CI result, blocked reason and next action in the architecture progress audit.
6. No change to production `market`, VPS or real trading as part of this audit.

Next bounded coding task: `DUP-01` — add *tests of the canonical workflow contract and legacy adapter consistency* before touching any old Stage model. Review `developer_agent/v3/workflow.py` and `orchestrator.py` callers first.
