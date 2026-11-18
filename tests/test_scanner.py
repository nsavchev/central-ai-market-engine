from datetime import date, timedelta, timezone
import pytest
from app.scanner import scan

def bars(start, n, initial, growth=0):
    return [{'date':(date(2025,1,1)+timedelta(days=i)).isoformat(), 'close':initial+i*growth} for i in range(start,start+n)]

def test_stronger_asset_ranks_first():
    data={'benchmark':{'symbol':'SPY','bars':bars(0,210,100,0)},'assets':[
        {'symbol':'FLAT','bars':bars(0,210,100,0)},
        {'symbol':'STRONG','bars':bars(0,210,100,1)}]}
    r=scan(data)
    assert r['rankings'][0]['symbol']=='STRONG'
    assert r['rankings'][0]['relative_performance_pp']['20']>0
    assert r['rankings'][1]['relative_performance_pp']['20']==0

def test_stale_asset_is_not_ranked():
    data={'benchmark':{'symbol':'SPY','bars':bars(0,210,100)},'assets':[{'symbol':'OLD','bars':bars(0,209,100)}]}
    assert scan(data)['rankings'][0]['status']=='STALE'
    assert scan(data)['rankings'][0].get('score') is None

def test_short_history_unranked():
    data={'benchmark':{'symbol':'SPY','bars':bars(0,40,100)},'assets':[{'symbol':'NEW','bars':bars(0,40,100)}]}
    assert scan(data)['rankings'][0]['status']=='INSUFFICIENT_DATA'

def test_duplicate_date_rejected():
    d=bars(0,2,100)
    data={'benchmark':{'symbol':'SPY','bars':d+d[:1]},'assets':[]}
    with pytest.raises(ValueError): scan(data)

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from app.scan_cli import main as scanner_cli_main, two_daily_demo
from app.scanner import scan


def _synthetic_two_report_fixture(tmp_path):
    days = [date(2026, 4, 1) + timedelta(days=i) for i in range(201)]
    benchmark = [{'date': day.isoformat(), 'close': 100} for day in days]
    stronger = [{'date': day.isoformat(), 'close': 100 + i} for i, day in enumerate(days)]
    market = {'benchmark': {'symbol': 'SPY', 'bars': benchmark},
              'assets': [{'symbol': 'STRONG', 'bars': stronger}]}
    macro = {'events': [{
        'event_id': 'synthetic-release', 'indicator': 'CPI_YOY', 'country': 'US',
        'released_at': '2026-11-10T10:30:00+00:00', 'consensus_asof': '2026-11-09T10:00:00+00:00',
        'actual': 3.2, 'consensus': 3.0, 'historical_surprise_std': 0.2,
        'unit': 'percent_yoy', 'source_url': 'https://example.org/synthetic',
    }]}
    valuation = {
        'symbol': 'STRONG', 'currency': 'USD', 'base_fcff': 100000,
        'net_debt': 0, 'diluted_shares': 10000, 'current_price': 10,
        'price_asof': '2026-10-18',
        'scenarios': [
            {'name': 'bear', 'growth_rate': 0.01, 'discount_rate': 0.13,
             'terminal_growth_rate': 0.015, 'years': 5},
            {'name': 'base', 'growth_rate': 0.05, 'discount_rate': 0.10,
             'terminal_growth_rate': 0.025, 'years': 5},
            {'name': 'bull', 'growth_rate': 0.12, 'discount_rate': 0.09,
             'terminal_growth_rate': 0.03, 'years': 5},
        ],
    }
    for name, data in [('demo_scan.json', market), ('demo_macro.json', macro),
                       ('demo_valuation.json', valuation)]:
        (tmp_path / name).write_text(json.dumps(data), encoding='utf-8')
    manifest = {
        'schema': 'market-two-daily-demo-input-v1', 'data_mode': 'SYNTHETIC_FIXTURE',
        'sessions': [
            {'slot': 'evening', 'report_asof': '2026-11-10T17:00:00+02:00',
             'market_fixture': 'demo_scan.json', 'macro_fixture': 'demo_macro.json',
             'valuation_fixture': 'demo_valuation.json'},
            {'slot': 'morning', 'report_asof': '2026-11-10T09:00:00+02:00',
             'market_fixture': 'demo_scan.json', 'macro_fixture': 'demo_macro.json',
             'valuation_fixture': 'demo_valuation.json'},
        ],
    }
    return manifest


def test_two_daily_demo_reuses_scanner_macro_valuation_without_real_actions(tmp_path):
    manifest = _synthetic_two_report_fixture(tmp_path)
    output = two_daily_demo(manifest, tmp_path)
    assert output['schema'] == 'market-two-daily-demo-report-v1'
    assert output['data_mode'] == 'SYNTHETIC_OFFLINE_ONLY'
    assert output['scheduler_executed'] is output['paper_trades_executed'] is False
    assert output['deployment_allowed'] is output['real_market_data_verified'] is False
    morning, evening = output['reports']
    assert [morning['slot'], evening['slot']] == ['morning', 'evening']
    assert morning['relative_strength']['rankings'][0]['symbol'] == 'STRONG'
    assert morning['relative_strength']['rankings'][0]['relative_performance_pp']['20'] > 0
    assert morning['valuation']['data_mode'] == 'EXPLICIT_INPUT_ONLY'
    assert {s['scenario'] for s in morning['valuation']['scenarios']} == {'bear', 'base', 'bull'}
    assert morning['macro']['events'][0]['status'] == 'upcoming'
    assert morning['macro']['events'][0]['actual'] is None
    assert evening['macro']['events'][0]['status'] == 'released'
    assert evening['macro']['events'][0]['actual'] == 3.2
    assert morning['market_data_age_calendar_days'] > 0
    assert 'MARKET_BARS_OLDER_THAN_REPORT_DAY' in morning['flags']
    assert all(len(value) == 64 for value in morning['fixture_sha256'].values())
    assert morning['fixture_sha256'] == evening['fixture_sha256']


@pytest.mark.parametrize('mutation,reason', [
    (lambda m: m.update(data_mode='LIVE'), 'SYNTHETIC_DEMO_MODE_REQUIRED'),
    (lambda m: m['sessions'].pop(), 'EXACTLY_TWO_SESSIONS_REQUIRED'),
    (lambda m: m['sessions'][0].update(slot='morning'), 'DUPLICATE_REPORT_SLOT'),
    (lambda m: m['sessions'][0].update(report_asof='2026-11-10T17:00:00'), 'REPORT_TIMEZONE_REQUIRED'),
    (lambda m: m['sessions'][0].update(market_fixture='../secret.json'), 'DEMO_FIXTURE_NAME_REQUIRED'),
    (lambda m: m['sessions'][0].update(report_asof='2026-11-09T17:00:00+02:00'), 'INVALID_TWO_DAILY_ORDER'),
])
def test_two_daily_demo_rejects_untrusted_mode_paths_or_dates(tmp_path, mutation, reason):
    manifest = _synthetic_two_report_fixture(tmp_path)
    mutation(manifest)
    with pytest.raises(ValueError, match=reason):
        two_daily_demo(manifest, tmp_path)


