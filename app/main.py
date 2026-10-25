from datetime import date
import math
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .config import settings
from .db import init_db,SessionLocal,Instrument,DailyBar,PaperAccount,PaperTrade
from .engine import analyze
try:
    from .ibkr import fetch_daily
except ModuleNotFoundError as exc:
    if exc.name != "ibapi":
        raise

    def fetch_daily(*args, **kwargs):
        raise RuntimeError("IBKR unavailable")

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield
app=FastAPI(title='Market Intelligence v0.2',lifespan=lifespan)

def auth(x_api_token: str|None=Header(default=None)):
    if settings.api_token=='change-me' or x_api_token!=settings.api_token:
        raise HTTPException(401,'Valid configured X-API-Token required')

class ImportRequest(BaseModel):
    symbol:str=Field(pattern=r'^[A-Za-z0-9._-]{1,32}$')
    exchange:str='SMART'
    currency:str='USD'
    primary_exchange:str=''
    sec_type:str='STK'
    duration:str='1 Y'

@app.get('/health')
def health(): return {'status':'ok'}

@app.post('/ingest/ibkr',dependencies=[Depends(auth)])
def ingest(req:ImportRequest):
    try:
        bars=fetch_daily(req.symbol,req.exchange,req.currency,req.primary_exchange,req.sec_type,req.duration,settings.ibkr_host,settings.ibkr_port,settings.ibkr_client_id)
    except Exception as e: raise HTTPException(502,str(e))
    with SessionLocal.begin() as db:
        ins=db.scalar(select(Instrument).where(Instrument.symbol==req.symbol,Instrument.exchange==req.exchange,Instrument.currency==req.currency,Instrument.primary_exchange==req.primary_exchange,Instrument.sec_type==req.sec_type))
        if ins is None:
            ins=Instrument(symbol=req.symbol,exchange=req.exchange,currency=req.currency,primary_exchange=req.primary_exchange,sec_type=req.sec_type)
            db.add(ins); db.flush()
        for bar in bars:
            day=date.fromisoformat(bar['day'][:10])
            old=db.scalar(select(DailyBar).where(DailyBar.instrument_id==ins.id,DailyBar.day==day,DailyBar.source=='IBKR'))
            if old is None: db.add(DailyBar(instrument_id=ins.id,day=day,open=bar['open'],high=bar['high'],low=bar['low'],close=bar['close'],volume=bar['volume']))
            else:
                for k in ('open','high','low','close','volume'): setattr(old,k,bar[k])
    return {'symbol':req.symbol,'bars_received':len(bars)}

@app.get('/analysis/{symbol}',dependencies=[Depends(auth)])
def analysis(symbol:str,benchmark:str='SPY'):
    with SessionLocal() as db:
        def load(sym):
            # v0.2 assumes one instrument per symbol; ambiguous global symbols must be disambiguated in v0.3.
            instruments=db.scalars(select(Instrument).where(Instrument.symbol==sym)).all()
            if len(instruments)!=1: raise HTTPException(409,f'{sym}: expected exactly one instrument, found {len(instruments)}')
            rows=db.scalars(select(DailyBar).where(DailyBar.instrument_id==instruments[0].id).order_by(DailyBar.day)).all()
            return {r.day:r.close for r in rows}
        a,b=load(symbol),load(benchmark)
    try: return {'symbol':symbol,'benchmark':benchmark,**analyze(a,b)}
    except ValueError as e: raise HTTPException(422,str(e))

class TradeRequest(BaseModel):
    symbol:str=Field(pattern=r'^[A-Za-z0-9._-]{1,32}$')
    side:str=Field(pattern='^(BUY|SELL)$')
    quantity:float=Field(gt=0)
    price:float=Field(gt=0,description='Explicit hypothetical fill price, not a live quote')
    fee:float=Field(default=0,ge=0)

    @model_validator(mode='after')
    def validate_paper_fill(self):
        # Reject NaN/infinity and excessive input precision before touching cash.
        for key in ('quantity', 'price', 'fee'):
            value = getattr(self, key)
            if not math.isfinite(value):
                raise ValueError('NON_FINITE_PAPER_FILL')
        if self.quantity > 1_000_000 or self.price > 1_000_000 or self.fee > 1_000_000:
            raise ValueError('PAPER_FILL_LIMIT_EXCEEDED')
        if round(self.price, 2) != self.price or round(self.fee, 2) != self.fee:
            raise ValueError('PAPER_MONEY_REQUIRES_CENTS')
        if round(self.quantity, 6) != self.quantity:
            raise ValueError('PAPER_QUANTITY_PRECISION_EXCEEDED')
        return self

