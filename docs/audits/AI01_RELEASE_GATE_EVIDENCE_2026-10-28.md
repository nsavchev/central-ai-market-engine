# Central AI / Market Engine: evidence-based release gate (2026-10-28)

## Verified candidate
- PR #97 head: `2115d4e8d04a9446f1c293ef2eac3e3c0301ab51`, stacked on #96 -> #95 -> #94, with earlier draft ancestors. **No merges.**
- PR #94 and #95: each 29/29 passing CI at their recorded heads.
- PR #96 and #97: each 29/29 failing Actions workflow status at recorded heads. For checked DUP-01 run, GitHub reported `steps=null`, `logs_url=null` and downloadable logs 404 BlobNotFound; root cause unknown. Do not claim failing Python tests.
- Operator on VPS ran candidate #97 from isolated Git clone/venv: 5/5 Python tests passed, Compose config passed. Starlette TestClient deprecation warning remains.
- Isolated Docker image built; persisted task ID survived container replacement via named volume.
- Full isolated E2E passed: HTTP API -> registered target -> existing coordinator one-shot read-only source analysis -> persisted result verified in separate container. **No actual production app, database, or trading interactions.**
- Existing VPS release last seen at `d987387`; running API, central-ai and PostgreSQL healthy with backup files on host.

## Unproven or blocking (NO-GO)
1. **GitHub Actions health**: inspect UI for account/repository Actions policy, billing limits, runner provisioning and workflow annotations; obtain actionable run-level evidence, do not repeatedly rerun 29 checks without diagnosis.
2. **Full PR ancestry/reconciliation**: map source diff from main to candidate; inspect migration and security changes throughout stack; avoid independent merges.
3. **Runtime model**: the current worker is opt-in *single-pass*, not a continuously running agent; explicit task targets remain separately registered. Autonomous developer-agent orchestration, scheduled work and retry/escalation are not proven in deployment.
4. **Production database**: test Alembic is disposable `test`-only. Must author independent reviewed production migration, match full real schema, identify/disable all writers, protect default-deny paper flags, preflight rollback and lock behavior.
5. **Operations**: trusted offsite backup/restore, controlled staging, secrets review, non-root persistent volume ownership, resource bounds, audit logging and deployment rollback still require evidence.
6. **Safety**: no automatic deployment/approval, no live orders, no production DDL or data mutations before explicit human authorization.

## Single next batch (avoid duplicated effort)
- A: Diagnose **run-level** GitHub Actions failing before steps; separate infrastructure failures from test assertions.
- B: Complete source-level security and PR dependency diff against deployed `d987387`; produce one ownership and writer-path matrix.
- C: Execute isolated staging candidate with deliberate worker opt-in and restricted workspace; verify persistence, restart and negative authorization tests.
- D: Draft production migration/rollback runbook; do **not** execute it. Present approval checklist.

**Gate status:** `audit_complete=false`, `approved=false`, `deployment_allowed=false`. Paper only.
