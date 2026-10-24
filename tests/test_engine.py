from datetime import date,timedelta
from app.engine import returns,trend,analyze

def test_relative_strength():
    days=[date(2025,1,1)+timedelta(days=i) for i in range(201)]
    a={d:100.0 for d in days}
    b={d:100.0 for d in days}
    b[days[-1]]=95.0
    r=analyze(a,b)
    assert abs(r['relative_performance_pp']['20']-5)<1e-8

def test_insufficient_data():
    assert trend([100.0]*10)=='INSUFFICIENT_DATA'
    assert returns([100.0]*10)['20'] is None

def test_date_alignment():
    d=date(2025,1,1)
    a={d+timedelta(days=i):100+i for i in range(25)}
    b={d+timedelta(days=i):100 for i in range(24)}
    r=analyze(a,b)
    assert r['as_of']==(d+timedelta(days=23)).isoformat()
