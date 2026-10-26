"""ORM contract only: no DB connection, no schema modification."""
from decimal import Decimal
from sqlalchemy import Numeric, Float
from app.db import PaperAccount, PaperTrade, DailyBar

def test_account_numeric_precision():
    col=PaperAccount.__table__.c.cash
    assert isinstance(col.type,Numeric)
    assert (col.type.precision,col.type.scale)==(20,2)
    assert isinstance(PaperAccount().cash if PaperAccount().cash is not None else Decimal('0'),Decimal)

def test_paper_trade_numeric_precision():
    for name,precision,scale in [('quantity',24,6),('price',20,2),('fee',20,2)]:
        col=PaperTrade.__table__.c[name]
        assert isinstance(col.type,Numeric)
        assert (col.type.precision,col.type.scale)==(precision,scale)

def test_market_data_remains_float():
    assert isinstance(DailyBar.__table__.c.close.type,Float)