def test_two_daily_demo_rejects_future_market_data(tmp_path):
    manifest = _synthetic_two_report_fixture(tmp_path)
    source = tmp_path / 'demo_scan.json'
    market = json.loads(source.read_text())
    market['benchmark']['bars'].append({'date': '2026-11-11', 'close': 101})
    source.write_text(json.dumps(market))
    with pytest.raises(ValueError, match='FUTURE_BAR_IN_REPORT'):
        two_daily_demo(manifest, tmp_path)


def test_two_daily_demo_rejects_symlink_fixture(tmp_path):
    manifest = _synthetic_two_report_fixture(tmp_path)
    scan_file = tmp_path / 'demo_scan.json'
    scan_file.rename(tmp_path / 'actual.json')
    scan_file.symlink_to(tmp_path / 'actual.json')
    with pytest.raises(ValueError, match='DEMO_FIXTURE_UNAVAILABLE'):
        two_daily_demo(manifest, tmp_path)


def test_two_daily_demo_rejects_missing_bear_base_bull(tmp_path):
    manifest = _synthetic_two_report_fixture(tmp_path)
    source = tmp_path / 'demo_valuation.json'
    valuation = json.loads(source.read_text())
    valuation['scenarios'].pop()
    source.write_text(json.dumps(valuation))
    with pytest.raises(ValueError, match='THREE_SCENARIOS_REQUIRED'):
        two_daily_demo(manifest, tmp_path)


def test_scan_cli_default_unchanged(tmp_path, monkeypatch):
    manifest = _synthetic_two_report_fixture(tmp_path)
    source = tmp_path / 'demo_scan.json'
    output = tmp_path / 'result.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--output', str(output)])
    scanner_cli_main()
    expected = scan(json.loads(source.read_text()))
    assert json.loads(output.read_text()) == expected
    assert 'reports' not in expected


def test_two_daily_cli_explicitly_opted_in(tmp_path, monkeypatch):
    manifest = _synthetic_two_report_fixture(tmp_path)
    source = tmp_path / 'demo_two_daily_reports.json'
    source.write_text(json.dumps(manifest))
    output = tmp_path / 'two.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--two-daily-demo', '--output', str(output)])
    scanner_cli_main()
    result = json.loads(output.read_text())
    assert len(result['reports']) == 2
    assert result['scheduler_executed'] is False


@pytest.mark.parametrize('age,limit,accepted', [(2, 2, True), (3, 2, False), (0, 0, True)])
def test_explicit_market_freshness_boundary(age, limit, accepted):
    data = {'benchmark': {'symbol': 'SPY', 'bars': bars(0, 210, 100)}, 'assets': []}
    report_day = date.fromisoformat(data['benchmark']['bars'][-1]['date']) + timedelta(days=age)
    if accepted:
        assert scan(data, report_day=report_day, max_age_calendar_days=limit) == scan(data)
    else:
        with pytest.raises(ValueError, match='STALE_MARKET_DATA'):
            scan(data, report_day=report_day, max_age_calendar_days=limit)


@pytest.mark.parametrize('day,limit', [(date(2025, 8, 1), None), (None, 2),
                                     (date(2025, 8, 1), True), (date(2025, 8, 1), -1)])
def test_reject_incomplete_or_invalid_freshness_policy(day, limit):
    with pytest.raises(ValueError, match='FRESHNESS'):
        scan({}, report_day=day, max_age_calendar_days=limit)


@pytest.mark.parametrize('stream', ['benchmark', 'asset', 'sector'])
def test_freshness_rejects_future_bars_in_any_stream(stream):
    data = {'benchmark': {'symbol': 'SPY', 'bars': bars(0, 210, 100)},
            'assets': [{'symbol': 'A', 'bars': bars(0, 210, 100)}],
            'sectors': {'tech': {'bars': bars(0, 210, 100)}}}
    rows = (data['benchmark']['bars'] if stream == 'benchmark' else
            data['assets'][0]['bars'] if stream == 'asset' else data['sectors']['tech']['bars'])
    rows.append({'date': '2025-08-02', 'close': 100})
    with pytest.raises(ValueError, match='FUTURE_MARKET_BAR'):
        scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)


def test_scan_cli_rejects_stale_input_without_output(tmp_path, monkeypatch):
    source = tmp_path / 'market.json'
    source.write_text(json.dumps({'benchmark': {'symbol': 'SPY', 'bars': bars(0, 210, 100)}, 'assets': []}))
    output = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--output', str(output),
                                   '--report-day', '2026-11-12', '--max-age-calendar-days', '3'])
    with pytest.raises(ValueError, match='STALE_MARKET_DATA'):
        scanner_cli_main()
    assert not output.exists()


def manual_market_input():
    return {'schema': 'market-manual-input-v1', 'provenance': {
        'source': 'manual', 'origin': 'Synthetic test export, not real vendor data',
        'retrieved_at': '2025-08-01T12:00:00+00:00', 'usage_rights_confirmed': True},
        'market': {'benchmark': {'symbol': 'SPY', 'bars': bars(0, 210, 100)}, 'assets': []}}


def test_manual_import_binds_provenance_and_prices():
    from app.scan_cli import manual_scan
    data = manual_market_input()
    result = manual_scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)
    assert result['relative_strength'] == scan(data['market'])
    assert result['provenance'] == data['provenance']
    assert not result['real_market_data_verified']
    assert not result['automated_acquisition']
    assert not result['paper_trades_executed']
    digest = result['market_sha256']
    data['market']['benchmark']['bars'][0]['close'] += 1
    assert manual_scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)['market_sha256'] != digest


@pytest.mark.parametrize('field,value', [('usage_rights_confirmed', False), ('usage_rights_confirmed', 1),
    ('origin', ''), ('origin', 'a\nb'), ('retrieved_at', '2025-08-01'),
    ('retrieved_at', '2025-08-02T00:00:00Z'), ('retrieved_at', 'invalid')])
def test_manual_import_rejects_invalid_provenance(field, value):
    from app.scan_cli import manual_scan
    data = manual_market_input()
    data['provenance'][field] = value
    with pytest.raises(ValueError):
        manual_scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)


def test_manual_import_requires_freshness_and_rejects_old_export():
    from app.scan_cli import manual_scan
    for day, limit in [(None, None), (date(2026, 11, 12), 3)]:
        with pytest.raises(ValueError):
            manual_scan(manual_market_input(), report_day=day, max_age_calendar_days=limit)


def test_manual_import_rejects_unauthorized_source():
    from app.scan_cli import manual_scan
    data = manual_market_input()
    data['provenance']['source'] = 'finviz'
    with pytest.raises(PermissionError):
        manual_scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)


