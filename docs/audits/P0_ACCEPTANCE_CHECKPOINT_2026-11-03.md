# P0 / issue #90 acceptance checkpoint — 2026-11-03

Audited source: 408e8ea7367b89f3c5e33b982e1cb56843dd0f88 on draft PR #128. This checkpoint introduces no new runtime module or queue. No merge, deployment, production database write or live trading authorized.

## Evidence and disposition

| Gate | Evidence | Status / remaining work |
|---|---|---|
| Immutable release recipe and dependency lock | release/Dockerfile.release, source-controlled amd64 lock, release-only ignore | CI passed; actual production Dockerfile deliberately unchanged |
| Repeatability across separate runners | Run 41590508584, artifact 13209519127; archive SHA256 dc43bbaec539cab35521f4367c5dfbfcd17ffbe767973d697a648cfe57d4b151 | Download verified; all 11 comparison fields true; 33/33 workflows on audited SHA |
| Static recipe hardening | 25 tests, including 11 new negative cases reproduced before fix | CI passed on audited SHA; narrow recipe validator is not a general Docker sandbox |
| Exact release API acceptance | New step in existing locked-candidate job; both images on both runners | Pending CI for this change; previously only third-party imports were smoked in this job |
| Workflow permissions | Read all 33 changed workflow sources at audited SHA | All declare contents: read; no pull_request_target, secrets expression or explicit token write permission found. This is a source scan, not a secret scan or proof of external app settings |
| Action provenance | Workflow actions use movable version tags; checkout credentials use default persistence | Open hardening work; action pinning/credential minimization not proven |
| Candidate/test provenance | verified_review_pipeline accepts caller test path; functional verifier hashes only candidate before bind mount | BLOCK autonomous untrusted execution; tests not independently authenticated; mutable file race remains |
| Host Docker authority | isolated_functional_verifier invokes host Docker | BLOCK production execution of untrusted candidates; use isolated non-production infrastructure |
| Cleanup | cleanup_unconfirmed returned on timeout removal uncertainty | Operator quarantine required; no automatic retry on uncertainty |
| Compose reconciliation | Existing VPS external-volume override differs from repository base | Current resolved configuration unavailable; must not replace override |
| VPS deployed SHA, schemas and runtime imports | Historical comments and AI24 script only | UNVERIFIED current state; CI does not satisfy this |
| Restore proof | AI24 script checks backup archive presence, not restore | BLOCK migration; require separate disposable restore and consistency results |

## Change inventory, not a completed full audit

GitHub compare main...408e8ea7367b89f3c5e33b982e1cb56843dd0f88: 284 commits ahead, 173 changed files. Counts: {".github":33,"root":3,"alembic_stage2":3,"app":14,"central_ai":18,"deploy":3,"developer_agent":3,"docs":29,"migrations":1,"release":3,"scripts":1,"tests":60,"tools":2}. All 33 changed workflow files were read. Selected trust-boundary files inspected: release_preflight.py, isolated_verifier.py, isolated_functional_verifier.py, verified_review_pipeline.py, app.py and scripts/ai24_vps_readonly_preflight.sh. All 173 files have NOT been fully reviewed. Existing inventory and architecture ownership documents remain relevant; do not create another controller, verifier or scheduler.

## Exact image acceptance added to existing workflow

Run both built release images with Task API NO, uid 10001, read-only root, no network, no bind/production volumes, no provider credentials, dropped capabilities and resource limits. Probe local health, authenticated provider configuration, unauthorized providers/tasks/ask (401), authenticated tasks submit/status (503 TASK_API_DISABLED), and absence of a created SQLite database. Use a clearly synthetic token. Compare JSON acceptance outputs locally and across runners and include them in the artifact integrity manifest. Test the real default uvicorn entrypoint; no model calls or candidate execution.

This is CI-only API acceptance. It does not verify PostgreSQL, backup restoration, autonomous developer loop or deployment. Acceptance output must be read alongside job conclusion.

## Next sequence and owners

1. Development/CI: verify new exact-image API result; preserve immutable source/image/artifact references.
2. Development/security: action provenance and credentials review, then candidate/test provenance boundary within existing components; no automatic executor activation.
3. Operator evidence: UTC timestamp, deployed full SHA and clean/dirty status; effective service/image/mount summary without secrets; read-only SQLite and PostgreSQL schema inventory and runtime owner map.
4. Operator/isolation: restore backups only to a separate disposable environment and record consistency and rollback evidence.
5. Review: reconcile all changed-file dispositions and DUP-01..07 with actual deployment; issue #90 remains NO-GO until evidence is complete. Separate explicit approval precedes any rollout.

Do not paste .env, tokens, provider keys, connection URLs, task descriptions or raw sensitive Compose/log dumps. No request for production changes is made by this checkpoint.
