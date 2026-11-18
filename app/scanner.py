"""Offline, deterministic relative-strength scanner. No trading or network access."""
from datetime import date
from math import isfinite
from app.engine import analyze

PERIODS = ('5', '20', '60', '120')

def _series(rows):
    result = {}
    for row in rows:
        day = date.fromisoformat(row['date'])
        price = float(row['close'])
        if not isfinite(price) or price <= 0 or day in result:
            raise ValueError('Invalid, nonpositive, or duplicate daily close')
        result[day] = price
    return result

def scan(payload: dict, *, report_day: date | None = None,
         max_age_calendar_days: int | None = None) -> dict:
    """Input: benchmark, sectors, assets, each with dated daily closes.
    All candidates must share benchmark's latest date. No implicit forward fills.
    Scores are heuristics, not probabilities or trading signals.
    """
    if (report_day is None) != (max_age_calendar_days is None):
        raise ValueError('FRESHNESS_DATE_AND_LIMIT_REQUIRED')
    if report_day is not None:
        if type(report_day) is not date or type(max_age_calendar_days) is not int or max_age_calendar_days < 0:
            raise ValueError('INVALID_FRESHNESS_POLICY')
    bench = _series(payload['benchmark']['bars'])
    if not bench: raise ValueError('Empty benchmark')
    asof = max(bench)
    sector_data = {key: _series(value['bars']) for key, value in payload.get('sectors', {}).items()}
    if report_day is not None:
        streams = [bench, *sector_data.values(), *(_series(a['bars']) for a in payload['assets'])]
        if any(day > report_day for stream in streams for day in stream):
            raise ValueError('FUTURE_MARKET_BAR')
        if (report_day - asof).days > max_age_calendar_days:
            raise ValueError('STALE_MARKET_DATA')
    result = []
    for asset in payload['assets']:
        prices = _series(asset['bars'])
        symbol = asset['symbol']
        if not prices: continue
        if max(prices) != asof:
            result.append({'symbol': symbol, 'status': 'STALE', 'as_of': max(prices).isoformat()})
            continue
        base = analyze(prices, bench)
        sector_key = asset.get('sector')
        sector_rs = None
        if sector_key in sector_data and sector_data[sector_key] and max(sector_data[sector_key]) == asof:
            sector_rs = analyze(prices, sector_data[sector_key])['relative_performance_pp']
        rp = base['relative_performance_pp']
        # Score is only assigned when 20d and 60d are available.
        if rp['20'] is None or rp['60'] is None:
            status, score = 'INSUFFICIENT_DATA', None
        else:
            score = round(max(0, min(100, 50 + 2 * rp['20'] + rp['60'] + (10 if base['asset_trend']=='UPTREND' else -10 if base['asset_trend']=='DOWNTREND' else 0))), 2)
            status = 'OK'
        result.append({'symbol':symbol,'sector':sector_key,'status':status,'as_of':base['as_of'],
                       'relative_performance_pp':rp,'relative_to_sector_pp':sector_rs,
                       'trend':base['asset_trend'],'score':score})
    result.sort(key=lambda x: (x.get('score') is None, -(x.get('score') or 0), x['symbol']))
    return {'as_of':asof.isoformat(),'benchmark':payload['benchmark']['symbol'],
            'benchmark_trend':analyze(bench,bench)['benchmark_trend'],
            'method':'price returns; aligned trading dates; heuristic score', 'rankings':result}