def test_manual_cli_writes_provenance_report(tmp_path, monkeypatch):
    source = tmp_path / 'export.json'; source.write_text(json.dumps(manual_market_input()))
    output = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--manual-import', '--report-day', '2025-08-01',
                                   '--max-age-calendar-days', '5', '--output', str(output)])
    scanner_cli_main()
    result = json.loads(output.read_text())
    assert result['schema'] == 'market-manual-report-v1'
    assert len(result['market_sha256']) == 64


def test_manual_import_rejects_prices_after_retrieval():
    from app.scan_cli import manual_scan
    data = manual_market_input()
    data['provenance']['retrieved_at'] = '2025-01-02T12:00:00Z'
    with pytest.raises(ValueError, match='FUTURE_BAR_IN_REPORT'):
        manual_scan(data, report_day=date(2025, 8, 1), max_age_calendar_days=5)


@pytest.mark.parametrize('payload', [{}, {'schema': 'market-manual-input-v1', 'provenance': {}, 'market': {}, 'extra': True}])
def test_manual_import_rejects_incomplete_or_unknown_envelope(payload):
    from app.scan_cli import manual_scan
    with pytest.raises(ValueError, match='MANUAL_MARKET_ENVELOPE_REQUIRED'):
        manual_scan(payload, report_day=date(2025, 8, 1), max_age_calendar_days=5)


def manual_two_report_input():
    return {'schema': 'market-two-daily-manual-input-v1', 'sessions': [
        {'slot': 'morning', 'report_asof': '2025-08-01T13:00:00Z', 'input': manual_market_input()},
        {'slot': 'evening', 'report_asof': '2025-08-01T18:00:00Z', 'input': manual_market_input()}]}


def test_manual_two_reports_reuse_scanner_and_mark_same_prices():
    from app.scan_cli import two_daily_manual
    result = two_daily_manual(manual_two_report_input(), max_age_calendar_days=5)
    assert result['same_market_snapshot'] is True
    assert [r['slot'] for r in result['reports']] == ['morning', 'evening']
    assert result['reports'][0]['relative_strength'] == scan(manual_market_input()['market'])
    assert result['scheduler_executed'] is result['automated_acquisition'] is False
    assert result['analysis_scope'] == 'relative_strength_only'


def test_manual_two_reports_distinguish_new_snapshot():
    from app.scan_cli import two_daily_manual
    data = manual_two_report_input()
    data['sessions'][1]['input']['market']['benchmark']['bars'][-1]['close'] += 1
    assert not two_daily_manual(data, max_age_calendar_days=5)['same_market_snapshot']


@pytest.mark.parametrize('timestamp', ['2025-08-01T11:00:00Z', '2025-08-01T11:00:00'])
def test_manual_two_reports_prevent_lookahead_or_naive_time(timestamp):
    from app.scan_cli import two_daily_manual
    data = manual_two_report_input(); data['sessions'][0]['report_asof'] = timestamp
    with pytest.raises(ValueError):
        two_daily_manual(data, max_age_calendar_days=5)


@pytest.mark.parametrize('change', ['missing', 'reversed', 'other_day', 'other_offset', 'other_universe', 'old', 'rights'])
def test_manual_two_reports_reject_invalid_combination(change):
    from app.scan_cli import two_daily_manual
    data = manual_two_report_input()
    if change == 'missing': data['sessions'].pop()
    elif change == 'reversed': data['sessions'].reverse()
    elif change == 'other_day': data['sessions'][1]['report_asof'] = '2025-08-02T18:00:00Z'
    elif change == 'other_offset': data['sessions'][1]['report_asof'] = '2025-08-01T20:00:00+02:00'
    elif change == 'other_universe': data['sessions'][1]['input']['market']['benchmark']['symbol'] = 'OTHER'
    elif change == 'old':
        for item in data['sessions']: item['report_asof'] = item['report_asof'].replace('2025-08-01', '2026-11-14')
    elif change == 'rights': data['sessions'][1]['input']['provenance']['usage_rights_confirmed'] = False
    with pytest.raises((ValueError, PermissionError)):
        two_daily_manual(data, max_age_calendar_days=5)


def test_manual_two_report_cli(tmp_path, monkeypatch):
    data = tmp_path / 'two.json'; data.write_text(json.dumps(manual_two_report_input()))
    out = tmp_path / 'reports.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(data), '--two-daily-manual',
                                   '--max-age-calendar-days', '5', '--output', str(out)])
    scanner_cli_main()
    assert json.loads(out.read_text())['schema'] == 'market-two-daily-manual-report-v1'


def combined_input():
    market = manual_market_input()
    market['market']['assets'] = [{'symbol': 'DEMO', 'bars': bars(0, 210, 10)}]
    return {'schema': 'market-combined-input-v1', 'report_asof': '2025-08-01T13:00:00Z', 'market_input': market}


def combined_context(data):
    return {'provenance': dict(manual_market_input()['provenance']), 'data': data}


def valuation_context():
    data = json.loads((Path(__file__).resolve().parents[1] / 'data/demo_valuation.json').read_text())
    data.update(current_price=10, price_asof=bars(0, 210, 10)[-1]['date'])
    return combined_context(data)


def test_combined_report_marks_missing_inputs_without_fabrication():
    from app.scan_cli import combined_report
    result = combined_report(combined_input(), max_age_calendar_days=5)
    assert result['completeness'] == 'partial'
    assert result['sections']['prices']['status'] == 'calculated_from_supplied_inputs'
    for name in ('macro', 'valuation', 'catalysts'):
        assert result['sections'][name]['status'] == 'unavailable'
        assert 'result' not in result['sections'][name]
    assert not result['paper_trades_executed'] and not result['deployment_allowed']


def test_combined_report_reuses_valuation_with_matched_price():
    from app.scan_cli import combined_report
    from app.valuation import ValuationRequest, evaluate
    data = combined_input(); data['valuation'] = valuation_context()
    result = combined_report(data, max_age_calendar_days=5)
    assert result['sections']['valuation']['result'] == evaluate(ValuationRequest.model_validate(data['valuation']['data']))
    assert result['sections']['macro']['status'] == 'unavailable'


def test_combined_report_upcoming_macro_has_no_actual_or_surprise():
    from app.scan_cli import combined_report
    data = combined_input()
    data['macro'] = combined_context({'events': [{'event_id': 'synthetic', 'indicator': 'CPI_YOY',
        'country': 'US', 'released_at': '2025-08-01T14:00:00Z', 'actual': None, 'consensus': 3.0,
        'unit': 'percent', 'source_url': 'https://example.org/synthetic'}]})
    result = combined_report(data, max_age_calendar_days=5)['sections']['macro']['result']['events'][0]
    assert result['status'] == 'upcoming' and result['actual'] is None and result['surprise'] is None
    data['macro']['data']['events'][0]['actual'] = 3.2
    with pytest.raises(ValueError, match='MACRO_ACTUAL_AFTER_RETRIEVAL'):
        combined_report(data, max_age_calendar_days=5)


