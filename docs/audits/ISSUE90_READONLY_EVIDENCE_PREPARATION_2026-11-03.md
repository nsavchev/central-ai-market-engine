# Issue #90 read-only evidence preparation — 2026-11-03

Parent 0c92b4b1a3a6690fada96f1409d2e48bb37b8956, PR #128. Expanded existing scripts/ai24_vps_readonly_preflight.sh; no second collector/runtime service. It has NOT been executed on the production VPS by this work.

## Output and trust

The script preserves its existing service, Task API NO, named-volume, localhost health, backup-file presence and timer checks. It adds JSON evidence after those checks: UTC time, hashed hostname fingerprint, repository path, full deployed Git SHA/branch, dirty flag (without potentially sensitive filenames), collector-file SHA256, two Compose source-file hashes, and selected container/image metadata for central-ai/api/db. Selected metadata includes status, image ID, RepoDigests if present, configured user, readonly/privileged flags, network mode, CPU/memory limits and redacted mounts. Bind source paths and environment values are never printed. RepoDigests may legitimately be empty for local images; image ID is not registry authenticity.

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
