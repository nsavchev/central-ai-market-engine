# P0 security and reproducibility gate — 2026-11-02

Audited candidate **8b935aafa6b2f896bfcee59bec41e15dbcc7e413** (before this audit-only commit). This SHA passed 32/32 GitHub checks; no merge or rollout. The audit docs themselves advance the PR branch, so do not silently call the branch tip a frozen candidate.

## Confirmed findings

1. **BLOCK — non-reproducible Central AI Dockerfile.** `central_ai/Dockerfile` starts with `FROM python:3.12-slim` (floating tag) and installs FastAPI, Uvicorn and httpx with broad ranges (`>=`, `<`) at build time. A rebuild of the same Git SHA may select different dependencies/base layers. Require a reviewed, vetted digest-pinned base and an exact dependency lock with hashes; build and record image digest; do not deploy before reproducibility is demonstrated.
2. **BLOCK — untrusted code/host Docker trust.** Functional verifier code invokes the host Docker CLI to execute a candidate with supplied tests. Basic `--network=none`, `--read-only`, `--cap-drop=ALL` and limits are helpful but not a hardened security boundary. The host-side component needs Docker API authority. Exclude from production host; use an isolated dedicated runner with no production credentials or mounts.
3. **BLOCK — no trusted source for candidate/test artifacts.** `verified_review_pipeline.py` accepts caller-provided Markdown code recommendations, test path and image. It does not prove the test came from a separate trusted source, nor persist signed results. The code generation and correction loop is incomplete.
4. **HIGH — timeout cannot be guaranteed under Docker daemon failure.** Real timeout forced-removal CI passed, but `cleanup_unconfirmed` is a hard stop requiring operator inspection. Automated retry must never proceed on uncertain cleanup.
5. **HIGH — production Compose context differs from GitHub.** GitHub `docker-compose.central.yml` contains a managed named volume and build configuration, while operator's existing VPS deployment uses a separate `docker-compose.central.release.yml` override with external `market_engine_v0_9_central_ai_tasks` volume and pinned candidate image tag. Do not overwrite the VPS override with the repository base. Compare fully resolved Compose configs and retain backup.
6. **HIGH — stacked unmerged changes.** 253 commits and 161 changed files relative to main at audited ref. Multiple new GitHub Actions workflows increase maintenance/audit surface. Require reviewed per-file classification before any merge.
7. **LOW — CI warning.** StarletteDeprecationWarning concerning httpx / testclient is known. Fix with explicitly vetted dependency migration later, not an incidental version bump during release cutover.

## Required P0 proofs

- Exact reviewed source SHA, dependencies lock and resolved image digest, plus immutable provenance/rollback record.
- Review all altered `.github/workflows`, API/Dockerfiles/Compose, database migration gates and broker-paper boundaries.
- CI must prohibit live execution or production promotion in untrusted PR contexts.
- Isolated clean-room candidate integration test on non-production infrastructure using disposable volumes; verify no secrets, host Docker socket, persistent prod DB or production network attached.
- No build on production VPS from floating tags; no PostgreSQL migrations under Central AI-only deployment.
- Deployment remains **not authorized** until these conditions are evidenced.

**Scope rule:** P0 is documentation and release gates only. Do not add another queue, scheduler, verifier, AI-XX stage or live trade connector.