@pytest.mark.parametrize('change', ['symbol', 'price', 'price_date', 'scenarios', 'rights', 'retrieved', 'malformed'])
def test_combined_report_rejects_inconsistent_context(change):
    from app.scan_cli import combined_report
    data = combined_input(); data['valuation'] = valuation_context()
    ctx = data['valuation']
    if change == 'symbol': ctx['data']['symbol'] = 'OTHER'
    elif change == 'price': ctx['data']['current_price'] = 999
    elif change == 'price_date': ctx['data']['price_asof'] = '2030-01-01'
    elif change == 'scenarios': ctx['data']['scenarios'].pop()
    elif change == 'rights': ctx['provenance']['usage_rights_confirmed'] = False
    elif change == 'retrieved': ctx['provenance']['retrieved_at'] = '2025-08-01T14:00:00Z'
    elif change == 'malformed': del ctx['provenance']
    with pytest.raises((ValueError, PermissionError)):
        combined_report(data, max_age_calendar_days=5)


def test_combined_report_in_two_daily_flow_keeps_sections():
    from app.scan_cli import two_daily_manual
    data = manual_two_report_input()
    for item in data['sessions']:
        item['input'] = combined_input()
        item['input']['report_asof'] = item['report_asof']
    result = two_daily_manual(data, max_age_calendar_days=5)
    assert result['analysis_scope'] == 'supplied_sections'
    assert all(r['sections']['valuation']['status'] == 'unavailable' for r in result['reports'])
    data['sessions'][1]['input']['report_asof'] = '2025-08-01T17:00:00Z'
    with pytest.raises(ValueError, match='COMBINED_REPORT_TIME_MISMATCH'):
        two_daily_manual(data, max_age_calendar_days=5)


def test_combined_cli_rejects_invalid_data_before_new_output(tmp_path, monkeypatch):
    data = combined_input(); data['macro'] = combined_context({'events': 'invalid'})
    source = tmp_path / 'combined.json'; source.write_text(json.dumps(data))
    output = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--combined-report', '--max-age-calendar-days', '5', '--output', str(output)])
    with pytest.raises(ValueError, match='MACRO_EVENTS_REQUIRED'):
        scanner_cli_main()
    assert not output.exists()


def test_combined_cli_writes_explicit_partial_report(tmp_path, monkeypatch):
    source = tmp_path / 'combined.json'; source.write_text(json.dumps(combined_input()))
    output = tmp_path / 'report.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--combined-report', '--max-age-calendar-days', '5', '--output', str(output)])
    scanner_cli_main()
    result = json.loads(output.read_text())
    assert result['schema'] == 'market-combined-report-v1'
    assert result['completeness'] == 'partial'
    assert result['sections']['catalysts']['status'] == 'unavailable'


def test_current_time_report_rechecks_age_instead_of_replaying_old_asof(tmp_path, monkeypatch):
    from app import scan_cli
    source = tmp_path / 'input.json'; source.write_text(json.dumps(combined_input()))
    output = tmp_path / 'report.json'; output.write_text('prior accepted report')
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2026-11-14T08:00:00Z'))
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--combined-report', '--report-asof-now',
                                   '--max-age-calendar-days', '3', '--output', str(output)])
    with pytest.raises(ValueError, match='STALE_MARKET_DATA'):
        scanner_cli_main()
    assert output.read_text() == 'prior accepted report'


def test_current_time_report_records_actual_time_and_original_asof(tmp_path, monkeypatch):
    from app import scan_cli
    source = tmp_path / 'input.json'; source.write_text(json.dumps(combined_input()))
    output = tmp_path / 'report.json'
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T18:00:00Z'))
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--combined-report', '--report-asof-now',
                                   '--max-age-calendar-days', '5', '--output', str(output)])
    scanner_cli_main()
    report = json.loads(output.read_text())
    assert report['report_asof'] == '2025-08-01T18:00:00+00:00'
    assert report['input_report_asof'] == '2025-08-01T13:00:00Z'
    assert report['execution_clock_mode'] == 'current_utc'
    assert report['market_data_age_calendar_days'] == 3
    assert list(tmp_path.glob('.report.json-*')) == []


def test_atomic_report_failure_preserves_previous_file(tmp_path, monkeypatch):
    from app import scan_cli
    output = tmp_path / 'report.json'; output.write_text('previous')
    def fail(*args): raise OSError('synthetic replace failure')
    monkeypatch.setattr(scan_cli.os, 'replace', fail)
    with pytest.raises(OSError): scan_cli._write_report(output, {'status': 'partial'})
    assert output.read_text() == 'previous'
    assert list(tmp_path.glob('.report.json-*')) == []


def test_current_time_flag_cannot_silently_change_demo_mode(tmp_path, monkeypatch):
    monkeypatch.setattr('sys.argv', ['scan_cli', str(tmp_path/'absent.json'), '--report-asof-now'])
    with pytest.raises(SystemExit): scanner_cli_main()


def test_cli_refuses_overwriting_its_input(tmp_path, monkeypatch):
    source = tmp_path / 'input.json'; source.write_text(json.dumps(combined_input())); before=source.read_bytes()
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--combined-report', '--max-age-calendar-days', '5', '--output', str(source)])
    with pytest.raises(ValueError, match='OUTPUT_MUST_NOT_REPLACE_INPUT'): scanner_cli_main()
    assert source.read_bytes() == before


def nasdaq_test_exports(tmp_path):
    import csv
    paths = []
    for symbol, price in [('SPY', '100.00'), ('NVDA', '10.00')]:
        path = tmp_path/(symbol+'.csv')
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Date', 'Close/Last', 'Volume', 'Open', 'High', 'Low'])
            writer.writeheader()
            for bar in reversed(bars(0, 210, 100)):
                writer.writerow({'Date': date.fromisoformat(bar['date']).strftime('%m/%d/%Y'),
                    'Close/Last': '$'+price, 'Volume': '1,000', 'Open': price, 'High': price, 'Low': price})
        paths.append(path)
    return paths


def test_nasdaq_staging_reuses_combined_validation_and_binds_original_bytes(tmp_path, monkeypatch):
    from app import scan_cli
    import hashlib
    benchmark, asset = nasdaq_test_exports(tmp_path)
    before = [p.read_bytes() for p in (benchmark, asset)]
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    data = scan_cli.prepare_nasdaq_input(benchmark, asset, benchmark_symbol='SPY', asset_symbol='NVDA', max_age_calendar_days=5, confirmed=True)
    report = scan_cli.combined_report(data, max_age_calendar_days=5)
    assert report['relative_strength']['rankings'][0]['symbol'] == 'NVDA'
    assert data['market_input']['market']['benchmark']['bars'][0]['date'] == '2025-01-01'
    for original in before:
        assert hashlib.sha256(original).hexdigest() in data['market_input']['provenance']['origin']
    assert before == [p.read_bytes() for p in (benchmark, asset)]


@pytest.mark.parametrize('field,value', [('Close/Last', 'NaN'), ('Close/Last', '-1'),
    ('Close/Last', '1$2'), ('Volume', '1.5'), ('High', '1'), ('Date', '08/02/2025')])
