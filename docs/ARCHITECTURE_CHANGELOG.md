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

**CI gate update (2026-10-24):** GitHub Actions run 40122432945, job 120956694505, completed SUCCESS. Logs show all 8 isolated tests passing in 0.077 seconds, including the two coordinator integration tests. Evidence: https://github.com/nsavchev/central-ai-market-engine/actions/runs/40122432945 . This validates A11.15.5's focused tests, not the full repository regression suite or live environment. PR #2 stays draft pending review.

### CHG-002 — A11.15.6 persistent incident fingerprint and dedup (2026-10-24)
**Problem:** Repeated failures and process restarts must not create independent FIX incidents that reset repair budgets.
**Decision:** Add `central_ai/fix_incident_registry.py` as a metadata-only SQLite registry. Stable SHA-256 fingerprint uses validated component/error-code/operation identifiers; `INSERT OR IGNORE` with `BEGIN IMMEDIATE` serializes concurrent registrations. Duplicate sightings increase occurrences but preserve original source task and terminal state. Terminal incidents never auto-reopen.
**Why:** Establish persistent canonical problem identity before creating repair subtasks and enforcing global anti-loop budgets.
**Files:** `central_ai/fix_incident_registry.py`, `tests/test_fix_incident_registry.py`.
**Tests:** Six focused unit tests added; not yet executed. No production deployment or trading changes.
**Limitations:** A fingerprint based on class/component/operation may merge distinct root causes; do not automatically repair from fingerprint alone. Registry is not yet connected to the coordinator or a repair planner. Time, cost and repair-attempt budgets belong to A11.15.9.
**Rollback:** Revert feature-branch commits `47dcf00` and `508b321`; no live data touched.
**Status:** In development, CI pending.

**CHG-002 integration follow-up (2026-10-24):** CI runs 40123649746 (6/6 incident tests) and 40123649722 (8/8 failure-audit tests) succeeded. Added coordinator integration (`f89d2dd`) that registers a canonical incident only after an ownership-validated failure audit event. Added tests (`ead54bb`) for successful incident registration and rejection of unowned failure registration. Reason: avoid orphan/unauthorized incident creation and preserve the original exception. New integration tests are pending CI. Limitations: incident grouping currently uses component, error class and operation; this is coarse and should not be treated as verified root-cause identity. No automatic FIX subtask creation or execution. Rollback by reverting these feature-branch commits.

**CI integration gate (2026-10-24):** GitHub Actions runs 40124109410 and 40124109327 completed SUCCESS: 6/6 registry tests and 10/10 coordinator/failure-audit tests. Added concurrent registration test (`2cb3d35`) to exercise the atomic `BEGIN IMMEDIATE` plus unique-fingerprint guarantee across 12 workers. Rationale: real agents can report the same failure simultaneously; duplicates must not fork the repair state. New concurrency test pending CI. No permission or deployment changes.

### CHG-003 — A11.15.7 isolated candidate verification (2026-10-24)
**Reason:** Repair candidates must be checked without mutating trusted source files or executing generated code.
**Decision:** Add `IsolatedRepairStager` with disjoint workspace/staging roots, safe relative .py paths, symlink rejection, SHA-256 optimistic source guard, 1 MiB candidate limit, syntax compilation without execution, private temporary candidate verification, and automatic temporary deletion. Returns only metadata; never applies code or deploys.
**Files:** `central_ai/isolated_repair_stager.py`, `tests/test_isolated_repair_stager.py`.
**Validation:** Six unit tests added, CI pending.
**Limitations:** This is a staging/verification primitive, not a sandbox against malicious Python, not a repair executor, and not a durable rollback mechanism. It cannot establish behavioral correctness. Future work must implement explicit approvals, full isolated test execution with OS/container isolation, and atomic rollback before any application.
**Rollback:** Revert `a4b0955` and `7e6b48e` on the feature branch; production untouched.

**CHG-003 rollback rehearsal extension (2026-10-24):** Three prior CI runs succeeded (7/7 incident, 10/10 failure audit, 6/6 isolated stager tests). Added `RepairRollbackRehearsal` (`1ea880b`) and four tests (`eb3197a`) plus CI (`87ffebe`). It writes a candidate into a disposable temporary copy, restores its original bytes from a backup, verifies SHA-256 and confirms the trusted source remains unchanged. This is a rehearsal only; it does not provide a production-safe apply/rollback transaction. Reason: verify reversible candidate handling before designing an approved application path. New tests pending CI. Rollback: revert feature commits; no production changes.

