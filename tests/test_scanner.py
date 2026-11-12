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
