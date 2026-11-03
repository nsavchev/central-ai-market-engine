# P0 CI action provenance and credentials — 2026-11-03

Parent audited source: 430ba55560ad98e4b4b97e96cdb28d7061f4c802, draft PR #128. All 33 workflow files read and updated. Existing action major-version tags were resolved through the upstream repository Git tag API to commit objects and the exact commit API read confirmed those objects. GitHub reported verified commit signatures for all five commits; this does not establish a complete source/security audit.

| Action | Previous ref | Pinned commit |
|---|---|---|
| actions/checkout | v4 | 11d5960a326750d5838078e36cf38b85af677262 |
| actions/setup-python | v5 | a26af69be951a213d495a4c3e4e4022e16d87065 |
| actions/upload-artifact | v4 | ea165f8d65b6e75b540449e92b4886f43607fa02 |
| docker/setup-buildx-action | v3 | 8d2750c68a42422c14e847fe6c8ac0403b4cbd6f |
| actions/download-artifact | v4 | d3f86a106a0bac45b974a628896c90dbdf5c8093 |

The pin manifest is release/ci-actions.lock.json. All uses entries use full 40-character SHAs. All 33 checkout steps explicitly set persist-credentials: false. No requested token permissions increased (contents: read remains). Actions are retained at the commits currently resolved by their existing major-version tags, not migrated to a new major. Future updates require explicit pin/manifest review and CI.

Regression tests inspect all current workflow action steps and reject mutable refs, unreviewed pin drift and persisted checkout credentials in the repository's simple step format. They are a regression check, not a general YAML security parser. Semantic local YAML validation confirmed the actual checkout setting and permissions for every workflow. All 61 local tests pass; all shell bodies parse. The test is added to the existing DUP-01 job, not a new workflow.

No runtime modules, queues, verifiers or scheduler ownership changed. No VPS operation, deployment, live trading, token write permission, production credential or new secret was introduced. Host-runner job permissions and event/workflow contents still require normal review; SHA pinning alone does not make untrusted PR code safe.

Parent exact-image acceptance: run 41591499327, artifacts 13210601566 (first), 13210506251 (second), 13210013691 (comparison). First manifest has 27 valid hashes; both API acceptance reports match across runners. Health ok, uid 10001, unauthorized 401, Task API 503, no task DB, no provider credentials. 33/33 workflows passed on parent. New-commit CI must be verified independently.

Next open P0 boundaries: authenticated candidate/test provenance and immutable input snapshot; host Docker execution remains excluded from production; current VPS/deployed SHA/schema evidence, disposable restore verification, full changed-file disposition and issue #90 NO-GO remain. No approval/merge/deployment inferred from CI.