def test_nasdaq_staging_rejects_bad_rows(tmp_path, monkeypatch, field, value):
    import csv
    from app import scan_cli
    benchmark, asset = nasdaq_test_exports(tmp_path)
    with asset.open(encoding='utf-8-sig', newline='') as f: rows = list(csv.DictReader(f))
    rows[0][field] = value
    with asset.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    with pytest.raises(ValueError):
        scan_cli.prepare_nasdaq_input(benchmark, asset, benchmark_symbol='SPY', asset_symbol='NVDA', max_age_calendar_days=5, confirmed=True)


@pytest.mark.parametrize('case', ['duplicate', 'different_sessions', 'wrong_columns', 'unconfirmed', 'stale', 'same_symbol', 'symlink'])
def test_nasdaq_staging_rejects_unusable_pair(tmp_path, monkeypatch, case):
    import csv
    from app import scan_cli
    benchmark, asset = nasdaq_test_exports(tmp_path)
    with asset.open(encoding='utf-8-sig', newline='') as f: rows = list(csv.DictReader(f))
    if case == 'duplicate': rows.append(rows[0])
    elif case == 'different_sessions': rows.pop()
    if case in ('duplicate', 'different_sessions'):
        with asset.open('w', newline='') as f:
            writer=csv.DictWriter(f, fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    elif case == 'wrong_columns': asset.write_text('Date,Close\n01/01/2025,10\n')
    elif case == 'symlink':
        original = tmp_path/'original.csv';asset.rename(original);asset.symlink_to(original)
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2026-11-14T13:00:00Z' if case == 'stale' else '2025-08-01T13:00:00Z'))
    with pytest.raises(ValueError):
        scan_cli.prepare_nasdaq_input(benchmark, asset, benchmark_symbol='SPY',
            asset_symbol='SPY' if case == 'same_symbol' else 'NVDA', max_age_calendar_days=5, confirmed=case != 'unconfirmed')


def test_nasdaq_cli_only_creates_new_staged_file(tmp_path, monkeypatch):
    from app import scan_cli
    benchmark, asset = nasdaq_test_exports(tmp_path)
    output = tmp_path/'staged.json'
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    monkeypatch.setattr('sys.argv', ['scan_cli', str(benchmark), '--prepare-nasdaq-input', '--asset-csv', str(asset),
        '--asset-symbol', 'NVDA', '--confirm-manual-use', '--max-age-calendar-days', '5', '--output', str(output)])
    scanner_cli_main(); original=output.read_bytes()
    assert json.loads(original)['schema'] == 'market-combined-input-v1'
    with pytest.raises(ValueError, match='STAGED_OUTPUT_MUST_BE_NEW'): scanner_cli_main()
    assert output.read_bytes() == original


def test_report_summary_recomputes_current_age_without_changing_report(monkeypatch):
    from app import scan_cli
    data = scan_cli.combined_report(combined_input(), max_age_calendar_days=5)
    original = json.dumps(data, sort_keys=True)
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-08T13:00:00Z'))
    text = scan_cli.report_summary(data)
    assert 'STALE MARKET DATA' in text
    assert 'macro: unavailable' in text and 'catalysts: unavailable' in text
    assert 'service/timer state' in text
    assert json.dumps(data, sort_keys=True) == original


def test_show_report_cli_is_read_only(tmp_path, monkeypatch, capsys):
    from app import scan_cli
    data = scan_cli.combined_report(combined_input(), max_age_calendar_days=5)
    source=tmp_path/'report.json';source.write_text(json.dumps(data));before=source.read_bytes()
    output=tmp_path/'must-not-exist.json'
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    monkeypatch.setattr('sys.argv', ['scan_cli', str(source), '--show-report', '--output', str(output)])
    scanner_cli_main()
    assert 'Prices as of: 2025-07-29' in capsys.readouterr().out
    assert source.read_bytes() == before and not output.exists()


def test_nasdaq_staging_honors_revoked_manual_permission(tmp_path, monkeypatch):
    from dataclasses import replace
    from app import scan_cli
    from app.sources import SOURCES
    benchmark, asset = nasdaq_test_exports(tmp_path)
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    monkeypatch.setitem(SOURCES, 'manual', replace(SOURCES['manual'], permission_verified=False))
    with pytest.raises(PermissionError):
        scan_cli.prepare_nasdaq_input(benchmark, asset, benchmark_symbol='SPY', asset_symbol='NVDA', max_age_calendar_days=5, confirmed=True)


def test_nasdaq_missing_volume_is_recorded_without_zero_fill(tmp_path, monkeypatch):
    import csv
    from app import scan_cli
    benchmark, asset = nasdaq_test_exports(tmp_path)
    with benchmark.open(encoding='utf-8-sig', newline='') as f: rows=list(csv.DictReader(f))
    rows[0]['Volume']='N/A'
    with benchmark.open('w', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2025-08-01T13:00:00Z'))
    data=scan_cli.prepare_nasdaq_input(benchmark,asset,benchmark_symbol='SPY',asset_symbol='NVDA',max_age_calendar_days=5,confirmed=True)
    assert 'benchmark=1, asset=0' in data['market_input']['provenance']['origin']
    assert all(set(bar)=={'date','close'} for bar in data['market_input']['market']['benchmark']['bars'])


@pytest.fixture
def twelve_case(tmp_path, monkeypatch):
    import json
    from copy import deepcopy
    from app import scan_cli
    monkeypatch.setenv('MARKET_TWELVE_DATA_ENABLED', '1')
    monkeypatch.setenv('MARKET_TWELVE_DATA_PRIVATE_USE_CONFIRMED', '1')
    monkeypatch.setattr(scan_cli, '_utc_now', lambda: datetime.fromisoformat('2026-11-15T12:00:00Z'))
    key = tmp_path / 'key'
    key.write_text('K' * 32)
    key.chmod(0o600)
    bodies = {}
    for symbol in ('SPY', 'NVDA'):
        bodies[symbol] = {'meta': {'symbol': symbol, 'currency': 'USD', 'interval': '1day',
            'exchange_timezone': 'America/New_York'}, 'values': [
            {'datetime': str(date(2026, 11, 13) - timedelta(days=i)),
             'open': '100', 'high': '102', 'low': '99', 'close': '101'} for i in range(200)]}
    calls = []
    class Response:
        status = 200
        def read(self, limit):
            return json.dumps(bodies[calls[-1]['symbol'][0]]).encode()[:limit]
    class Connection:
        def __init__(self, host, timeout):
            assert host == 'api.twelvedata.com' and timeout == 20
        def request(self, method, path, headers):
            from urllib.parse import parse_qs, urlsplit
            assert method == 'GET'
            query = parse_qs(urlsplit(path).query)
            assert query['adjust'] == ['splits'] and query['prepost'] == ['false']
            calls.append(query)
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(scan_cli.http.client, 'HTTPSConnection', Connection)
    return scan_cli, key, bodies, calls, deepcopy


def test_twelve_provider_provenance_and_no_manual_masquerade(twelve_case, monkeypatch):
    cli, key, _, calls, deepcopy = twelve_case
    payload = cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert len(calls) == 2 and calls[0]['end_date'] == ['2026-11-14']
    assert payload['market_input']['schema'] == 'market-provider-input-v1'
    report = cli.combined_report(payload, max_age_calendar_days=3)
    assert report['automated_acquisition'] and report['data_mode'] == 'PROVIDER_API'
    assert not report['deployment_allowed'] and not report['paper_trades_executed']
    assert report['completeness'] == 'partial'
    assert 'not dividend total return' in report['provenance']['origin']
    assert 'K' * 32 not in str(payload)
    manual = deepcopy(payload)
    manual['market_input']['schema'] = 'market-manual-input-v1'
    with pytest.raises(PermissionError):
        cli.combined_report(manual, max_age_calendar_days=3)
    monkeypatch.delenv('MARKET_TWELVE_DATA_ENABLED')
    with pytest.raises(PermissionError):
        cli.combined_report(payload, max_age_calendar_days=3)


@pytest.mark.parametrize('missing', ['MARKET_TWELVE_DATA_ENABLED', 'MARKET_TWELVE_DATA_PRIVATE_USE_CONFIRMED'])
def test_twelve_policy_before_key_or_network(twelve_case, monkeypatch, missing):
    cli, key, _, calls, _ = twelve_case
    monkeypatch.delenv(missing)
    key.unlink()
    with pytest.raises(PermissionError):
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert not calls


@pytest.mark.parametrize('fault', ['symbol', 'currency', 'timezone', 'interval', 'duplicate',
    'future', 'nan', 'infinite', 'envelope', 'short', 'error', 'session_gap', 'stale'])
def test_twelve_rejects_invalid_pair(twelve_case, fault):
    cli, key, bodies, calls, _ = twelve_case
    body = bodies['NVDA']
    if fault == 'symbol': body['meta']['symbol'] = 'OTHER'
    if fault == 'currency': body['meta']['currency'] = 'EUR'
    if fault == 'timezone': body['meta']['exchange_timezone'] = 'Australia/Sydney'
    if fault == 'interval': body['meta']['interval'] = '1week'
    if fault == 'duplicate': body['values'][1] = body['values'][0]
    if fault == 'future': body['values'][0]['datetime'] = '2026-11-16'
    if fault == 'nan': body['values'][0]['close'] = 'NaN'
    if fault == 'infinite': body['values'][0]['high'] = 'Infinity'
    if fault == 'envelope': body['values'][0]['low'] = '200'
    if fault == 'short': body['values'] = body['values'][:120]
    if fault == 'error': bodies['NVDA'] = {'status': 'error', 'message': 'K' * 32}
    if fault == 'session_gap': body['values'].pop()
    if fault == 'stale':
        for row in body['values']:
            row['datetime'] = str(date.fromisoformat(row['datetime']) - timedelta(days=5))
    with pytest.raises(ValueError) as error:
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert 'K' * 32 not in str(error.value)
    assert len(calls) == 2


@pytest.mark.parametrize('hour,minute,expected', [(20, 9, '2026-11-15'), (21, 9, '2026-11-15'), (21, 10, '2026-11-16')])
def test_twelve_closed_session_cutoff(twelve_case, monkeypatch, hour, minute, expected):
    cli, key, _, calls, _ = twelve_case
    monkeypatch.setattr(cli, '_utc_now', lambda: datetime(2026, 11, 16, hour, minute, tzinfo=timezone.utc))
    cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert calls[0]['end_date'] == [expected]


def test_twelve_key_permissions_and_symlink_block_before_network(twelve_case, tmp_path):
    cli, key, _, calls, _ = twelve_case
    key.chmod(0o644)
    with pytest.raises(ValueError):
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    key.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(key)
    with pytest.raises(OSError):
        cli.prepare_twelve_data_input(link, max_age_calendar_days=3)
    assert not calls


def test_twelve_network_errors_are_sanitized_no_retry(twelve_case, monkeypatch):
    cli, key, _, calls, _ = twelve_case
    def fail(*args, **kwargs):
        raise RuntimeError('https://example/?apikey=' + 'K' * 32)
    monkeypatch.setattr(cli.http.client.HTTPSConnection, 'getresponse', fail)
    with pytest.raises(ValueError, match='^TWELVE_DATA_REQUEST_FAILED$'):
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert len(calls) == 1


def test_twelve_cli_failure_keeps_output_absent(twelve_case, tmp_path, monkeypatch):
    cli, key, bodies, _, _ = twelve_case
    bodies['NVDA'] = {'status': 'error'}
    output = tmp_path / 'new.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', '-', '--prepare-twelve-data-input',
        '--api-key-file', str(key), '--max-age-calendar-days', '3', '--output', str(output)])
    with pytest.raises(ValueError):
        cli.main()
    assert not output.exists()


