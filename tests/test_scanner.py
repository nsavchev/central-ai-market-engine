from datetime import date, timedelta
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
