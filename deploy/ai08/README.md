# AI-08: explicitly opt-in staging schedule

**Not production.** This design runs the existing AI-04 supervised worker as a bounded
one-shot container on a systemd timer. It does not create new task logic, does not
start unattended until the operator enables the timer, and does not deploy code.

## Preconditions / operator review
1. Deploy an **exact pinned audited commit** into a separate checkout at
   `/opt/central-ai/staging-ai08`. Never replace the production checkout.
2. Check `docker compose -f docker-compose.ai06.yml --profile ai06 config -q`.
3. Build image using the pinned staging checkout. The image tag is only local
   staging, never assume it identifies the latest commit.
4. Initialize the staging-only named volume/task SQLite as UID 10001, using
   `PersistentTaskBridge(Path("/var/lib/central-ai/tasks.sqlite"))`, before
   starting the timer. The supervisor intentionally fails closed if DB is absent.
5. Ensure only approved *analysis target registrations* exist in staging.
   Tasks are read-only AST analysis, **not autonomous code changes**.
6. Check `systemctl cat central-ai-staging.service` to ensure no overrides.
7. Install the unit and timer only after all above checks, and explicitly
   `systemctl enable --now central-ai-staging.timer`. The repository creates
   files only; it does not install or enable them.

Timer triggers one bounded supervised job every 5 min after the previous run,
not an always-running loop; systemd does not overlap the same oneshot unit.
The existing scheduler uses a separate file lock as defense in depth.
Docker container retains read-only root, no network, nonroot UID and 256MB/0.5CPU
limits via existing AI-06 Compose profile. The task DB resides in the
`ca-ai08-staging` Compose project volume, separate from production.

## Inspect / stop
- `systemctl status central-ai-staging.timer`
- `systemctl status central-ai-staging.service`
- `journalctl -u central-ai-staging.service -n 100 --no-pager`
- `systemctl disable --now central-ai-staging.timer` stops future schedules.
- `systemctl stop central-ai-staging.service` stops an active run.
- Never use `docker compose down -v` or `docker volume prune` on production.
- Do not erase staging volume until its retention is explicitly approved.

## Gates
CI on upstream PR chain is failing independently; do not merge or activate
production. Validate this exact commit, isolated staging execution, timer
lifecycle, restart across host reboot, audit persistence, permissions, and
rollback/backup before production promotion. No live broker trading.
