# Central AI / Market Engine

Minimal working foundation: IBKR historical daily bars -> PostgreSQL -> relative performance/trend -> FastAPI; separate manual-fill internal paper ledger. **No real brokerage orders.**

## Current architecture and progress

Start with the [living architecture, ownership, decisions and task register](docs/audits/PROJECT_ARCHITECTURE_OWNERSHIP_PROGRESS_2026-10-26.md). Its filename records its creation date; the document is updated in place. The [P0–P4 focus plan](docs/audits/PROJECT_FOCUS_AND_COMPLETION_GATES_2026-11-02.md) defines the order of work; [static module/function/import and PR metadata](docs/audits/project-architecture-inventory.json) describe the exact inspected source snapshot.

Checkpoint 2026-11-04: PR #130 source `a2aee7b…` passed **33/33 workflows**; local aggregate **325 passed / 43 PostgreSQL-dependent skipped / 0 warnings**. P0-RECON classified 128 draft PRs (87 heads in ancestry, 41 outside) and restored missing IBKR error redaction and legacy paper input guards from #15/#16. The TestClient warning is fixed. Older conflicting alternatives remain on hold; FIN-QUALITY-01 and the reproduced direct-acquire retry gap P0-LEASE-01 are recorded. Next: fix that existing lease boundary before new developer-loop features. Task API stays opt-in; complete #90/VPS reconciliation and production migration remain separate open gates.

Contributors: follow [AGENTS.md](AGENTS.md), reuse the existing owner, and record every change and handoff in the living register. No second queue/AI manager or new dated master audit.

The versioned prototype examples below are historical interface documentation and limitations; they are not proof of deployed capabilities or an approved production rollout procedure.

## Prototype installation example (not a production migration)

```bash
cp .env.example .env
# Replace both secrets in .env. Never commit it.
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

The API is bound to VPS loopback only. Access through SSH tunnel (`ssh -L 8000:127.0.0.1:8000 user@vps`) or a secured HTTPS reverse proxy. Do not publicly expose IB Gateway/TWS ports. Configure UFW/SSH keys, VPS backups, TLS, and secret rotation.

## IBKR Gateway / TWS

This package does NOT install or manage IB Gateway. Install the official gateway separately, use a **paper account** and enable API socket clients. Paper IB Gateway default port often 4002; paper TWS often 7497. Confirm actual settings. Connect only over a secure private network / local host tunnel. API access, entitlements and unattended login/re-authentication may restrict data retrieval. `IBKR_HOST=host.docker.internal` assumes Gateway is on the VPS host and its API listener permits the Docker bridge; otherwise use a secure private address. Never expose the API socket publicly. Contract identification for non-US listings requires exchange, currency and sometimes primary_exchange. Historical TRADES data may not be entitled; delayed quote access does not guarantee historical data rights. Pacing limits apply.

## Example calls

```bash
export TOKEN='YOUR_API_TOKEN'
curl -X POST http://127.0.0.1:8000/ingest/ibkr -H "X-API-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"symbol":"SPY","primary_exchange":"ARCA"}'
curl -X POST http://127.0.0.1:8000/ingest/ibkr -H "X-API-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"symbol":"NVDA","primary_exchange":"NASDAQ"}'
curl -H "X-API-Token: $TOKEN" 'http://127.0.0.1:8000/analysis/NVDA?benchmark=SPY'
curl -X POST http://127.0.0.1:8000/paper/trades -H "X-API-Token: $TOKEN" -H 'Content-Type: application/json' -d '{"symbol":"NVDA","side":"BUY","quantity":2,"price":100,"fee":1}'
curl -H "X-API-Token: $TOKEN" http://127.0.0.1:8000/paper/account
```

## Tests

```bash
pip install -r requirements-test.txt 'alembic>=1.13,<2'
python -m pytest -q
```

## Explicit limitations and next milestones

- IBKR import is a synchronous blocking request; production requires background job queue, pacing control, retries, monitoring and client-ID coordination.
- Legacy manual paper fills are finite, capped at 1,000,000 per quantity/price/fee input, with at most six quantity decimals and two price/fee decimals; the legacy route stays disabled by default. The V2 Decimal path has separate checks.
- Daily TRADES bars with `useRTH=1` and `formatDate=1`; returns are price-only, not total returns. Corporate actions and FX normalization must be addressed before cross-market comparisons.
- SMA200 needs >=200 aligned observations; one year of daily bars may suffice but not always. All returns use intersecting sessions; align to a canonical market calendar in v0.3.
- Multiple listings of the same ticker are rejected as ambiguous in the analysis endpoint. Use instrument identifiers in v0.3.
- Paper fills are manually supplied hypothetical prices; no slippage model, execution delay, mark-to-market, FX, splits, or transaction taxes. Paper cash is in USD. **Never use this as an execution-quality backtest.**
- Scheduler is deliberately disabled until exchange calendars, DST handling and data freshness checks are implemented. Configure two daily runs in v0.3.
- API token is a single shared token; add accounts, role permissions, audit logs and request throttling before public deployment.
- PostgreSQL tables are initialized with create_all for prototype only; introduce Alembic migrations.
- Global market data licensing and API terms must be validated before automated use.

## v0.3 offline scanner (new)

No VPS, broker credentials, or database is required for this scanner. From the project directory:

```bash
python -m app.scan_cli data/demo_scan.json --output scan_report.json
pytest -q
```

`data/demo_scan.json` is synthetic data, **not** actual NVIDIA or SPY quotes. Replace it with properly licensed historical daily closes. Inputs must have date `YYYY-MM-DD`, positive close, unique dates. Missing or stale candidate latest dates are not ranked. The heuristic score is NOT a validated trading strategy. It does not adjust for FX, dividends, splits, market holidays, volatility, or survivorship bias. Sector comparison is only computed when sector data is present and current. This is a standalone offline scanner, not yet wired into the API or scheduler.


## v0.4: Macro & News triage (offline MVP)

Run from project root:

```bash
python -m app.macro_cli data/demo_macro.json --asof 2026-10-18T00:00:00+00:00 --output macro_report.json
pytest -q
```

Or POST authenticated JSON `{"events":[...]}` to `/macro/evaluate`.

**Limitations:** Demo data are synthetic. No Investing.com scraper, economic calendar feed,
news ingestion, FedWatch integration, historical expectation database, cross-asset reaction,
AI synthesis, or automated notification yet. `simple_directional_hint` is an intentionally
naive per-release sign, not a trading recommendation. Priority is only calculated when
a measured historical surprise standard deviation is supplied. No live orders.

## v0.5: Source Manager + Investment Fundamentals

New endpoints: authenticated `GET /sources` lists the source registry and automation permissions; authenticated `POST /fundamentals/evaluate` calculates financial ratios from **user-supplied** statements. No new network collectors or scrapers are enabled. Investolens is listed as `reference_only` and blocked from automated and manual-import endpoint impersonation. A source being listed does **not** grant access or reuse rights. Verify actual terms and permissions independently before implementing an adapter.

Offline example:

```bash
python -m app.fundamentals_cli data/demo_fundamentals.json --output fundamentals_report.json
pytest -q
```

The demo is **synthetic**, not a real company's results. Financial ratios are indicative: ROIC uses an estimated effective tax rate and ending invested capital; price multiples need date-matched share counts and market prices; EPS, total return, CAGR, fair value and DCF are not yet implemented. `capital_expenditure` must be entered as a positive outflow. Missing inputs produce `null`, not invented values. Data are not persisted to PostgreSQL yet; no UI for adding arbitrary sources and no automatic API adapter generation. Existing v0.4 limitations still apply.


## v0.6 — historical fundamentals (manual import only)

Adds `financial_snapshots` SQLAlchemy table with source, currency, fiscal period, and JSON financial payload. Import is idempotent per symbol/date/type/currency/source.

- POST `/fundamentals/history/import` with a JSON list of 1–100 `Financials` objects, requires `X-API-Token`.
- GET `/fundamentals/history/DEMO?currency=USD&source=manual&years=10`, requires token.
- Offline demo: `python -m app.history_cli data/demo_financial_history.json --database sqlite:///financial_history_demo.db --output history_report.json`

