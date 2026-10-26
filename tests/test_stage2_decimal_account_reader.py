from decimal import Decimal
from unittest.mock import MagicMock
from app import main

def test_account_reader_returns_exact_decimal_strings(monkeypatch):
    session=MagicMock()
    session.get.return_value=type("Account",(),{"cash":Decimal("99918.75")})()
    session.scalars.return_value.all.return_value=[
      type("Trade",(),{"symbol":"SPY","side":"BUY","quantity":Decimal("2.000001")})(),
      type("Trade",(),{"symbol":"SPY","side":"SELL","quantity":Decimal("1.000000")})()]
    manager=MagicMock()
    manager.__enter__.return_value=session
    monkeypatch.setattr(main,"SessionLocal",lambda:manager)
    result=main.paper_account()
    assert result["cash"]=="99918.75"
    assert result["positions"]=={"SPY":"1.000001"}
    assert result["mode"]=="SIMULATION_ONLY"

def test_account_reader_preserves_initial_balance_without_account(monkeypatch):
    session=MagicMock()
    session.get.return_value=None
    session.scalars.return_value.all.return_value=[]
    manager=MagicMock()
    manager.__enter__.return_value=session
    monkeypatch.setattr(main,"SessionLocal",lambda:manager)
    assert main.paper_account()["cash"]=="100000.00"
