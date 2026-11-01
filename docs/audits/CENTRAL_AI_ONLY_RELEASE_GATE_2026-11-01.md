# Central AI only: release gate and rollback (manual approval required)

Candidate: PR #106 commit `3cd854f39fa42e890b7bf46084bf593b898f1e9d`.
Do **not** deploy the full 203-commit stack with the Market Engine compose file.
The running Central AI was created under Compose project `market_engine_v0_9`
with config `/opt/central-ai/release-v1/market_engine_v0_9/docker-compose.central.yml`.
The default `docker compose` file covers only `api` and `db`.

## Do not cross these boundaries

- No `docker compose up` in the production directory without `-f docker-compose.central.yml`,
  `-p market_engine_v0_9`, and `--no-deps central-ai`.
- No `down`, `down -v`, `prune`, production Alembic, or live broker operations.
- Preserve `CENTRAL_TASK_API_ENABLED=NO` until an explicit separate authorization.
- Preserve localhost binding `127.0.0.1:8010:8010`.
- Preserve the production `.env.central` at its current path. Never publish its values or
  copy secrets into CI logs.
- `central_ai_tasks` is a named volume: do not remove it or rename the Compose project.
- The tested staging systemd service uses a different Compose project and volume;
  do not stop or recreate it as part of an API cutover.

## Required human-reviewed release gates

1. Confirm fresh production Postgres dump and isolated restore (observed 2026-11-01).
   Confirm production code tar backup and SHA-256, including `docker-compose.central.yml`.
2. Obtain actual current running image ID and retain/label it as a rollback image;
   image ID lists alone are not a complete restore mechanism.
3. Compare the effective production Docker configuration against the candidate
   **without printing environment values**; inspect labels, network, mounts,
   published ports, read-only, UID, and restart policies.
4. Build candidate from exact pinned SHA in a **separate checkout**, not by
   modifying production files. Validate API health, no-token 401, Task API 503,
   and volume permissions in an isolated container.
5. Audit secret exposure and dependencies; run all required CI checks (29/29 on
   PR #106 at time of writing), and check PR ancestry before merge.
6. Perform a dedicated Central AI service-only cutover with operator approval.
   Explicitly select the correct Compose file and project, `--no-deps`, and a
   pinned immutable image. Never rely on a mutable `:latest` tag for rollback.
7. After cutover, verify localhost /health, authorization, task API disabled,
   service logs, network binding, and unchanged API/Postgres container IDs.
8. On any failure, restore the previous Central AI image/configuration only,
   check health again, and retain relevant logs. Do not restore Postgres unless
   data loss is explicitly confirmed and a separate restoration is approved.

## Known limitations

The existing staging worker proves scheduled read-only AST analysis of registered
targets; it does not autonomously write/review/deploy code. Passing API and
workflow tests does not authorize automatic deployments or live trading.
