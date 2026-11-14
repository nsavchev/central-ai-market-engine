"""Offline relative-strength CLI and explicitly synthetic two-report rehearsal.

No scheduler, network acquisition, database access, order execution or deployment.
"""
import argparse
import csv
import io
import hashlib
import json
import os
import tempfile
import re
from datetime import date, datetime, timezone
from decimal import Decimal
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


def _manual_provenance(provenance):
    if (not isinstance(provenance, dict) or set(provenance) !=
            {'source', 'origin', 'retrieved_at', 'usage_rights_confirmed'}):
        raise ValueError('MANUAL_PROVENANCE_REQUIRED')
    validate_source(provenance['source'], automated=False)
    if (provenance['usage_rights_confirmed'] is not True
            or type(provenance['origin']) is not str
            or not 1 <= len(provenance['origin'].strip()) <= 500
            or any(ord(c) < 32 for c in provenance['origin'])):
        raise ValueError('MANUAL_USAGE_RIGHTS_AND_ORIGIN_REQUIRED')
    try:
        retrieved = datetime.fromisoformat(provenance['retrieved_at'])
    except (TypeError, ValueError) as exc:
        raise ValueError('INVALID_RETRIEVAL_TIMESTAMP') from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError('INVALID_RETRIEVAL_TIMESTAMP')
    return retrieved


def manual_scan(payload: dict, *, report_day: date, max_age_calendar_days: int) -> dict:
    """Validate operator-declared provenance; never fetch or certify vendor rights."""
    if (not isinstance(payload, dict) or set(payload) != {'schema', 'provenance', 'market'}
            or payload['schema'] != 'market-manual-input-v1'):
        raise ValueError('MANUAL_MARKET_ENVELOPE_REQUIRED')
    provenance = payload['provenance']
    retrieved = _manual_provenance(provenance)
    if type(report_day) is not date or type(max_age_calendar_days) is not int or max_age_calendar_days < 0:
        raise ValueError('EXPLICIT_MANUAL_FRESHNESS_POLICY_REQUIRED')
    if retrieved.date() > report_day:
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