### CHG-004 — A11.15.8 regression gates (2026-10-24)
**Evidence:** Prior PR #4 CI passed 27/27 focused tests across four jobs.
**Why:** Targeted unit tests alone cannot detect regressions in other Central AI modules.
**Decision:** Add `RegressionGatePlanner` to generate review-only allowlisted unittest commands (no shell execution or deployment), six focused tests, and a CI job that runs both planner tests and all tests discoverable by Python unittest. CI is independent of generated repair candidates.
**Files:** `central_ai/regression_gate_planner.py`, `tests/test_regression_gate_planner.py`, `.github/workflows/regression-gates.yml`.
**Limitations:** Full unittest discovery is not necessarily the entire project's test suite; pytest-only tests and external dependencies may need additional CI. No isolated candidate execution or repair approval is implemented. New CI pending.
**Rollback:** Revert `4827d0e`, `c91cb40`, `b2e0540` on feature branch; no VPS changes.

**CHG-004 CI diagnosis and fix (2026-10-24):** Initial full unittest discovery failed in run 40125522319: 41 tests discovered, 8 import errors due to missing `pytest` and `fastapi` in GitHub runner. Verified both dependencies are declared in repository `requirements.txt`. Changed `.github/workflows/regression-gates.yml` (`1ebaa10`) to install declared dependencies before running targeted and full discovery. Reason: test environment must match project requirements; no test exclusions or bypasses. Re-run pending; remaining failures must be investigated rather than suppressed. Rollback: revert workflow commit.

### CHG-005 — A11.15.9 persistent bounded repair budget (2026-10-25)
**Evidence:** A11.15.8 full unittest CI run 40128621117 succeeded: 6/6 planner tests and 33/33 discovered tests; four other workflows succeeded.
**Reason:** Repeated repair attempts must have durable limits across restarts and avoid loops.
**Decision:** Introduce `RepairBudget` with SQLite transactional attempt admission, hard cap 3 attempts, 900-second maximum window, escalation on repeated identical failure code, terminal states, and fail-closed validation. Metadata-only: does not execute repairs or deploy.
**Files:** `central_ai/repair_budget.py`, `tests/test_repair_budget.py`, `.github/workflows/repair-budget-tests.yml`.
**Validation:** Seven focused tests added; CI pending.
**Limitations:** Not yet integrated into an actual repair executor. Window is measured from first attempt and does not reset automatically. The failure-code comparison is a coarse heuristic. No explicit aggregate cost budget or subtask-depth limit yet; those must be implemented before autonomous execution. No live trading or VPS changes.
**Rollback:** Revert commits `97cb5a0`, `8667241`, `39d92ad` in feature branch.

**CHG-005 budget extension (2026-10-25):** GitHub Actions run 40158861381 passed 7/7 focused budget tests and run 40158861412 passed 40/40 full unittest tests plus 6/6 planner tests. Added `reserve_subtask` (`ed1481a`) with durable atomic cumulative integer cost reservations (default maximum 100 accounting units), depth <= 2, terminal/time/attempt guards, and schema migration for existing SQLite tables. Added four tests (`cff519d`); new CI pending. Reason: repeated subtasks must not reset cost/depth controls after restart. These units are not actual money, and the budget does not enforce provider/API spend or recursive lineage yet. Reservations are non-refundable and no code is executed. Rollback: revert feature commits; migration adds a non-destructive column.

**CHG-005 CI defect correction (2026-10-25):** Runs 40158970050 and 40158970033 failed because a depth=3 request raised `INVALID_DEPTH` rather than returning a fail-closed `LIMIT_EXCEEDED` denial; the other workflow checks passed. Commit `4ad7cd6` distinguishes malformed/absurd depth inputs from a valid integer exceeding the configured maximum. Hard max_depth remains 2; no execution or deployment permission changes. CI recheck pending. Reason: callers need deterministic denial semantics for exceeded policy budgets without weakening the guard. Rollback: revert correction commit.

