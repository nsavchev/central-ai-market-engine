"""Offline relative-strength CLI and explicitly synthetic two-report rehearsal.

No scheduler, network acquisition, database access, order execution or deployment.
"""
import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from app.scanner import scan
from app.macro import Event, evaluate as evaluate_macro
from app.valuation import ValuationRequest, evaluate as evaluate_valuation

_DEMO_NAME = re.compile(r'demo_[a-z0-9_]+\.json\Z')


def _fixture(directory: Path, name: str):
    """Accept plain, colocated demo JSON only; no external path, URL or symlink."""
    if type(name) is not str or _DEMO_NAME.fullmatch(name) is None:
        raise ValueError('DEMO_FIXTURE_NAME_REQUIRED')
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('DEMO_FIXTURE_UNAVAILABLE')
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _reject_future_bars(market, asof_day):
    streams = [market['benchmark'], *market['assets'], *market.get('sectors', {}).values()]
    for stream in streams:
        for bar in stream['bars']:
            if date.fromisoformat(bar['date']) > asof_day:
                raise ValueError('FUTURE_BAR_IN_REPORT')


def two_daily_demo(manifest: dict, directory: Path) -> dict:
    """Compose exactly two explicit-input demo snapshots via existing owners.

    The output proves only offline report assembly, not live feed freshness or
    that any recurring job, worker, broker, paper ledger or VPS ran.
    """
    if (not isinstance(manifest, dict) or manifest.get('schema') != 'market-two-daily-demo-input-v1'
            or manifest.get('data_mode') != 'SYNTHETIC_FIXTURE'):
        raise ValueError('SYNTHETIC_DEMO_MODE_REQUIRED')
    sessions = manifest.get('sessions')
    if not isinstance(sessions, list) or len(sessions) != 2:
        raise ValueError('EXACTLY_TWO_SESSIONS_REQUIRED')
    reports = []
    observed_times = {}
    for item in sessions:
        if not isinstance(item, dict) or item.get('slot') not in ('morning', 'evening'):
            raise ValueError('INVALID_REPORT_SLOT')
        slot = item['slot']
        if slot in observed_times:
            raise ValueError('DUPLICATE_REPORT_SLOT')
        try:
            asof = datetime.fromisoformat(item['report_asof'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('INVALID_REPORT_TIMESTAMP') from exc
        if asof.tzinfo is None or asof.utcoffset() is None:
            raise ValueError('REPORT_TIMEZONE_REQUIRED')
        observed_times[slot] = asof

        market, market_hash = _fixture(directory, item.get('market_fixture'))
        macro, macro_hash = _fixture(directory, item.get('macro_fixture'))
        valuation, valuation_hash = _fixture(directory, item.get('valuation_fixture'))
        _reject_future_bars(market, asof.date())
        relative_strength = scan(market)
        data_day = date.fromisoformat(relative_strength['as_of'])
        if date.fromisoformat(valuation['price_asof']) > asof.date():
            raise ValueError('FUTURE_VALUATION_PRICE')
        request = ValuationRequest.model_validate(valuation)
        if not {'bear', 'base', 'bull'}.issubset({s.name.lower() for s in request.scenarios}):
            raise ValueError('THREE_SCENARIOS_REQUIRED')
        macro_result = evaluate_macro([Event.model_validate(e) for e in macro['events']], asof)
        age = (asof.date() - data_day).days
        flags = ['SYNTHETIC_FIXTURE_NOT_LIVE_MARKET_DATA', 'NO_AUTOMATED_ACQUISITION_OR_TRADING']
        if age > 0:
            flags.append('MARKET_BARS_OLDER_THAN_REPORT_DAY')
        if request.symbol not in {r['symbol'] for r in relative_strength['rankings']}:
            flags.append('VALUATION_SYMBOL_NOT_IN_SCANNER_RANKINGS')
        reports.append({
            'slot': slot, 'report_asof': asof.isoformat(),
            'market_data_asof': data_day.isoformat(), 'market_data_age_calendar_days': age,
            'relative_strength': relative_strength, 'macro': macro_result,
            'valuation': evaluate_valuation(request),
            'fixture_sha256': {
                'market': market_hash, 'macro': macro_hash, 'valuation': valuation_hash,
            },
            'flags': flags,
        })
    if (observed_times.get('morning') is None or observed_times.get('evening') is None
            or observed_times['morning'].date() != observed_times['evening'].date()
            or observed_times['morning'] >= observed_times['evening']):
        raise ValueError('INVALID_TWO_DAILY_ORDER')
    return {
        'schema': 'market-two-daily-demo-report-v1',
        'data_mode': 'SYNTHETIC_OFFLINE_ONLY',
        'scheduler_executed': False, 'paper_trades_executed': False,
        'deployment_allowed': False, 'real_market_data_verified': False,
        'reports': sorted(reports, key=lambda r: r['report_asof']),
        'limitations': [
            'Both reports use only named local demo JSON fixtures; no network or brokerage connection.',
            'Price-series data may be old; fixture dates are not evidence of live market freshness.',
            'Scanner scores are heuristics; DCF inputs and macro events are illustrative.',
            'No scheduled run, paper fill, IBKR transaction, production migration or trading occurred.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description='Offline market scanner or synthetic two-report demo')
    parser.add_argument('input', help='Dated closes JSON, or synthetic two-report manifest')
    parser.add_argument('--output', default='scan_report.json')
    parser.add_argument('--two-daily-demo', action='store_true', help='Opt-in synthetic offline rehearsal only')
    args = parser.parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    result = two_daily_demo(payload, input_path.parent) if args.two_daily_demo else scan(payload)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Saved', args.output)


if __name__ == '__main__':
    main()
