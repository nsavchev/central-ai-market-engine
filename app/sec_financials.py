"""Convert SEC Company Facts into annual Financials."""

from datetime import date
from decimal import Decimal

from .fundamentals import Financials


TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    ],
    "net_income": ["NetIncomeLoss"],
    "total_assets": ["Assets"],
    "shareholders_equity": ["StockholdersEquity"],
}


def select_fact(gaap, tags, period_end, instant=False, as_of_date=None):
    candidates = []

    for tag in tags:
        records = gaap.get(tag, {}).get(
            "units", {}
        ).get("USD", [])

        for r in records:
            if r.get("form") not in ("10-K", "10-K/A"):
                continue

            if as_of_date is not None:
                date.fromisoformat(as_of_date)
                filed = r.get("filed")
                if not filed or filed > as_of_date:
                    continue

            if r.get("fp") not in (None, "FY"):
                continue

            if r.get("fy") is not None:
                if (
                    not isinstance(r["fy"], int)
                    or isinstance(r["fy"], bool)
                    or abs(r["fy"] - date.fromisoformat(period_end).year) > 1
                ):
                    continue

            if r.get("end") != period_end:
                continue

            if not isinstance(r.get("val"), (int, float)):
                continue

            if instant:
                if r.get("start") is not None:
                    continue
            else:
                start = r.get("start")
                if not start:
                    continue

                try:
                    days = (
                        date.fromisoformat(period_end)
                        - date.fromisoformat(start)
                    ).days
                except ValueError:
                    continue

                if not 330 <= days <= 380:
                    continue

            candidates.append((
                r.get("filed", ""),
                r.get("accn", ""),
                -tags.index(tag),
                r["val"],
            ))

    if not candidates:
        return None

    best = max(candidates)
    return Decimal(str(best[3]))


def sec_to_financials(data, symbol, period_end, as_of_date=None):
    """Build an annual financial model from SEC facts."""

    gaap = data.get("facts", {}).get("us-gaap", {})

    if not gaap:
        raise ValueError("Missing US GAAP facts")

    date.fromisoformat(period_end)

    values = {}

    for field, tags in TAGS.items():
        values[field] = select_fact(
            gaap,
            tags,
            period_end,
            instant=field in (
                "total_assets",
                "shareholders_equity",
            ),
            as_of_date=as_of_date,
        )

    return Financials(
        symbol=symbol.upper(),
        period_end=period_end,
        period_type="FY",
        currency="USD",
        source="sec_edgar",
        **values,
    )
