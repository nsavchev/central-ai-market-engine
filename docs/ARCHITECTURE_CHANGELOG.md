# Central AI Architecture Decisions and Change Log

This is the durable architecture record. Git commits and pull requests are the authoritative implementation history. Update this document **in the same pull request** as each architectural change. Never record credentials, tokens, private paths, or raw exception messages.

## Change documentation contract
For every change record: ID/date, problem and evidence, decision and reason, affected modules, invariants/permissions, tests (actual results, not assumptions), risks, rollback, commit/PR link, and status. A proposed or untested change must never be marked verified.

## Architecture invariants
- Central AI orchestrates specialized functions/agents; do not create redundant models or duplicate existing queue/bridge/worker logic.
- Worker code changes and repairs are isolated. No automatic production deployment, no live trading, no implicit permission elevation.
- Keep `approved=0` and `deployment_allowed=0` restrictions.
- Every repair must have bounded attempts, wall-clock time, child-task depth/count and cost budget, persisted across restarts.
- Deduplicate repeated failures using stable problem fingerprints. Never reset budgets by creating a new child task or renaming an error.
- Final states: VERIFIED (objective tests passed), ESCALATED (limits or unsolved), CANCELLED. Terminal tasks cannot silently restart.
- No secrets, tokens or raw exception text in durable audit logs.
- Stop and escalate if there is no measurable progress, repeated identical outcomes or a safety boundary is encountered.
- Distinguish a green CI check from complete architecture and security review.

## Decisions
### ADR-001 — Central AI bounded autonomous repair (2026-10-24)
**Problem:** Developer workers may fail repeatedly; unchecked recursive repairs can create an infinite loop and unnecessary cost.

**Decision:** Reuse TaskQueue, PersistentTaskBridge, DeveloperWorkerCoordinator and DeveloperTaskRunner. Central AI coordinates diagnosis -> bounded sandbox repair -> targeted tests -> regression -> VERIFIED or ESCALATED. Default proposed caps: three repair attempts, 15 minutes wall time, stop after two identical repeated failures; explicit configurable cost and child-task limits. Persist a canonical problem identity across retries and restarts.

**Why:** Achieve autonomous recovery without uncontrolled recursive execution, bypassing permissions or modifying production.

**Status:** Architectural requirement; anti-loop controller not yet implemented.

**Tracking:** Issue #1: https://github.com/nsavchev/central-ai-market-engine/issues/1

### CHG-001 — A11.15.5 sanitized failure audit (2026-10-24)
**Problem:** Failures in the coordinator were not durably recorded, preventing diagnosis and supervised repair.

**Change:** Added `TaskQueue.record_failure` for current lease owner, sanitized error type only; coordinator now records failure best-effort and re-raises the original exception. Added lease-expiry guard and four regression test cases. Added GitHub Actions workflow for the isolated tests.

**Files:** `central_ai/task_queue.py`, `central_ai/developer_worker_coordinator.py`, `tests/test_failure_audit.py`, `.github/workflows/failure-audit-tests.yml`.

**Why:** Central AI needs an audit trail before deduplication and autonomous repair, without exposing raw exception details.

**Security:** No permission escalation, production deployment, or brokerage operations. Current audit event stores only the exception class, not full diagnostics; detailed safe diagnostic context is future work.

**Validation:** Screenshot supplied by repository owner shows one passing GitHub check on PR #2. Individual test cases and full regression suite have not been independently inspected here. PR remains draft pending review.

**Risks / open questions:** Error class alone cannot distinguish different root causes; audit event format is minimal. Additional tests needed for expired leases and coordinator error propagation. Ensure no sensitive context is stored in later diagnostic expansion.

**Rollback:** Revert commits from PR #2 while still unmerged; no production rollback required.

**Commits:** `ccba1d9`, `8dc0bec`, `5bff418`, `ea550b7`, `92cd150`.

**PR:** https://github.com/nsavchev/central-ai-market-engine/pull/2

**Status:** Implemented in feature branch; initial CI green as shown in screenshot, awaiting re-run and broader validation.

**Follow-up (2026-10-24):** Added explicit tests for expired lease rejection and malformed/unsafe error codes (`a0b025f`). This closes two test gaps identified above. Results of these newly added tests are not yet verified; the earlier green check predates this commit. No production changes.


**Verified CI evidence (2026-10-24):** GitHub Actions run 40121676796, job 120954406395, finished SUCCESS. The job log explicitly reports `Ran 6 tests in 0.089s` and `OK`. This confirms the six isolated failure-audit tests; it does not constitute full project regression, coordinator integration testing, or production validation. Source: https://github.com/nsavchev/central-ai-market-engine/actions/runs/40121676796

**Next quality gate:** Before merge, add coordinator failure-propagation integration tests and run broader regression checks. Keep PR #2 in draft until review.

**Follow-up integration tests (2026-10-24):** Added two coordinator tests (`4892eda`) to confirm original exceptions propagate, failure type is audited, and audit storage failures do not mask the original error. Tests are pending CI verification. Reason: the first six tests exercised TaskQueue, not coordinator integration. Rollback: revert this feature-branch commit; no VPS changes.

## Planned next records
- CHG-002: A11.15.6 failure fingerprint and FIX task deduplication.
- CHG-003: A11.15.7 isolated repair and rollback.
- CHG-004: A11.15.8 verification and regression gates.
- CHG-005: A11.15.9 persistent anti-loop controller.
- CHG-006: A11.15.10 end-to-end architecture/security review.
