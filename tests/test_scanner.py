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