@app.post('/paper/trades',dependencies=[Depends(auth)])
def paper_trade(t:TradeRequest):
    # Manual hypothetical fills only. No brokerage orders, FX conversion, or margin.
    with SessionLocal.begin() as db:
        account=db.get(PaperAccount,1)
        if account is None:
            account=PaperAccount(id=1,cash=100000.0); db.add(account); db.flush()
        trades=db.scalars(select(PaperTrade).where(PaperTrade.account_id==1,PaperTrade.symbol==t.symbol)).all()
        held=sum(x.quantity*(1 if x.side=='BUY' else -1) for x in trades)
        if t.side=='SELL' and t.quantity>held+1e-9: raise HTTPException(400,'Insufficient shares')
        amount=t.quantity*t.price
        if t.side=='BUY' and amount+t.fee>account.cash+1e-9: raise HTTPException(400,'Insufficient cash')
        account.cash+=(-amount-t.fee) if t.side=='BUY' else (amount-t.fee)
        db.add(PaperTrade(account_id=1,symbol=t.symbol,side=t.side,quantity=t.quantity,price=t.price,fee=t.fee))
        return {'cash':round(account.cash,2),'symbol':t.symbol,'position_shares':held+(t.quantity if t.side=='BUY' else -t.quantity),'mode':'SIMULATION_ONLY'}

@app.get('/paper/account',dependencies=[Depends(auth)])
def paper_account():
    with SessionLocal() as db:
        a=db.get(PaperAccount,1)
        trades=db.scalars(select(PaperTrade).where(PaperTrade.account_id==1)).all()
        positions={}
        for t in trades: positions[t.symbol]=positions.get(t.symbol,0)+t.quantity*(1 if t.side=='BUY' else -1)
        return {'cash':a.cash if a else 100000,'currency':'USD','positions':positions,'valuation':'NOT_IMPLEMENTED','mode':'SIMULATION_ONLY'}

# Macro triage is data-only: caller supplies verified event records.
from .macro import Event as MacroEvent, evaluate as evaluate_macro
class MacroRequest(BaseModel):
    events: list[MacroEvent] = Field(max_length=500)
    asof: __import__("datetime").datetime | None = None

@app.post('/macro/evaluate', dependencies=[Depends(auth)])
def macro_evaluate(request: MacroRequest):
    try: return evaluate_macro(request.events,request.asof)
    except ValueError as exc: raise HTTPException(422,str(exc))

# v0.5: permission-aware registry and calculation-only fundamental endpoint.
from .sources import list_sources, validate_source
from .fundamentals import Financials, calculate

@app.get('/sources', dependencies=[Depends(auth)])
def sources():
    return {'sources':list_sources()}

@app.post('/fundamentals/evaluate', dependencies=[Depends(auth)])
def fundamentals_evaluate(financials: Financials):
    try: validate_source(financials.source, automated=False)
    except (ValueError, PermissionError) as exc: raise HTTPException(403,str(exc))
    return calculate(financials)

# v0.6: manually sourced annual financial history, stored in PostgreSQL.
from .db import FinancialSnapshot
from .fundamentals_history import store_snapshot, history_report

@app.post('/fundamentals/history/import', dependencies=[Depends(auth)])
def fundamentals_history_import(items: list[Financials]):
    if not items or len(items) > 100:
        raise HTTPException(422, 'Provide 1-100 records')
    try:
        with SessionLocal.begin() as db:
            for item in items:
                store_snapshot(db,item)
        return {'stored':len(items),'mode':'MANUAL_IMPORT_ONLY'}
    except (ValueError,PermissionError) as exc:
        raise HTTPException(422,str(exc))

@app.get('/fundamentals/history/{symbol}', dependencies=[Depends(auth)])
def fundamentals_history(symbol: str, currency: str='USD', source: str='manual', years: int=10):
    if years<2 or years>20: raise HTTPException(422,'years must be 2-20')
    try:
        with SessionLocal() as db:
            return history_report(db,symbol,currency,source,years)
    except (ValueError,PermissionError) as exc:
        raise HTTPException(422,str(exc))

# v0.7: explicit-input DCF. No live quotes or trading actions.
from .valuation import ValuationRequest, evaluate as evaluate_valuation

@app.post('/valuation/evaluate', dependencies=[Depends(auth)])
def valuation_evaluate(request: ValuationRequest):
    try: return evaluate_valuation(request)
    except (ValueError, OverflowError) as exc: raise HTTPException(422,str(exc))

# Advanced probability-weighted DCF valuation
from .advanced_valuation import AdvancedRequest, analyze

@app.post(
    "/valuation/advanced",
    dependencies=[Depends(auth)]
)
def valuation_advanced(request: AdvancedRequest):
    try:
        return analyze(request)
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
