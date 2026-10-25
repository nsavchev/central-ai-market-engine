"""Isolated test-only HTTP application; never mounted on production FastAPI."""
import os
from decimal import Decimal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from app.paper_atomic_service import record_paper_fill

app=FastAPI(title="Disposable Paper Test API")

class Fill(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9._-]{1,32}$")
    side: str = Field(pattern=r"^(BUY|SELL)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"),ge=0)
    generation: int = Field(ge=0)

@app.post("/test-only/paper/fills")
def fill(body:Fill,x_api_token:str|None=Header(default=None)):
    token=os.getenv("TEST_PAPER_API_TOKEN")
    if not token or x_api_token!=token:
        raise HTTPException(401,"Unauthorized")
    url=os.getenv("TEST_POSTGRES_URL")
    if not url or not url.startswith("postgresql+psycopg://") or "127.0.0.1" not in url:
        raise HTTPException(503,"Disposable PostgreSQL required")
    engine=create_engine(url)
    try:
        return record_paper_fill(engine,account_id=1,symbol=body.symbol,
                                 side=body.side,quantity=body.quantity,
                                 price=body.price,fee=body.fee,
                                 expected_generation=body.generation)
    except PermissionError:
        raise HTTPException(409,"PAPER_WRITES_FENCED") from None
    except ValueError:
        raise HTTPException(422,"PAPER_FILL_REJECTED") from None
    finally:
        engine.dispose()
