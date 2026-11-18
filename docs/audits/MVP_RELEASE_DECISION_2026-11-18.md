# Central AI / Market Engine — MVP release decision, 2026-11-18

**Decision: GO — controlled offline/synthetic demonstration only. NO-GO — productive autonomy, real scheduled market reports, production migrations and live trading.** This is a bounded demonstration of selected components, not completion of the full self-governing trading/analysis project.

## Evidence separation

- **GitHub/source:** PR [#130](https://github.com/nsavchev/central-ai-market-engine/pull/130) remains open, draft and unmerged. Accepted installed runtime source `a1ffdd715e7f6fec343886eb812a89bf45485078` passed **33/33 CI workflows**. The previous documentation checkpoint `3eee7b633ba473595e931d2d86452e19d9854a5f` also passed **33/33**. Any new documentation-only commit has its own CI status.
- **Operator-reported VPS:** the operator supplied successful sanitized terminal acceptance markers on 18 November. This is not direct remote access by the author, and source CI does not substitute for installed-host proof.
- **Privacy:** original host receipts, protected environment, private paths and raw logs are retained outside the public source repository.

## Accepted results and strict limits

| Component | Accepted evidence | Decision |
|---|---|---|
| Central AI supervised installed idle | Real one-time systemd start, return code 0 in **3.377 seconds**; `cycles=1`, `processed=0`, `review_state=idle`. Unique start-ticket consumed. | **GO for installed idle-path acceptance only** |
| Central AI protected state | After test, service inactive, guard `NO`, `execution_authorized=false`, timer disabled, temporary overrides removed. Existing DB/key/journal/admissions unchanged; reported application accounting **2/3**. | **GO — disabled/fail-closed state preserved** |
| Central AI productive generation | The installed run did **not** execute a fresh task or use a provider credential; isolation/signal/cleanup scenarios are separately tested and bounded. | **NO-GO for unattended productive work** |
| Market Engine combined report | Operator marker `CAI_MARKET_COMBINED_DEMO_ACCEPTED`; **2 single combined CLI runs + 1 two-daily combined CLI**, producing **2 reports**. Synthetic macro/DCF valuation calculated, negative-rights input rejected. | **GO for offline reproducible demonstration** |
| Market report completeness | Catalyst integration `unavailable`; **same market snapshot reused** morning/evening. Synthetic manual fixture: source market date **2025-07-29**, both report dates **2025-08-01**. | **Partial analysis — not real-time intelligence** |
| Data, scheduling and trading | `automated_acquisition=false`, `real_market_data_verified=false`, `scheduler_executed=false`, `paper_trades_executed=false`, `deployment_allowed=false`, `provider_request_sent=false`. | **NO-GO for live feeds, twice-daily automatic reports or orders** |
| Paper API and production PostgreSQL | Source/CI tests exist. Earlier operator PostgreSQL baseline had five empty tables and a limited disposable restore; roles/ACL, all constraints, populated restore/rollback and writers remain unconfirmed. | **NO-GO for production schema change and trading activation** |

**Exact demo output:** SHA256 `fc91e82a4b38ced29d2e8ece2090451aad6af35e7375c7c8f32cf2c0bd3fb52c`. This checksum identifies the synthetic demo output; it is not evidence of real vendor prices or independently verified rights. The observed service was `static/inactive` (not active), and its timer was `disabled/inactive`. Protected Central AI files and standing units were reported unchanged by the Market test.

## Remaining release gates (ordered)

1. **P0-OPS-RECON-01 / [Issue #90](https://github.com/nsavchev/central-ai-market-engine/issues/90): OPEN.** Gather fresh read-only effective stack/source/Compose and PostgreSQL catalog, ownership/roles/ACL/indexes/defaults/sequences/writers/Alembic identity. Verify backup-and-restore equivalence on disposable restored copies, including populated data and rollback. Do not infer this from earlier empty-table matching.
2. **Market Engine data rights/freshness and scheduling:** explicitly authorize a specific source or manual export; verify timestamps, adjustment basis, exchange-calendar freshness and usage rights. Separately prove real twice-daily bounded service/timer behavior, failure semantics and rollback; no invented catalysts/assumptions.
3. **Central AI productive bounded workflow:** separately define and approve exact task, policy/grant, verified image/harness, credential route and budget; measure true task stop/cleanup and restart barriers before any standing activation. Empty idle success does not authorize paid execution.
4. **P4 release governance:** reconcile installed source vs draft PR stack, review broad diff and require separate explicit sign-off before merge, DB migration, service/timer activation, third-party account use or real trading.

## Handoff and exclusions

The **current supported deliverable** is a repeatable offline demonstration with separately accepted installed CAI idle behavior and source-level paper safety checks. It is **not** a deployable autonomous investor. Keep the existing service disabled, timer off, paper-only mode, and no real orders. Do not repeat successful one-time idle or synthetic-demo acceptance; no automatic additional provider request, budget reset, DB restore or OS upgrade is part of release acceptance. Security updates and host reboot require a separate controlled maintenance/rollback plan.

The living [architecture register](PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md) and [P0–P4 focus plan](PROJECT_FOCUS_AND_COMPLETION_GATES_2026-11-02.md) remain authoritative for next tasks. This is a one-time release decision record, not a duplicate master register or operational command.