@pytest.mark.parametrize('status,raw', [(302, b'{}'), (429, b'{}'),
    (200, b'x' * 2_000_001), (200, b'not-json'), (200, b'[]')])
def test_twelve_http_redirect_limit_and_malformed_fail_closed(twelve_case, monkeypatch, status, raw):
    cli, key, _, calls, _ = twelve_case
    class Response:
        def read(self, limit):
            assert limit == 2_000_001
            return raw
    response = Response()
    response.status = status
    monkeypatch.setattr(cli.http.client.HTTPSConnection, 'getresponse', lambda self: response)
    with pytest.raises(ValueError, match='^TWELVE_DATA_REQUEST_FAILED$'):
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    assert len(calls) == 1


def test_twelve_cli_existing_output_never_fetches_or_replaces(twelve_case, tmp_path, monkeypatch):
    cli, key, _, calls, _ = twelve_case
    output = tmp_path / 'existing.json'
    output.write_bytes(b'last valid input')
    monkeypatch.setattr('sys.argv', ['scan_cli', '-', '--prepare-twelve-data-input',
        '--api-key-file', str(key), '--max-age-calendar-days', '3', '--output', str(output)])
    with pytest.raises(ValueError, match='STAGED_OUTPUT_MUST_BE_NEW'):
        cli.main()
    assert output.read_bytes() == b'last valid input' and not calls


def test_twelve_cli_success_and_readonly_view(twelve_case, tmp_path, monkeypatch, capsys):
    import json
    cli, key, _, calls, _ = twelve_case
    output = tmp_path / 'new.json'
    monkeypatch.setattr('sys.argv', ['scan_cli', '-', '--prepare-twelve-data-input',
        '--api-key-file', str(key), '--max-age-calendar-days', '3', '--output', str(output)])
    cli.main()
    assert len(calls) == 2 and output.stat().st_mode & 0o777 == 0o600
    result = cli.combined_report(json.loads(output.read_text()), max_age_calendar_days=3)
    assert 'PROVIDER_API' in cli.report_summary(result)


