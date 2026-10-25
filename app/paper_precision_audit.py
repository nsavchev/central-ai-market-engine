"""Fail-closed candidate conversion audit: Float -> NUMERIC (no writes)."""
from decimal import Decimal, InvalidOperation

def assess(value, *, integer_digits: int, decimal_places: int):
    try:
        if value is None or isinstance(value, bool):
            return {"safe": False, "reason": "NULL_OR_BOOLEAN"}
        val = Decimal(str(value))
        if not val.is_finite():
            return {"safe": False, "reason": "NONFINITE"}
        scale = Decimal(1).scaleb(-decimal_places)
        rounded = val.quantize(scale)
        if val != rounded:
            return {"safe": False, "reason": "PRECISION_LOSS"}
        if abs(rounded) >= Decimal(10) ** integer_digits:
            return {"safe": False, "reason": "OUT_OF_RANGE"}
        return {"safe": True, "reason": "EXACT_DECIMAL_REPRESENTATION", "value": str(rounded)}
    except (InvalidOperation, ValueError, TypeError):
        return {"safe": False, "reason": "INVALID_VALUE"}