def combined_report(payload: dict, *, max_age_calendar_days: int) -> dict:
    """Compose existing calculators; missing context remains explicitly unavailable."""
    required = {'schema', 'report_asof', 'market_input'}
    if (not isinstance(payload, dict) or not required <= set(payload)
            or set(payload) - required - {'macro', 'valuation'}
            or payload['schema'] != 'market-combined-input-v1'):
        raise ValueError('COMBINED_REPORT_ENVELOPE_REQUIRED')
    try:
        asof = datetime.fromisoformat(payload['report_asof'])
    except (TypeError, ValueError) as exc:
        raise ValueError('INVALID_REPORT_TIMESTAMP') from exc
    if asof.tzinfo is None or asof.utcoffset() is None:
        raise ValueError('REPORT_TIMEZONE_REQUIRED')
    prices = manual_scan(payload['market_input'], report_day=asof.date(),
                         max_age_calendar_days=max_age_calendar_days)
    if datetime.fromisoformat(prices['provenance']['retrieved_at']) > asof:
        raise ValueError('INPUT_RETRIEVED_AFTER_REPORT')
    sections = {'prices': {'status': 'calculated_from_supplied_inputs'},
                'macro': {'status': 'unavailable', 'reason': 'NO_MACRO_INPUT'},
                'valuation': {'status': 'unavailable', 'reason': 'NO_VALUATION_INPUT'},
                'catalysts': {'status': 'unavailable', 'reason': 'NO_CATALYST_INTEGRATION'}}
    for name in ('macro', 'valuation'):
        context = payload.get(name)
        if context is None:
            continue
        if not isinstance(context, dict) or set(context) != {'provenance', 'data'}:
            raise ValueError('CONTEXT_PROVENANCE_REQUIRED')
        retrieved = _manual_provenance(context['provenance'])
        if retrieved > asof:
            raise ValueError('INPUT_RETRIEVED_AFTER_REPORT')
        if name == 'macro':
            data = context['data']
            if not isinstance(data, dict) or set(data) != {'events'} or not isinstance(data['events'], list):
                raise ValueError('MACRO_EVENTS_REQUIRED')
            events = [Event.model_validate(e) for e in data['events']]
            if any(e.actual is not None and e.released_at > retrieved for e in events):
                raise ValueError('MACRO_ACTUAL_AFTER_RETRIEVAL')
            value = evaluate_macro(events, asof)
        else:
            request = ValuationRequest.model_validate(context['data'])
            if {scenario.name.lower() for scenario in request.scenarios} != {'bear', 'base', 'bull'}:
                raise ValueError('THREE_SCENARIOS_REQUIRED')
            price_day = date.fromisoformat(request.price_asof)
            assets = payload['market_input']['market']['assets']
            matching = [a for a in assets if a['symbol'] == request.symbol]
            if len(matching) != 1:
                raise ValueError('VALUATION_SYMBOL_MISMATCH')
            bars = matching[0]['bars']
            latest = max(bars, key=lambda bar: date.fromisoformat(bar['date']))
            if price_day != date.fromisoformat(latest['date']) or request.current_price != float(latest['close']):
                raise ValueError('VALUATION_PRICE_MISMATCH')
            value = evaluate_valuation(request)
        sections[name] = {'status': 'calculated_from_supplied_inputs', 'provenance': dict(context['provenance']),
                          'input_sha256': hashlib.sha256(json.dumps(context['data'], sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode()).hexdigest(), 'result': value}
    return dict(prices, schema='market-combined-report-v1', report_asof=asof.isoformat(),
                sections=sections, completeness='partial',
                limitations=prices['limitations'] + [
                    'No company news/catalyst integration; the report is partial.',
                    'Valuation financial units, assumptions and price currency are operator-supplied, not independently verified.'])


def two_daily_manual(manifest: dict, *, max_age_calendar_days: int) -> dict:
    """Assemble two supplied snapshots, without implying either was scheduled."""
    if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'sessions'}
            or manifest['schema'] != 'market-two-daily-manual-input-v1'):
        raise ValueError('TWO_DAILY_MANUAL_ENVELOPE_REQUIRED')
    sessions = manifest['sessions']
    if not isinstance(sessions, list) or len(sessions) != 2:
        raise ValueError('EXACTLY_TWO_SESSIONS_REQUIRED')
    reports, times = [], []
    for slot, item in zip(('morning', 'evening'), sessions):
        if (not isinstance(item, dict) or set(item) != {'slot', 'report_asof', 'input'}
                or item['slot'] != slot):
            raise ValueError('ORDERED_MORNING_EVENING_REQUIRED')
        try:
            asof = datetime.fromisoformat(item['report_asof'])
        except (TypeError, ValueError) as exc:
            raise ValueError('INVALID_REPORT_TIMESTAMP') from exc
        if asof.tzinfo is None or asof.utcoffset() is None:
            raise ValueError('REPORT_TIMEZONE_REQUIRED')
        if isinstance(item['input'], dict) and item['input'].get('schema') == 'market-combined-input-v1':
            report = combined_report(item['input'], max_age_calendar_days=max_age_calendar_days)
            if datetime.fromisoformat(report['report_asof']) != asof:
                raise ValueError('COMBINED_REPORT_TIME_MISMATCH')
        else:
            report = manual_scan(item['input'], report_day=asof.date(),
                                 max_age_calendar_days=max_age_calendar_days)
        retrieved = datetime.fromisoformat(report['provenance']['retrieved_at'])
        if retrieved > asof:
            raise ValueError('INPUT_RETRIEVED_AFTER_REPORT')
        times.append(asof)
        reports.append(dict(report, slot=slot, report_asof=asof.isoformat()))
    if (times[0].date() != times[1].date() or times[0] >= times[1]
            or times[0].utcoffset() != times[1].utcoffset()):
        raise ValueError('INVALID_TWO_DAILY_ORDER')
    first, second = reports
    if (first['relative_strength']['benchmark'] != second['relative_strength']['benchmark']
            or {r['symbol'] for r in first['relative_strength']['rankings']} !=
               {r['symbol'] for r in second['relative_strength']['rankings']}):
        raise ValueError('TWO_DAILY_UNIVERSE_MISMATCH')
    return {
        'schema': 'market-two-daily-manual-report-v1', 'data_mode': 'MANUAL_IMPORT',
        'analysis_scope': 'supplied_sections' if any('sections' in r for r in reports) else 'relative_strength_only',
        'reports': reports,
        'same_market_snapshot': first['market_sha256'] == second['market_sha256'],
        'scheduler_executed': False, 'automated_acquisition': False,
        'real_market_data_verified': False, 'paper_trades_executed': False,
        'deployment_allowed': False,
        'limitations': ['Report times and provenance are supplied, not proof of actual scheduled execution.',
                        'Repeated price snapshots do not demonstrate an intraday market update.',
                        'Macro events, catalysts and valuation scenarios are not supplied by this path.'],
    }


