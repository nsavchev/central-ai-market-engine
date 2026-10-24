from datetime import date
from math import isfinite

def returns(prices: list[float], periods=(5,20,60,120)) -> dict[str,float|None]:
    if not prices or any(not isfinite(x) or x <= 0 for x in prices):
        raise ValueError('Prices must be positive finite numbers')
    return {str(n): (prices[-1]/prices[-n-1]-1)*100 if len(prices)>n else None for n in periods}

def sma(prices: list[float], n: int) -> float|None:
    return sum(prices[-n:])/n if len(prices)>=n else None

def trend(prices: list[float]) -> str:
    s50,s200=sma(prices,50),sma(prices,200)
    if s50 is None or s200 is None: return 'INSUFFICIENT_DATA'
    if prices[-1]>s50>s200: return 'UPTREND'
    if prices[-1]<s50<s200: return 'DOWNTREND'
    return 'MIXED'

def analyze(asset: dict[date,float], benchmark: dict[date,float]) -> dict:
    # Align sessions before computing both returns; avoids stale/mismatched dates.
    days=sorted(set(asset)&set(benchmark))
    if not days: raise ValueError('No overlapping dates')
    a=[asset[d] for d in days]
    b=[benchmark[d] for d in days]
    ar,br=returns(a),returns(b)
    rs={k: round(ar[k]-br[k],4) if ar[k] is not None and br[k] is not None else None for k in ar}
    return {'as_of':days[-1].isoformat(),'sessions':len(days),'asset_return_pct':ar,'benchmark_return_pct':br,'relative_performance_pp':rs,'asset_trend':trend(a),'benchmark_trend':trend(b)}
