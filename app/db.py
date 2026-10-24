from datetime import date, datetime, timezone
from sqlalchemy import create_engine, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

class Instrument(Base):
    __tablename__ = 'instruments'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(32), default='SMART')
    currency: Mapped[str] = mapped_column(String(8), default='USD')
    sec_type: Mapped[str] = mapped_column(String(12), default='STK')
    primary_exchange: Mapped[str] = mapped_column(String(32), default='')
    __table_args__ = (UniqueConstraint('symbol','exchange','currency','sec_type','primary_exchange'),)

class DailyBar(Base):
    __tablename__ = 'daily_bars'
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instruments.id'))
    day: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(24), default='IBKR')
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('instrument_id','day','source'),)

class PaperAccount(Base):
    __tablename__ = 'paper_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    cash: Mapped[float] = mapped_column(Float, default=100000.0)
    currency: Mapped[str] = mapped_column(String(8), default='USD')

class PaperTrade(Base):
    __tablename__ = 'paper_trades'
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('paper_accounts.id'))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class FinancialSnapshot(Base):
    __tablename__ = 'financial_snapshots'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('symbol','period_end','period_type','currency','source'),)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