def _utc_now():
    return datetime.now(timezone.utc)


def _write_report(path: Path, result: dict):
    """Replace a complete JSON report atomically, keeping old output on failure."""
    content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name + '-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _nasdaq_csv(path: Path, report_day: date):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError('NASDAQ_REGULAR_CSV_REQUIRED')
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    columns = {'Date', 'Close/Last', 'Open', 'High', 'Low', 'Volume'}
    if reader.fieldnames is None or len(reader.fieldnames) != 6 or set(reader.fieldnames) != columns:
        raise ValueError('NASDAQ_COLUMNS_REQUIRED')
    prices = {}
    missing_volume = 0
    for row in reader:
        if len(prices) >= 20_000 or set(row) != columns or any(v is None for v in row.values()):
            raise ValueError('INVALID_NASDAQ_ROW')
        day = datetime.strptime(row['Date'], '%m/%d/%Y').date()
        if day in prices or day > report_day:
            raise ValueError('DUPLICATE_OR_FUTURE_NASDAQ_DATE')
        values = {}
        for name in ('Close/Last', 'Open', 'High', 'Low', 'Volume'):
            text = row[name].strip()
            if name == 'Volume' and text in ('N/A', ''):
                values[name] = None
                missing_volume += 1
                continue
            if name != 'Volume' and text.startswith('$'):
                text = text[1:]
            if re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?', text) is None:
                raise ValueError('INVALID_NASDAQ_NUMBER')
            value = Decimal(text.replace(',', ''))
            if not value.is_finite() or value < 0 or (name != 'Volume' and value == 0):
                raise ValueError('INVALID_NASDAQ_NUMBER')
            values[name] = value
        if ((values['Volume'] is not None and values['Volume'] != values['Volume'].to_integral_value())
                or not values['Low'] <= values['Open'] <= values['High']
                or not values['Low'] <= values['Close/Last'] <= values['High']):
            raise ValueError('INCONSISTENT_NASDAQ_OHLCV')
        prices[day] = float(values['Close/Last'])
    if not prices:
        raise ValueError('EMPTY_NASDAQ_CSV')
    return prices, hashlib.sha256(raw).hexdigest(), missing_volume


