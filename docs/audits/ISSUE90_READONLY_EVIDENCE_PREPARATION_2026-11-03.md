# Issue #90 read-only evidence preparation — 2026-11-03

Parent 0c92b4b1a3a6690fada96f1409d2e48bb37b8956, PR #128. Expanded existing scripts/ai24_vps_readonly_preflight.sh; no second collector/runtime service. It has NOT been executed on the production VPS by this work.

## Output and trust

The script preserves its existing service, Task API NO, named-volume, localhost health, backup-file presence and timer checks. It adds JSON evidence after those checks: UTC time, hashed hostname fingerprint, repository path, full deployed Git SHA/branch and dirty flag when Git metadata is accessible (without potentially sensitive filenames), collector-file SHA256, two Compose source-file hashes, and selected container/image metadata for central-ai/api/db. Selected metadata includes status, image ID, RepoDigests if present, configured user, readonly/privileged flags, network mode, CPU/memory limits and redacted mounts. Bind source paths and environment values are never printed. RepoDigests may legitimately be empty for local images; image ID is not registry authenticity.

Git optional locks are disabled. Extra commands only read Git/container/image metadata and local Compose/collector file bytes. No source checkout, service changes, Docker run/build/pull, database connection or migration added. Existing legacy health/exec checks remain read-only probes; normal application/access logging by those services is not suppressed.

The fixed deployment and historical backup paths are unchanged. If they no longer match the VPS, the script must fail and be reviewed; do not fix a missing backup/service by automatically creating or replacing it.

## Explicit non-proofs

backup_files_present=true is emitted only after existing nonempty archive checks. backup_restoration remains unverified: file existence is not restore proof. SQLite schema, PostgreSQL schema and runtime call graph remain not_collected. audit_complete=false and deployment_authorized=false always. A dirty working tree is reported, not silently declared clean. Collector Git SHA and container image identity are distinct; neither proves source-to-image provenance by itself.

On metadata command failure or invalid data, emit only generic collection_failed JSON and exit nonzero; raw command stderr/stdout or environment is not dumped. A legacy prerequisite failure exits before JSON and is not a successful collection.

## Validation

bash -n passed. 110 local tests passed including the embedded collector exercised with synthetic subprocess responses: known sensitive mount paths/filenames are absent; deployed SHA/dirty flag/backup limits are preserved; metadata failure does not leak captured command output. The complete shell script was not run against real services in local/CI tests. Existing DUP-01 workflow runs the two collector regressions; no extra workflow added. Final-commit CI must be checked separately.

## Operator handoff without deployment

Review the exact script commit and run only a standalone reviewed copy on the operator-controlled VPS. Do not git pull/checkout the release stack, overwrite Compose files, enable Task API or install a reviewer key merely to collect evidence. Preserve stdout from this script for review; do not supply .env, raw full docker inspect/config output, API tokens, credentials or task records. Compare the report with the frozen GitHub candidate and known VPS release override before discussing any deployment.

Next remaining evidence: source/runtime ownership reconciliation DUP-01..07, read-only SQLite/PostgreSQL schema inventory using reviewed procedures, integration/source availability, restore and consistency test in a separate disposable environment, plus authenticated reviewer provisioning and persisted review audit. No current VPS evidence or restorable backup is claimed by this repository change.


## Archive-based deployment compatibility — P0-OPS-COLLECTOR-01

Operator screenshots on 2026-11-04 show the checksum-verified earlier collector reaching its Python block and returning collection_failed; a separate read-only Git probe reports deployment Git metadata unavailable. This establishes a metadata collection blocker, not its precise cause (absent .git, inaccessible repository or Git executable), a failed service, or a deployed source SHA. Legacy preflight checks reached before the Python block passed at that observation; a complete fresh metadata report is still required.

The same collector now catches Git command nonzero/missing-executable errors locally. It emits git.sha/branch/dirty=null, git_metadata_status=unavailable, collection_status=partial and evidence_gaps=[deployment_git_metadata], preserving successfully read service/image/Compose metadata. A null dirty flag is not a clean tree. Accessible Git retains the original git field shape and adds available/collected status. Collected means these collector fields were read, not that the full #90 audit is complete. Invalid SHA, Git timeout, Docker or Compose-hash read failure still return generic collection_failed/nonzero; no raw command errors are published. audit_complete and deployment_authorized remain false. The final shell marker is FINISHED rather than PASSED, because a partial report cannot establish source provenance.

No git init/clone/pull, production file replacement, restart, activation, DB query/write or backup/restore action is added. The operator uses a checksum-verified standalone temporary copy; the deployment remains unchanged. Collector SHA256 after correction: ee50ca0e157cef600072446b6305d3c3af235d50bddd8e5977bbd319e468416f.

Validation: before correction, 2 failed / 4 passed; after correction, 6 passed in existing tests/test_vps_readonly_evidence.py. These execute the embedded Python collector with synthetic subprocess responses, not the complete shell script or real VPS. Missing Git executable/repository, sensitive-output redaction, null provenance, preserved service evidence, invalid SHA/timeout and fatal metadata error are covered. bash -n and git diff --check passed. Existing DUP-01 owns the tests; no workflow or second collector is added. Exact-source CI and operator rerun are separate pending evidence.
