# AUD-01 / AUD-02: canonical dependency map and progress
Snapshot 2026-10-26. Source-only audit, not VPS/runtime verification.

## Canonical workflow path
DeveloperWorkerCoordinator -> PersistentTaskBridge -> TaskBridge -> DeveloperOrchestrator (initial task)
PersistentTaskBridge -> TaskStorage (authoritative task records), TaskQueue (leases), PersistentWorkflowV05 (state)
PersistentWorkflowV05 -> WorkflowController v03 (canonical transitions)
DeveloperWorkerCoordinator -> TaskFileTargets -> DeveloperTaskRunner -> HeartbeatWorker and TaskQueue.

These are complementary responsibilities. Do not build a second orchestrator or new queue.

## Overlap requiring careful consolidation
- Three stage models: developer_agent/v3/workflow.py, developer_agent/v3/orchestrator.py, central_ai/workflow_controller_v03.py. Canonical runtime controller is central_ai/workflow_controller_v03.py; migrate callers via tests.
- Persistent workflow v04/v05: preserve v04 restore compatibility.
- Trusted verifier secure_runner.py, secure_runner_v21.py, secure_runner_v22.py: different trusted baseline paths; do not delete without security tests.
- developer_agent/v3/workflow_controller.py has an unconditional raise in verify_report, leaving code after it unreachable. Keep fail-closed until verified replacement.
- Paper schema preflights check distinct legacy, NUMERIC, constraints, values. Compose reports; do not delete specialized guards.

## Recorded PR chain (draft, stacked)
#74 -> #75 -> #76 -> #77 -> #78 -> #79 -> #80 -> #81 -> #82 -> current audit.
Earlier #47–#73 are staged predecessors. A11.15.x is another lineage requiring reconciliation.
The 80 open PRs are NOT 80 standalone features. Reconfirm base/head/diffs before any merge.

## Task states
AUD-01: Core call path mapped; exhaustive AST/call-site scan remains OPEN.
AUD-02: Main Stage 2 PR chain mapped; complete open-PR triage remains OPEN.
AI-01: Existing coordinator/bridge/queue identified; end-to-end integration tests remain OPEN.
DB-01: BLOCKED on read-only live market schema report.
DB-02: BLOCKED on verified backup/restore.
DB-03: Production Alembic requires DB-01/02, reviewed runbook and human authorization.
DATA-01: SEC client/normalizer exist, safe persistence still PARTIAL.

## Non-duplication protocol
Before code: inspect this map, search existing functions, import callers/tests/PRs; assign one owner. Record task ID, modified files, PR SHA/CI, blockers and next step. No merge, VPS edits, live DB migration or real trades from these audit PRs.