def prepare_nasdaq_input(benchmark_file: Path, asset_file: Path, *, benchmark_symbol: str,
                         asset_symbol: str, max_age_calendar_days: int, confirmed: bool) -> dict:
    """Prepare a new staged manual envelope; never install it or touch a service."""
    if confirmed is not True:
        raise ValueError('CONFIRM_MANUAL_USE_REQUIRED')
    for symbol in (benchmark_symbol, asset_symbol):
        if type(symbol) is not str or re.fullmatch(r'[A-Za-z0-9._-]{1,32}', symbol) is None:
            raise ValueError('EXPLICIT_SYMBOL_REQUIRED')
    if benchmark_symbol.upper() == asset_symbol.upper() or benchmark_file.resolve() == asset_file.resolve():
        raise ValueError('DISTINCT_BENCHMARK_AND_ASSET_REQUIRED')
    now = _utc_now()
    benchmark, benchmark_hash, benchmark_missing_volume = _nasdaq_csv(benchmark_file, now.date())
    asset, asset_hash, asset_missing_volume = _nasdaq_csv(asset_file, now.date())
    if benchmark.keys() != asset.keys():
        raise ValueError('NASDAQ_SESSION_SETS_MUST_MATCH')
    def stream(symbol, values):
        return {'symbol': symbol.upper(), 'bars': [
            {'date': str(day), 'close': value} for day, value in sorted(values.items())]}
    payload = {'schema': 'market-combined-input-v1', 'report_asof': now.isoformat(),
        'market_input': {'schema': 'market-manual-input-v1', 'provenance': {
            'source': 'manual', 'usage_rights_confirmed': True,
            'retrieved_at': now.isoformat(),
            'origin': 'Operator-supplied Nasdaq CSV; benchmark SHA256=' + benchmark_hash
                + '; asset SHA256=' + asset_hash
                + '; retrieved_at is local receipt/conversion time; vendor download time and adjustment basis unverified.'
                + f'; missing volume rows (unused by price scanner): benchmark={benchmark_missing_volume}, asset={asset_missing_volume}.'},
            'market': {'benchmark': stream(benchmark_symbol, benchmark),
                       'assets': [stream(asset_symbol, asset)]}}}
    combined_report(payload, max_age_calendar_days=max_age_calendar_days)
    return payload