@pytest.fixture
def twelve_publish_case(twelve_case, tmp_path, monkeypatch):
    import importlib.util
    import json
    import os
    import pwd
    from pathlib import Path
    cli, key, _, _, _ = twelve_case
    path = Path(__file__).resolve().parents[1] / 'deploy/market-report/twelve_data_rollout.py'
    spec = importlib.util.spec_from_file_location('twelve_rollout', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(helper, 'ROOT_UID', os.geteuid())
    # Root code trust is an installation precondition; test filesystem operations as CI UID.
    monkeypatch.setattr(helper, 'trusted', lambda path: None)
    config = tmp_path / 'config'
    state = tmp_path / 'state'
    config.mkdir()
    state.mkdir()
    old = {'schema': 'market-combined-input-v1', 'market_input': {}, 'report_asof': 'old'}
    target = config / 'input.json'
    target.write_text(json.dumps(old))
    target.chmod(0o640)
    payload = cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    pending = state / 'pending.json'
    pending.write_text(json.dumps(payload))
    def validate(command, **kwargs):
        candidate = Path(command[command.index('app.scan_cli') + 1])
        assert candidate.parent == config and candidate.stat().st_mode & 0o777 == 0o640
        data = json.loads(candidate.read_text())
        result = cli.combined_report(data, max_age_calendar_days=3)
        (state / 'preview.json').write_text(json.dumps(result))
        return ''
    account = pwd.getpwuid(os.geteuid()).pw_name
    return helper, config, state, account, payload, validate


def test_twelve_publisher_retains_metadata_and_durable_previous_input(twelve_publish_case):
    import json
    import os
    helper, config, state, account, payload, validate = twelve_publish_case
    target = config / 'input.json'
    old = target.read_bytes()
    helper.publish(config, config, account, state, config, runner=validate)
    assert json.loads(target.read_text()) == payload
    assert (config / 'input.previous.json').read_bytes() == old
    assert target.stat().st_uid == os.geteuid()
    assert target.stat().st_mode & 0o777 == 0o640
    assert not list(config.glob('.provider-check-*'))


@pytest.mark.parametrize('failure', ['validation', 'binding', 'concurrent', 'pending_swap'])
def test_twelve_publisher_failure_and_immutable_snapshot(twelve_publish_case, failure):
    import json
    helper, config, state, account, payload, validate = twelve_publish_case
    target = config / 'input.json'
    old = target.read_bytes()
    def runner(command, **kwargs):
        if failure == 'validation':
            raise ValueError('rejected by CLI')
        validate(command, **kwargs)
        if failure == 'binding':
            preview = state / 'preview.json'
            result = json.loads(preview.read_text())
            result['market_sha256'] = 'wrong'
            preview.write_text(json.dumps(result))
        if failure == 'concurrent':
            target.write_bytes(b'external authorized update')
        if failure == 'pending_swap':
            (state / 'pending.json').write_bytes(b'changed after snapshot')
    if failure == 'pending_swap':
        helper.publish(config, config, account, state, config, runner=runner)
        assert json.loads(target.read_text()) == payload
    else:
        with pytest.raises(ValueError):
            helper.publish(config, config, account, state, config, runner=runner)
        assert target.read_bytes() == (b'external authorized update' if failure == 'concurrent' else old)
        assert not (config / 'input.previous.json').exists()
    assert not list(config.glob('.provider-check-*'))


@pytest.mark.parametrize('failure', ['context', 'wrong_pair', 'symlink'])
def test_twelve_publisher_rejects_context_pair_and_symlink(twelve_publish_case, failure):
    import json
    helper, config, state, account, payload, validate = twelve_publish_case
    target = config / 'input.json'
    if failure == 'context':
        target.write_text(json.dumps({'macro': {'valuable': 'existing data'}}))
    if failure == 'wrong_pair':
        payload['market_input']['market']['assets'][0]['symbol'] = 'OTHER'
        (state / 'pending.json').write_text(json.dumps(payload))
    if failure == 'symlink':
        (state / 'pending.json').unlink()
        (state / 'pending.json').symlink_to(target)
    old = target.read_bytes()
    with pytest.raises((ValueError, OSError)):
        helper.publish(config, config, account, state, config, runner=validate)
    assert target.read_bytes() == old


def test_twelve_units_keep_credential_out_of_report_and_no_second_timer(twelve_publish_case):
    from pathlib import Path
    helper, _, _, _, _, _ = twelve_publish_case
    refresh, report = helper.units(Path('/opt/market-report/releases/reviewed'),
        Path('/opt/market-report/venv/bin/python'), 'market-report')
    assert b'LoadCredential=' in refresh and b'LoadCredential=' not in report
    assert b'RuntimeDirectory=market-report-refresh' in refresh
    assert b'stage-credential --source %d/twelve-data.key' in refresh
    assert b'--api-key-file /run/market-report-refresh/provider.key' in refresh
    assert b'ExecStopPost=/usr/bin/rm -f /run/market-report-refresh/provider.key' in refresh
    assert b'ExecStartPost=+/usr/bin/python3 -I -B' in refresh
    assert b'Requires=market-report-refresh.service' in report
    assert b'After=market-report-refresh.service' in report
    assert b'OnCalendar=' not in refresh + report
    assert b'RemainAfterExit=' not in refresh
    assert b'api-key-file' not in report
    with pytest.raises(ValueError):
        helper.units(Path('/opt/source'), Path('/usr/bin/python3'), 'bad user')


@pytest.mark.parametrize('fail_start', [False, True])
def test_twelve_rollout_restores_baseline_and_timer_on_failure_or_manual_rollback(twelve_publish_case, tmp_path, monkeypatch, fail_start):
    import hashlib
    import io
    import json
    import os
    from pathlib import Path
    import tarfile
    helper, _, _, account, _, _ = twelve_publish_case
    sandbox = tmp_path / 'installation'
    sandbox.mkdir()
    def mapped(value):
        value = str(value)
        if value == '/root' or value.startswith(('/etc/', '/opt/', '/var/')):
            return sandbox / value.lstrip('/')
        return Path(value)
    monkeypatch.setattr(helper, 'Path', mapped)
    real_atomic = helper.atomic
    monkeypatch.setattr(helper, 'atomic', lambda path, data, uid, gid, mode:
        real_atomic(path, data, uid, os.getegid() if gid == 0 else gid, mode))
    original_mkdtemp = helper.tempfile.mkdtemp
    monkeypatch.setattr(helper.tempfile, 'mkdtemp', lambda prefix, dir:
        original_mkdtemp(prefix=prefix, dir=mapped(dir)))
    service = mapped('/etc/systemd/system/market-report.service')
    timer = mapped('/etc/systemd/system/market-report.timer')
    input_file = mapped('/etc/market-report/input.json')
    report = mapped('/var/lib/market-report/latest-report.json')
    for path in (service, timer, input_file, report, mapped('/root') / 'placeholder'):
        path.parent.mkdir(parents=True, exist_ok=True)
    mapped('/opt/market-report').mkdir(parents=True)
    service.write_bytes(b'accepted original service')
    timer.write_bytes(b'OnCalendar=*-*-* 08:00:00 Europe/Sofia\nOnCalendar=*-*-* 23:15:00 Europe/Sofia\n')
    input_file.write_bytes(b'{"original":"input"}')
    input_file.chmod(0o640)
    report.write_bytes(b'{"original":"report"}')
    report.chmod(0o600)
    before = (input_file.read_bytes(), report.read_bytes(), timer.read_bytes())
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        if command[0] == 'git':
            return 'a' * 40 if command[-1] == 'HEAD' else ''
        if command[:2] == ['systemctl', 'is-enabled']: return 'enabled'
        if command[:2] == ['systemctl', 'is-active']: return 'active'
        if command[:2] == ['systemctl', 'show']: return 'inactive'
        if command == ['systemctl', 'start', 'market-report.service']:
            if fail_start:
                raise ValueError('service dependency failed')
            payload = {'market_input': {'market': {}, 'provenance': {'source': 'twelve_data'}}}
            input_file.write_text(json.dumps(payload))
            result = {'market_sha256': hashlib.sha256(b'{}').hexdigest(),
                'data_mode': 'PROVIDER_API', 'provenance': payload['market_input']['provenance'],
                'automated_acquisition': True, 'deployment_allowed': False,
                'relative_strength': {'as_of': '2026-11-13'}}
            report.write_text(json.dumps(result))
        return ''
    monkeypatch.setattr(helper, 'run', runner)
    def archive(command, stdout, check):
        assert command[-2:] == ['archive', 'a' * 40] and check
        with tarfile.open(fileobj=stdout, mode='w') as stream:
            member = tarfile.TarInfo('app/example.py')
            raw = b'# reviewed immutable source\n'
            member.size = len(raw)
            stream.addfile(member, io.BytesIO(raw))
    monkeypatch.setattr(helper.subprocess, 'run', archive)
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    args = (checkout, 'a' * 40, account, hashlib.sha256(service.read_bytes()).hexdigest())
    if fail_start:
        with pytest.raises(ValueError, match='service dependency failed'):
            helper.install(*args)
    else:
        helper.install(*args)
        audit = next(mapped('/root').glob('market-api-rollout-*'))
        assert json.loads((audit / 'receipt.json').read_text())['automatic_data_download']
        helper.rollback(audit)
        assert (audit / 'rollback-current-input.json').exists()
        assert (audit / 'rollback.json').exists()
    assert (input_file.read_bytes(), report.read_bytes(), timer.read_bytes()) == before
    assert input_file.stat().st_mode & 0o777 == 0o640
    assert report.stat().st_mode & 0o777 == 0o600
    assert commands[-1] == ['systemctl', 'start', 'market-report.timer'] or not fail_start
    assert not mapped('/etc/systemd/system/market-report-refresh.service').exists()


def test_twelve_managed_credential_copy_preserves_strict_cli_key_policy(twelve_publish_case, twelve_case, tmp_path):
    import os
    helper, _, _, _, _, _ = twelve_publish_case
    cli, key, _, _, _ = twelve_case
    # A readable manager-style mode is not an ordinary privately owned key file.
    key.chmod(0o440)
    with pytest.raises(ValueError, match='PRIVATE_OWNED_KEY_FILE_REQUIRED'):
        cli.prepare_twelve_data_input(key, max_age_calendar_days=3)
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    output = runtime / 'provider.key'
    helper.stage_credential(key, output)
    assert output.stat().st_uid == os.geteuid()
    assert output.stat().st_mode & 0o777 == 0o400
    assert key.stat().st_mode & 0o777 == 0o440
    assert cli.prepare_twelve_data_input(output, max_age_calendar_days=3)['market_input']['provenance']['source'] == 'twelve_data'


def test_twelve_credential_entrypoint_runs_without_root_but_publish_still_requires_root(twelve_publish_case, twelve_case, tmp_path, monkeypatch):
    import os
    if os.geteuid() == 0:
        pytest.skip('This entrypoint regression requires an unprivileged test UID')
    helper, _, _, _, _, _ = twelve_publish_case
    _, key, _, _, _ = twelve_case
    monkeypatch.setattr(helper, 'ROOT_UID', 0)
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    output = runtime / 'provider.key'
    monkeypatch.setattr('sys.argv', ['rollout', 'stage-credential', '--source', str(key), '--key-output', str(output)])
    helper.main()
    assert output.stat().st_mode & 0o777 == 0o400
    monkeypatch.setattr('sys.argv', ['rollout', 'publish', '--source', str(tmp_path), '--account', 'market-report'])
    with pytest.raises(PermissionError, match='ROOT_CONTROLLED_OPERATION_REQUIRED'):
        helper.main()


@pytest.mark.parametrize('fault', ['shared_directory', 'existing_key', 'symlink', 'invalid', 'oversized'])
def test_twelve_credential_copy_refuses_unsafe_destination_or_content(twelve_publish_case, twelve_case, tmp_path, fault):
    helper, _, _, _, _, _ = twelve_publish_case
    _, key, _, _, _ = twelve_case
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    output = runtime / 'provider.key'
    if fault == 'shared_directory': runtime.chmod(0o755)
    if fault == 'existing_key': output.write_bytes(b'previous private key')
    if fault == 'symlink': output.symlink_to(key)
    if fault == 'invalid': key.write_bytes(b'invalid')
    if fault == 'oversized': key.write_bytes(b'A' * 513)
    before = key.read_bytes()
    with pytest.raises((ValueError, OSError)):
        helper.stage_credential(key, output)
    assert key.read_bytes() == before
    if fault == 'existing_key': assert output.read_bytes() == b'previous private key'
    elif fault == 'symlink': assert output.is_symlink()
    else: assert not output.exists()


@pytest.mark.parametrize('fault', [None, 'input_changed', 'successful_prior', 'wrong_account'])
def test_twelve_recovery_accepts_only_matching_failed_rollout(twelve_publish_case, tmp_path, fault):
    import json
    helper, _, _, account, _, _ = twelve_publish_case
    audit = tmp_path / 'failed-audit'
    audit.mkdir(mode=0o700)
    state = tmp_path / 'retained-state'
    state.mkdir(mode=0o700)
    manifest = {'account': account if fault != 'wrong_account' else 'someone-else'}
    (audit / 'manifest.json').write_text(json.dumps(manifest))
    for name, raw in [('service.before', b'service'), ('timer.before', b'timer'), ('input.before.json', b'input')]:
        (audit / name).write_bytes(raw)
    (state / 'pending.json').write_bytes(b'failed attempt evidence')
    if fault == 'successful_prior': (audit / 'receipt.json').write_bytes(b'{}')
    args = (audit, account, state, b'service', b'timer', b'changed' if fault == 'input_changed' else b'input')
    if fault:
        with pytest.raises(ValueError): helper.accept_failed_state(*args)
        assert not (audit / 'state-before-recovery').exists()
    else:
        helper.accept_failed_state(*args)
        assert (audit / 'state-before-recovery/pending.json').read_bytes() == b'failed attempt evidence'
    assert (state / 'pending.json').read_bytes() == b'failed attempt evidence'
