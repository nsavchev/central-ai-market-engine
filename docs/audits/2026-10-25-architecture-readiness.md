# Central AI / Market Engine — architecture and functionality audit

Date: 2026-10-25. Scope: repository static review of `main`, README, selected application modules and the GitHub Actions results for stacked draft PR #12. **Not a VPS runtime audit, penetration test, broker connectivity test or validation of trading strategy performance.**

## Evidence and status
- Draft PR #12 at commit `be3c2af72cc5035970aaf57e0eb1fa1d5febb724`: 13/13 queried PR-triggered workflow runs completed successfully. This is **not evidence of autonomous production repair**.
- Draft PRs #2–#12 remain a stacked development sequence and are not assumed to be merged into `main`. Their test successes are separate from production readiness.
- API: `app/main.py`; storage: `app/db.py`; ingestion: `app/fundamentals_history.py`; data quality: `app/data_quality.py`; source policy: `app/sources.py`; infrastructure: `docker-compose.yml`, `app/config.py`.

## Findings (risk-ranked)

| ID | Priority | Evidence | Finding | Acceptance criterion |
| --- | --- | --- | --- | --- |
| A-01 | Critical | `app/main.py` history import + `app/fundamentals_history.py` | Financial snapshots are written after `validate_source`, but the separate `check_snapshot` data-quality gate is not enforced. | Reject blocked snapshots transactionally; preserve `validate_source`; test invalid units, periods, balance, source permissions and no partial batch commit. |
| A-02 | High | `app/main.py` IBKR ingestion | `HTTPException(502,str(e))` returns raw internal exception text. | Return a generic correlation-ID error to client, sanitized server logs; test sensitive error messages absent in response. |
| A-03 | High | `app/main.py`, `app/db.py` | Paper ledger takes hypothetical manual fills; no mark-to-market, slippage, exchange calendar, FX or realistic execution; currency/cash and quantities are stored as floating point. | Clearly label research-only; use precise accounting types; verify cash/positions/invariants with concurrent requests and realistic simulated fill assumptions before treating results as performance. |
| A-04 | High | `app/db.py`, `app/main.py` lifespan | `Base.metadata.create_all` is not schema migration/versioning; no confirmed Alembic path or PostgreSQL upgrade test. | Automated forward/rollback migration rehearsal against throwaway PostgreSQL; backed-up, reviewed production migration plan. |
| A-05 | High | `central_ai` modules on draft PR #12 | Failure -> incident -> budget -> staging -> audit runs in explicit test harness only; no demonstrated authorized end-to-end coordinator orchestration, verified patch application and deterministic rollback. | Security review and integration of coordinator with immutable incident identity, lease ownership, refusal to execute STAGED tasks, robust stop limits and audit. |
| A-06 | Medium | `app/sources.py` | SEC EDGAR is recorded official but disabled; Finviz/Investolens are reference-only. No approved ingestion path demonstrated. | Use permitted, source-specific adapters with provenance, fair access, validation and permissions. Do not bypass `validate_source`. |
| A-07 | Medium | `requirements.txt` | Ranged dependencies can resolve differently on later builds. | Lock reproducible versions and retain automated dependency/security checks. |
| A-08 | Medium | `app/config.py`, `app/main.py` | Single shared API token; no authenticated roles or throttling shown. | Role-scoped credentials, token rotation, audit of sensitive operations, request throttling. |
| A-09 | Medium | `docker-compose.yml` | API is loopback-bound (positive); DB has persistent volume and readiness healthcheck (positive). No repository proof of VPS backups/restores, runtime observability or ingress hardening. | Read-only VPS inspection; backup/restore exercise; alerts, disk/DB metrics and access review without disclosing secrets. |
| A-10 | Medium | `README.md`, scanner/valuation notes | Scanner and valuation inputs include synthetic data; strategy and valuation accuracy not independently validated. | Point-in-time licensed data, corporate actions, FX/fees, out-of-sample and walk-forward testing before performance claims. |

## Release gates
1. **Do not merge or deploy** solely because standalone CI passes; require reviewed end-to-end safety criteria.
2. **Paper-only**; no live orders, unattended patch execution, or auto-deploy.
3. Transactional source provenance and financial quality checks before any automatic data import.
4. Deterministic rollback and safety limits after restart, concurrent worker activity and expired lease.
5. Full CI on the intended merge commit, migration and rollback rehearsals, plus read-only VPS checks.
6. Record test evidence and reviewer sign-off for each gate.

## Recommended implementation order
- M1: enforce `check_snapshot` before financial history persistence, without bypassing `validate_source`.
- M2: sanitize IBKR error responses and add security regression tests.
- M3: patch FIX orchestration integration with ownership, incident, cost and stop guards, still non-executable until reviewed.
- M4: schema migrations, paper ledger precision and concurrent invariants.
- M5: data-quality provenance, backtesting methodology and VPS operational audit.

## Audit limitations
No live VPS credentials or runtime environment were used. No backend load test, security penetration test, source license review, SEC EDGAR integration test or brokerage order test was performed. Confirm findings against the actual deployed commit and infrastructure before deciding readiness.
