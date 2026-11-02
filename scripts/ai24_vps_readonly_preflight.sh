#!/usr/bin/env bash
# AI-24 read-only production preflight. Do not alter services, secrets or volumes.
set -euo pipefail
cd /opt/central-ai/release-v1/market_engine_v0_9
echo "AI24_PREFLIGHT_START"
docker compose -p market_engine_v0_9 -f docker-compose.central.yml -f docker-compose.central.release.yml config --quiet
docker volume inspect market_engine_v0_9_central_ai_tasks >/dev/null
docker inspect market_engine_v0_9-central-ai-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-api-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-db-1 --format '{{.State.Status}}' | grep -qx running
docker inspect market_engine_v0_9-central-ai-1 --format '{{json .Mounts}}' | grep -q 'market_engine_v0_9_central_ai_tasks'
docker exec market_engine_v0_9-central-ai-1 python -c 'import os; assert os.getenv("CENTRAL_TASK_API_ENABLED")=="NO"; assert os.getenv("CENTRAL_TASK_DB")=="/var/lib/central-ai/tasks.sqlite"'
curl -fsS --max-time 4 http://127.0.0.1:8010/health >/dev/null
curl -fsS --max-time 4 http://127.0.0.1:8000/health >/dev/null
test -s /root/central-ai-backups/release-preupdate-20261101/central-ai-rollback-image.tar
test -s /root/central-ai-backups/release-preupdate-20261101/production-code.tar.gz
systemctl is-active --quiet central-ai-staging.timer
echo "AI24_READ_ONLY_VPS_PREFLIGHT_PASSED"
