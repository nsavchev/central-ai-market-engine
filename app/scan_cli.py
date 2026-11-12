"""Offline relative-strength CLI and explicitly synthetic two-report rehearsal.

No scheduler, network acquisition, database access, order execution or deployment.
"""
import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from app.sources import validate_source
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


def manual_scan(payload: dict, *, report_day: date, max_age_calendar_days: int) -> dict:
    """Validate operator-declared provenance; never fetch or certify vendor rights."""
    if (not isinstance(payload, dict) or set(payload) != {'schema', 'provenance', 'market'}
            or payload['schema'] != 'market-manual-input-v1'):
        raise ValueError('MANUAL_MARKET_ENVELOPE_REQUIRED')
    provenance = payload['provenance']
    if (not isinstance(provenance, dict) or set(provenance) !=
            {'source', 'origin', 'retrieved_at', 'usage_rights_confirmed'}):
        raise ValueError('MANUAL_PROVENANCE_REQUIRED')
    validate_source(provenance['source'], automated=False)
    if (provenance['usage_rights_confirmed'] is not True
            or type(provenance['origin']) is not str
            or not 1 <= len(provenance['origin'].strip()) <= 500
            or any(ord(c) < 32 for c in provenance['origin'])):
        raise ValueError('MANUAL_USAGE_RIGHTS_AND_ORIGIN_REQUIRED')
    if type(report_day) is not date or type(max_age_calendar_days) is not int or max_age_calendar_days < 0:
        raise ValueError('EXPLICIT_MANUAL_FRESHNESS_POLICY_REQUIRED')
    try:
        retrieved = datetime.fromisoformat(provenance['retrieved_at'])
    except (TypeError, ValueError) as exc:
        raise ValueError('INVALID_RETRIEVAL_TIMESTAMP') from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None or retrieved.date() > report_day:
        raise ValueError('INVALID_RETRIEVAL_TIMESTAMP')
    market = payload['market']
    # Retrieval must not predate any daily close claimed in this export.
    _reject_future_bars(market, retrieved.date())
    result = scan(market, report_day=report_day, max_age_calendar_days=max_age_calendar_days)
    return {
        'schema': 'market-manual-report-v1', 'data_mode': 'MANUAL_IMPORT',
        'report_day': report_day.isoformat(), 'max_age_calendar_days': max_age_calendar_days,
        'provenance': dict(provenance),
        'market_sha256': hashlib.sha256(json.dumps(market, sort_keys=True, separators=(',', ':'),
                                                  allow_nan=False).encode()).hexdigest(),
        'relative_strength': result,
        'real_market_data_verified': False, 'automated_acquisition': False,
        'paper_trades_executed': False, 'deployment_allowed': False,
        'limitations': ['Origin and usage rights are operator declarations, not independent verification.',
                        'Calendar-day freshness does not implement an exchange holiday calendar.'],
    }


def main():
    parser = argparse.ArgumentParser(description='Offline market scanner or synthetic two-report demo')
    parser.add_argument('input', help='Dated closes JSON, or synthetic two-report manifest')
    parser.add_argument('--output', default='scan_report.json')
    parser.add_argument('--two-daily-demo', action='store_true', help='Opt-in synthetic offline rehearsal only')
    parser.add_argument('--report-day', type=date.fromisoformat, help='Explicit as-of date for offline freshness validation')
    parser.add_argument('--max-age-calendar-days', type=int, help='Maximum calendar-day age; includes weekends and holidays')
    parser.add_argument('--manual-import', action='store_true', help='Operator-declared market export with provenance and mandatory freshness policy')
    args = parser.parse_args()
    if args.manual_import and args.two_daily_demo:
        parser.error('Choose manual import or synthetic demo')
    if args.two_daily_demo and (args.report_day is not None or args.max_age_calendar_days is not None):
        parser.error('Freshness options apply only to the offline scanner, not synthetic demos')
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    if args.manual_import:
        result = manual_scan(payload, report_day=args.report_day, max_age_calendar_days=args.max_age_calendar_days)
    else:
        result = two_daily_demo(payload, input_path.parent) if args.two_daily_demo else scan(
            payload, report_day=args.report_day, max_age_calendar_days=args.max_age_calendar_days)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Saved', args.output)


if __name__ == '__main__':
    main()
