# Central AI API-only transfer candidate — 2026-11-03

Purpose: transfer the exact CI-tested Central AI image first; Market Engine has a separate release. This document is preparation, NOT deployment authorization. Audited starting source: ec4689c575427b530dff038bd9534a58fcec548b. The bundle's head-sha.txt and checkout-sha.txt identify the NEW exact candidate and PR merge checkout actually built; do not substitute a branch tip.

## Contents and acceptance scope

The existing P0 workflow exports central-ai-image.tar after local image/API checks. Only the first runner exports; the independent-comparison job must also succeed on the same workflow run before using the artifact. Require all 33 workflows green on head-sha.txt. An artifact may exist even if a later comparison fails: presence alone is not approval.

manifest.sha256 covers the image archive, image ID, source refs/epoch, source recipe hashes, API report, reviewed VPS preflight and these instructions. GitHub artifact archive digest and in-bundle checksums prove integrity relative to retrieved metadata, not independent registry authenticity. Artifact retention is 14 days; preserve reviewed evidence before expiration.

Entrypoint is uvicorn central_ai.app:app, UID 10001, immutable Python base and hash-locked dependencies. The image contains existing Central AI/developer-agent source, but this release enables only the API; autonomous review/verification/workers are not started. There is no Market Engine app, PostgreSQL service or migration in this transfer procedure.

CI runs each image with read-only root, no network, no provider credentials, no published port, a fresh disposable volume and Task API NO. It checks health, unauthorized 401, authenticated Task API 503, writable volume as UID 10001 and no task database creation. A second clean build and separate runner must match.

## 1. First obtain current VPS evidence

Use only the reviewed standalone vps-readonly-preflight.sh from this checksum-verified bundle. Review it, then run it as a standalone file on the operator-controlled VPS; no git pull/checkout or production script replacement. Its output must be reconciled before any cutover. Do not paste environment values or raw Docker/Compose output.

A successful preflight does not demonstrate backup restoration. Retain the old Central AI image, existing production Compose override and protected environment file. Verify restoration separately on disposable storage. Existing API/database container IDs and staging timer configuration must be recorded and unchanged by the API-only cutover.

## 2. Verify transferred files before loading an image

In a separate directory on an approved test host (or a separately authorized isolated VPS test session):

```bash
sha256sum -c manifest.sha256
IFS= read -r expected_image < image-id.txt
[[ "$expected_image" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 1
docker load --input central-ai-image.tar
test "$(docker image inspect "$expected_image" --format '{{.Id}}')" = "$expected_image"
```

docker load imports an image; it does not start it. Do not rebuild from a floating tag or run docker compose up in the production directory. Do not print/copy .env.central into this bundle or use production provider keys for isolated tests.

## 3. Isolated API acceptance — separate explicit operator session

The following starts only a named test container and fresh test volume. It publishes no port and has no external network or production volume. Verify the names are unused; stop on collision.

```bash
test_container=central-ai-api-isolated-check
test_volume=central-ai-api-isolated-check-data
if docker inspect "$test_container" >/dev/null 2>&1; then exit 1; fi
if docker volume inspect "$test_volume" >/dev/null 2>&1; then exit 1; fi
docker volume create "$test_volume"
docker run -d --name "$test_container" --label central-ai.scope=isolated-api-acceptance --network none --read-only --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=64 --memory=256m --cpus=1 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=8m --mount "type=volume,src=$test_volume,dst=/var/lib/central-ai" -e CENTRAL_API_TOKEN=ci-only-release-token-000000000000 -e CENTRAL_TASK_API_ENABLED=NO -e CENTRAL_TASK_DB=/var/lib/central-ai/tasks.sqlite "$expected_image"
```

The token above is a public synthetic test fixture, never a production token. Probe via docker exec from inside this container, using the same accepted /health, /providers and /tasks cases from the CI workflow. Do not call a provider or enable tasks. Record image ID, UID, expected HTTP statuses and disposable-volume writability. Inspect only sanitized logs on failure. Do not run arbitrary generated candidate code here.

After review, remove ONLY this labeled test container and this test volume; confirm the label before removal. Never use down -v or prune. If cleanup is uncertain, stop and inspect before retrying.

## 4. Central AI production promotion — not yet executable

Assemble a final service-only override only AFTER receiving current VPS evidence and explicit approval:
- retain Compose project market_engine_v0_9 and existing localhost 127.0.0.1:8010 binding;
- select only central-ai with --no-deps and an exact verified image;
- retain protected existing .env.central and existing external SQLite volume identity;
- preserve Task API NO, current API/Postgres containers and staging timer;
- use a separate reviewed override; do not replace repository/prod Compose files blindly;
- review effective configuration without printing secrets; no build/pull/recreate of api/db;
- retain exact previous image/config and verify rollback health before sign-off.

No runnable production cutover is supplied here because actual resolved VPS configuration, current image/volume permissions and rollback/restore evidence have not yet been received. API-only means behavior and promotion scope, not that the complete autonomous developer loop is ready.

## 5. After stable Central AI API promotion

Only then return to developer-loop activation criteria and Market Engine's separate paper-only acceptance/migrations. No real trading. Reviewer key/service provisioning remains blocked and is not required merely to run the API with Task API NO.
