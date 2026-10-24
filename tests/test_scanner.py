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
