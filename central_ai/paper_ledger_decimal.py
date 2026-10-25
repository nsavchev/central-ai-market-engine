"""Deterministic paper-account arithmetic; no broker or database writes.

Isolated pure arithmetic for future migration away from floating-point persistence.
The API is not yet wired to this helper. Concurrency requires database row locking.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

CENT = Decimal("0.01")
SHARE = Decimal("0.000001")


def _decimal(value, label):
    if isinstance(value, bool):
        raise ValueError(label)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(label) from None
    if not number.is_finite():
        raise ValueError(label)
    return number


def simulate_fill(*, cash, held, side, quantity, price, fee=0):
    """Return exact cash and shares after one explicitly hypothetical fill."""
    balance = _decimal(cash, "INVALID_CASH")
    shares = _decimal(held, "INVALID_HELD")
    qty = _decimal(quantity, "INVALID_QUANTITY")
    px = _decimal(price, "INVALID_PRICE")
    charge = _decimal(fee, "INVALID_FEE")
    if side not in ("BUY", "SELL"):
        raise ValueError("INVALID_SIDE")
    if balance < 0 or shares < 0 or qty <= 0 or px <= 0 or charge < 0:
        raise ValueError("INVALID_LEDGER_INPUT")
    if balance != balance.quantize(CENT) or px != px.quantize(CENT) or charge != charge.quantize(CENT):
        raise ValueError("INVALID_MONEY_PRECISION")
    if qty != qty.quantize(SHARE) or shares != shares.quantize(SHARE):
        raise ValueError("INVALID_QUANTITY_PRECISION")
    gross = (qty * px).quantize(CENT, rounding=ROUND_HALF_EVEN)
    if side == "BUY":
        cost = gross + charge
        if cost > balance:
            raise ValueError("INSUFFICIENT_CASH")
        return {"cash": balance - cost, "shares": shares + qty}
    if qty > shares:
        raise ValueError("INSUFFICIENT_SHARES")
    if gross < charge:
        raise ValueError("SELL_FEE_EXCEEDS_PROCEEDS")
    return {"cash": balance + gross - charge, "shares": shares - qty}