**A11.15.10 preliminary audit finding (2026-10-25):** All six workflows on commit `026946b` passed, including 11/11 repair budget and 44/44 full unittest tests. Code review identified a safety gap: `reserve_subtask` previously allowed unlimited reservations up to the cost cap without requiring a new admitted repair attempt. Fixed in `0a60d97` by persisting reservation count and enforcing at most one reservation per admitted attempt, including across restarts; schema migration adds `reservations`. Added tests in `1a1c63e` and adjusted cost test to admit a second attempt before reserving again. **Pending CI.** Further gaps remain: no verified parent-child lineage, no actual provider spend tracking, and no automatic repair executor. These are merge blockers for autonomous execution. Rollback: revert commits in draft branch; no VPS changes.

**A11.15.10 follow-up review (2026-10-25):** CI runs 40161014266 and 40161014290 succeeded (13/13 focused budget and 46/46 full unittest). Review found a boundary bug: after the third attempt was admitted, `reserve_subtask` incorrectly rejected its first reservation because `attempts >= max_attempts`. Commit `bbe5e45` fixes this by relying on `reservations >= attempts` to prevent a fourth reservation; commit `f5117a0` tests that three admitted attempts may each reserve once and a fourth attempt is denied. **New CI pending.** Parent-child lineage remains unenforced: a caller can still pass arbitrary fingerprint/depth and use a separate budget. Do not enable autonomous repair until lineage and executor permission checks are atomic and verified. No VPS changes.

### CHG-006 — A11.15.10 canonical parent-child repair lineage (2026-10-25)
**CI baseline:** Commit 14bc34f passed all six workflows; repair budget 14/14, full unittest 47/47 and planner 6/6.
**Reason:** Without durable parent-child ancestry, independently keyed subtasks can evade shared depth/attempt budgets.
**Decision:** Add `RepairLineage` with immutable task-to-parent and canonical root fingerprint mapping in SQLite. Reject unknown parents, mismatched root fingerprints, reparenting, cycles by construction and depth above two. Restart-safe and idempotent. Add eight focused tests and a CI workflow.
**Files:** `central_ai/repair_lineage.py`, `tests/test_repair_lineage.py`, `.github/workflows/repair-lineage-tests.yml`.
**Validation:** CI pending. No tasks are created or executed by this module.
**Known blocker:** Ledger and RepairBudget are separate transactions and the budget API still accepts a caller-supplied fingerprint and depth. An executor must atomically resolve lineage and reserve the canonical root budget, prevent duplicate reservations by task ID, and check task permissions before any autonomous repair. No merge/deploy approval implied.
**Rollback:** Revert commits 54f1e9c, 6efe07e, 8c0fe7f on the feature branch; no VPS changes.

**CHG-006 atomic lineage budget follow-up (2026-10-25):** GitHub Actions commit `3e1a158` passed seven workflows, including 8/8 lineage and 55/55 full unittest tests. Added `RepairBudget.reserve_lineage_task` (`511321a`): under one SQLite `BEGIN IMMEDIATE` transaction it resolves the registered child task's immutable root fingerprint and depth, checks the canonical root's admitted attempt/time/cost limits, inserts a unique task-ID reservation, and increments the root budget. This requires the lineage and budget tables to share one SQLite database. Added six tests (`103cb13`) including 12 concurrent requests and sibling tasks, and a dedicated workflow (`588cf6d`). **New CI pending.** Reason: prevent arbitrary child-provided fingerprints and duplicate budget reservations from forking attempts. **Important remaining gap:** Legacy `reserve_subtask` still accepts caller-provided fingerprint/depth; autonomous executors must exclusively use `reserve_lineage_task` with explicit permission checks. No task creation, actual API spend enforcement, repair execution or deployment enabled. Rollback: revert these feature commits; no VPS changes.

## Planned next records
- CHG-002: A11.15.6 failure fingerprint and FIX task deduplication.
- CHG-003: A11.15.7 isolated repair and rollback.
- CHG-004: A11.15.8 verification and regression gates.
- CHG-005: A11.15.9 persistent anti-loop controller.
- CHG-006: A11.15.10 end-to-end architecture/security review.
