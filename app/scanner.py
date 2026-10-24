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

def scan(payload: dict) -> dict:
    """Input: benchmark, sectors, assets, each with dated daily closes.
    All candidates must share benchmark's latest date. No implicit forward fills.
    Scores are heuristics, not probabilities or trading signals.
    """
    bench = _series(payload['benchmark']['bars'])
    if not bench: raise ValueError('Empty benchmark')
    asof = max(bench)
    sector_data = {key: _series(value['bars']) for key, value in payload.get('sectors', {}).items()}
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