def report_summary(report: dict) -> str:
    """Read-only view; file contents never establish service/timer health."""
    if not isinstance(report, dict) or report.get('schema') != 'market-combined-report-v1':
        raise ValueError('COMBINED_REPORT_REQUIRED')
    market = report['relative_strength']
    age = (_utc_now().date() - date.fromisoformat(market['as_of'])).days
    limit = report['max_age_calendar_days']
    if age < 0 or type(limit) is not int or limit < 0:
        raise ValueError('INVALID_REPORT_FRESHNESS')
    lines = ['Generated: ' + report['report_asof'], 'Prices as of: ' + market['as_of'],
             f'Current price age: {age} calendar days; allowed: {limit}',
             'STALE MARKET DATA' if age > limit else 'Within declared calendar-day age limit',
             'Completeness: ' + report['completeness'],
             'Benchmark: ' + market['benchmark'] + ' / ' + market['benchmark_trend']]
    for item in market['rankings']:
        lines.append(item['symbol'] + ': ' + item['status'] + ' / ' + item.get('trend', 'unavailable'))
        for period, value in item.get('relative_performance_pp', {}).items():
            lines.append(f'  {period} sessions vs benchmark: ' + ('unavailable' if value is None else f'{value:+.4f} pp'))
    for name in ('macro', 'valuation', 'catalysts'):
        lines.append(name + ': ' + report['sections'][name]['status'])
    lines.append('File view only; service/timer state and vendor data are not independently verified.')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Offline market scanner or synthetic two-report demo')
    parser.add_argument('input', help='Dated closes JSON, or synthetic two-report manifest')
    parser.add_argument('--output', default='scan_report.json')
    parser.add_argument('--two-daily-demo', action='store_true', help='Opt-in synthetic offline rehearsal only')
    parser.add_argument('--report-day', type=date.fromisoformat, help='Explicit as-of date for offline freshness validation')
    parser.add_argument('--max-age-calendar-days', type=int, help='Maximum calendar-day age; includes weekends and holidays')
    parser.add_argument('--manual-import', action='store_true', help='Operator-declared market export with provenance and mandatory freshness policy')
    parser.add_argument('--two-daily-manual', action='store_true', help='Assemble two operator-supplied snapshots; does not schedule execution')
    parser.add_argument('--combined-report', action='store_true', help='Compose supplied manual market/macro/valuation inputs; missing sections remain unavailable')
    parser.add_argument('--report-asof-now', action='store_true', help='Combined reports only: use actual UTC execution time for freshness checks')
    parser.add_argument('--prepare-nasdaq-input', action='store_true', help='Prepare a new staged input from operator-supplied Nasdaq CSVs; no installation')
    parser.add_argument('--asset-csv', type=Path)
    parser.add_argument('--asset-symbol')
    parser.add_argument('--benchmark-symbol')
    parser.add_argument('--confirm-manual-use', action='store_true')
    parser.add_argument('--show-report', action='store_true', help='Read-only summary of an existing combined report')
    args = parser.parse_args()
    if sum((args.prepare_nasdaq_input, args.show_report, args.combined_report, args.manual_import, args.two_daily_demo, args.two_daily_manual)) > 1:
        parser.error('Choose exactly one report/input mode')
    if (args.asset_csv or args.asset_symbol or args.benchmark_symbol or args.confirm_manual_use) and not args.prepare_nasdaq_input:
        parser.error('CSV options require prepare-nasdaq-input mode')
    if args.prepare_nasdaq_input and (args.report_day is not None or args.report_asof_now):
        parser.error('CSV preparation uses actual receipt time')
    if args.report_asof_now and not args.combined_report:
        parser.error('Current-time execution requires combined-report mode')
    if args.combined_report and (args.manual_import or args.two_daily_demo or args.two_daily_manual or args.report_day is not None):
        parser.error('Combined report uses its own timestamp and cannot combine with other modes')
    if args.two_daily_manual and (args.manual_import or args.two_daily_demo or args.report_day is not None):
        parser.error('Two-daily manual mode uses its own report timestamps and cannot be combined with other modes')
    if args.manual_import and args.two_daily_demo:
        parser.error('Choose manual import or synthetic demo')
    if args.two_daily_demo and (args.report_day is not None or args.max_age_calendar_days is not None):
        parser.error('Freshness options apply only to the offline scanner, not synthetic demos')
    input_path = Path(args.input)
    if args.prepare_nasdaq_input:
        if args.asset_csv is None or args.asset_symbol is None:
            parser.error('Both asset-csv and asset-symbol are required')
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise ValueError('STAGED_OUTPUT_MUST_BE_NEW')
        payload = prepare_nasdaq_input(input_path, args.asset_csv, benchmark_symbol=args.benchmark_symbol or 'SPY',
            asset_symbol=args.asset_symbol, max_age_calendar_days=args.max_age_calendar_days, confirmed=args.confirm_manual_use)
        _write_report(output, payload)
        print('Staged input saved; not installed:', args.output)
        return
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    if args.show_report:
        print(report_summary(payload))
        return
    if args.combined_report:
        original_asof = None
        if args.report_asof_now:
            original_asof = payload['report_asof']
            declared = datetime.fromisoformat(original_asof)
            now = _utc_now()
            if declared.tzinfo is None or declared.utcoffset() is None or declared > now:
                raise ValueError('INVALID_DECLARED_REPORT_TIME')
            payload = dict(payload, report_asof=now.isoformat())
        result = combined_report(payload, max_age_calendar_days=args.max_age_calendar_days)
        if args.report_asof_now:
            result['input_report_asof'] = original_asof
            result['execution_clock_mode'] = 'current_utc'
            result['market_data_age_calendar_days'] = (now.date() - date.fromisoformat(result['relative_strength']['as_of'])).days
    elif args.two_daily_manual:
        result = two_daily_manual(payload, max_age_calendar_days=args.max_age_calendar_days)
    elif args.manual_import:
        result = manual_scan(payload, report_day=args.report_day, max_age_calendar_days=args.max_age_calendar_days)
    else:
        result = two_daily_demo(payload, input_path.parent) if args.two_daily_demo else scan(
            payload, report_day=args.report_day, max_age_calendar_days=args.max_age_calendar_days)
    if Path(args.output).resolve() == input_path.resolve():
        raise ValueError('OUTPUT_MUST_NOT_REPLACE_INPUT')
    _write_report(Path(args.output), result)
    print('Saved', args.output)


if __name__ == '__main__':
    main()