Only manually provided data is supported. Investolens, Finviz and Investing.com are NOT scraped. The history calculations include CAGR (calendar-year span), ROIC/ROE/margin trends and basic debt-to-equity / cash-flow indicators. These are descriptive metrics, not financial health verdicts.

**Deployment warning:** `create_all` creates new tables but is NOT a migration system. For a production VPS, take backups and introduce Alembic before changing existing schemas. Multiple fiscal periods per calendar year are rejected in reports; financial units, fiscal year-end, restatements, split-adjustments, point-in-time filings and FX are not harmonized. PostgreSQL integration is not exercised in automated SQLite tests.

## v0.7: Investment Valuation Agent (explicit-input FCFF DCF)

Offline demo:

```bash
python -m app.valuation_cli data/demo_valuation.json --output valuation_report.json
```

Authenticated API: `POST /valuation/evaluate` with JSON matching `data/demo_valuation.json`.

- Scenario inputs: normalized *unlevered* annual FCFF, net debt, diluted shares, explicit current share price and date, 1–20 forecast years, annual FCFF growth, discount rate, terminal growth or optional terminal FCFF exit multiple.
- Outputs: annual cash flows, enterprise/equity/share value, upside, margin of safety, price-only implied annualized return, terminal-value dependence, 3x3 sensitivity grid (configurable offsets).
- **Not automated:** FCFF normalization, historical inputs, actual price retrieval, live financial feeds, WACC derivation, scenario probability weighting, FX conversion, real trading, or price projections for arbitrary independent 3/5/10-year holding periods.
- Price-only CAGR is the annualized rate required to reach the *modeled* fair value at the end of the DCF horizon, not an empirically validated expected return. The terminal value itself is valued as of the end of the horizon and discounted to today; thus the implied CAGR is a scenario comparison metric, not a realized forecast.
- Avoid mixing fiscal-year dates, currencies, debt or share counts. A negative equity value is shown as negative, with undefined margin of safety and CAGR.
- Investolens scraping is not enabled. Any new external source requires an approved connector and usage rights.


## v0.8 Advanced Valuation Agent

Two-stage ten-year FCFF DCF, three-or-more weighted scenarios, margin-of-safety buy-below levels, terminal-value concentration alert and reverse DCF for first-five-year growth. All inputs are explicit, demo data is fictional.

```bash
python -m app.advanced_valuation_cli data/demo_advanced_valuation.json --output advanced_report.json
pytest -q
```

Scenario probabilities are subjective, not backtested probabilities. Reverse DCF is a single-parameter sensitivity, not an implied market forecast. No investment advice or broker order placement.


## v0.9 — Financial Data Quality Agent

`app/data_quality.py` offers deterministic validation and source-to-source comparison.
Run `python -m app.quality_cli data/demo_quality.json --output quality_report.json`.

**Important:** The existing v0.6 import and valuation flows are **not yet gated** by these checks.
The new validator is an independent preflight step; enforce it in ingestion pipelines before production use.
Requires explicit units, validates period/currency/balance equation, warns on old records and
missing point-in-time metadata, compares only like-for-like figures. It does not fetch vendor
data, reconcile restatements, normalize GAAP vs IFRS, or verify filing authenticity.

All included sample data are synthetic. No trading orders are placed.
