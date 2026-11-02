# Central AI / Market Engine — release integration audit (2026-11-02)

Scope: read-only inspection of the AI-10 through AI-24 branch stack, compared to main. VPS operator reported AI24_VPS_ACCEPTANCE_PASSED for the currently deployed earlier candidate, **not** this branch.

## Findings and release disposition

**BLOCK: no verified autonomous end-to-end development workflow.** The verified AI-14 test manually calls the persistent task queue / bounded analyzer, handoff, adapter and verifier gate. The production FastAPI app and worker scheduler do not yet orchestrate the entire AI-10→AI-19 sequence. AI-15 expects externally supplied Markdown Python; AI-18 expects separately supplied functional tests. None of the tests demonstrate automatic synthesis of a patch, independent review, iterative repair or merge.

**BLOCK: untrusted-code execution environment.** AI-18 functional testing starts a restricted Docker container, but the host-side process needs Docker daemon access; basic Docker isolation is not a high-assurance sandbox against malicious source. Test artifacts supplied to the runner are not independently authenticated; digest-pinned runner image alone does not establish provenance. Candidate file hash is checked before mounting, leaving a possible replacement/read race. Do not invoke AI-18 with arbitrary untrusted code on the production VPS.

**BLOCK: timeout cleanup guarantees are limited.** AI-21/22 test the normal forced-removal path, but host daemon outages, cleanup uncertainty, parallelism and leftover resources need explicit operational quarantine. A timeout with unconfirmed cleanup must prevent further operations.

**HIGH: release-preflight checks are partial.** AI-23 uses string containment checks rather than semantic Compose parsing; this is a convenience preflight, **not** a security policy decision. AI-24 VPS check verifies the currently deployed Central AI API (Task API disabled), named SQLite volume and existing rollback files, but does not validate this full branch's container image in isolation.

**HIGH: stacked draft PR chain.** AI-10..AI-24 is an unmerged chain stacked on a release branch that itself contains many earlier changes; 240 commits ahead of main, 152 changed files from the latest GitHub comparison. Each individual CI success is a necessary, not sufficient, condition for merging. A focused diff review and a single immutable release SHA are required.

**DUPLICATION AUDIT:** Existing TaskQueue, PersistentTaskBridge, DeveloperWorkerCoordinator, worker_batch, worker_scheduler, worker_supervised implement distinct layers (storage/ownership, coordinator, batching, scheduling, supervision); do **not** add a second queue or scheduler. Existing developer_agent v3 Workflow is an in-memory planning state machine, distinct from the persisted workflow v05. Do not use its stages as proof of persistent execution or approval. The AI-11→AI-13 adapter modules are orchestration steps; keep them behind one explicit execution path when ready.

## Release gate

1. Keep production CENTRAL_TASK_API_ENABLED=NO and paper-only trading.
2. Keep all untrusted candidate execution off the production VPS; use dedicated isolated workers with explicit authorization and no production secrets.
3. Add authenticated artifact provenance and robust verification of a frozen candidate/test snapshot.
4. Verify end-to-end orchestration, bounded retries, cancellation/cleanup, and negative security tests as one suite.
5. Produce an immutable candidate image and run isolated VPS acceptance with rollback; inspect full Compose effective config and hashes.
6. Only then consider merging reviewed changes and separately authorize production activation. No automatic deploy and no real trading.
