# Working on Central AI / Market Engine

Before changing code or planning a new module, read:
- `docs/audits/PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md` — canonical living architecture, owners, decisions, evidence and task register.
- `docs/audits/PROJECT_FOCUS_AND_COMPLETION_GATES_2026-11-02.md` — scope and P0–P4 order.
- `docs/audits/AUD01_DUPLICATION_TRIAGE_AND_REFACTOR_GATES.md` — compatibility/trust constraints before consolidation.

Use the existing owner first. Search definitions, callers, tests and PR dependencies with rg and the existing `tools/audit_python_ownership.py`; do not add another inventory implementation, queue, manager, controller, scheduler or verifier just to wrap existing behavior. Same-named definitions do not prove duplication.

For every task, update the canonical register with task ID, objective, existing owner/functions, changed files, PR/base/head/source SHA, exact checks/results, blockers and one next action. Distinguish source/CI, operator-provided VPS evidence, and unverified state. The generated JSON inventory is a dated source snapshot, not live telemetry. Git history preserves exact changes; do not create a new dated master register at each handoff.

Keep the recorded safety boundaries: paper simulator first, IBKR paper later, no live orders; automated planning cannot approve deployment. A successful CI run or API-only transfer does not authorize worker activation, merge, production database migration or arbitrary generated-code execution on the production VPS. Follow the user's explicit authorized scope.

For documentation-only changes, validate links and JSON/source references; do not add tests or runtime modules for bookkeeping. For behavior changes, run relevant meaningful regressions and required existing checks. Never paste provider keys, env values, private backups, raw container configuration or secret-bearing logs into public artifacts.
