from decimal import Decimal

import pytest

from app.sec_financials import select_fact, sec_to_financials


def make_fact(value, start=None, end="2025-09-27",
              form="10-K", filed="2025-10-31"):
    return {
        "val": value,
        "start": start,
        "end": end,
        "form": form,
        "filed": filed,
        "accn": "TEST-001",
        "fy": 2025,
        "fp": "FY",
    }


def test_annual_revenue():
    gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    make_fact(
                        100000000,
                        start="2024-09-29"
                    )
                ]
            }
        }
    }

    result = select_fact(
        gaap,
        ["Revenues"],
        "2025-09-27"
    )

    assert result == Decimal("100000000")


def test_wrong_period_rejected():
    gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    make_fact(
                        100000000,
                        start="2023-09-30",
                        end="2024-09-28"
                    )
                ]
            }
        }
    }

    result = select_fact(
        gaap,
        ["Revenues"],
        "2025-09-27"
    )

    assert result is None


def test_quarterly_duration_rejected():
    gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    make_fact(
                        25000000,
                        start="2025-06-29"
                    )
                ]
            }
        }
    }

    result = select_fact(
        gaap,
        ["Revenues"],
        "2025-09-27"
    )

    assert result is None


def test_instant_assets():
    gaap = {
        "Assets": {
            "units": {
                "USD": [
                    make_fact(300000000)
                ]
            }
        }
    }

    result = select_fact(
        gaap,
        ["Assets"],
        "2025-09-27",
        instant=True
    )

    assert result == Decimal("300000000")


def test_missing_gaap_rejected():
    with pytest.raises(ValueError):
        sec_to_financials(
            {"facts": {}},
            "TEST",
            "2025-09-27"
        )


def test_quarterly_form_rejected():
    gaap = {
        "Revenues": {
            "units": {
                "USD": [
                    make_fact(
                        100000000,
                        start="2024-09-29",
                        form="10-Q"
                    )
                ]
            }
        }
    }
    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) is None


def test_wrong_fiscal_year_rejected():
    fact = make_fact(
        100000000,
        start="2024-09-29"
    )
    fact["fy"] = 2023

    gaap = {
        "Revenues": {
            "units": {"USD": [fact]}
        }
    }
    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) is None


def test_invalid_numeric_value_rejected():
    fact = make_fact(
        "INVALID",
        start="2024-09-29"
    )
    gaap = {
        "Revenues": {
            "units": {"USD": [fact]}
        }
    }
    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) is None


def test_wrong_fiscal_period_rejected():
    fact = make_fact(
        100000000,
        start="2024-09-29"
    )
    fact["fp"] = "Q3"

    gaap = {
        "Revenues": {
            "units": {"USD": [fact]}
        }
    }
    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) is None


def test_latest_filing_selected():
    old = make_fact(
        100000000,
        start="2024-09-29",
        filed="2025-10-31"
    )
    new = make_fact(
        110000000,
        start="2024-09-29",
        filed="2025-11-15",
        form="10-K/A"
    )

    gaap = {
        "Revenues": {
            "units": {"USD": [old, new]}
        }
    }

    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) == Decimal("110000000")


def test_future_filing_not_used_as_of_date():
    old = make_fact(
        100000000,
        start="2024-09-29",
        filed="2025-10-31"
    )
    new = make_fact(
        110000000,
        start="2024-09-29",
        filed="2025-11-15"
    )

    gaap = {
        "Revenues": {
            "units": {"USD": [old, new]}
        }
    }

    # Current adapter has no as-of-date parameter.
    # This test documents current selection behavior.
    assert select_fact(
        gaap, ["Revenues"], "2025-09-27"
    ) == Decimal("110000000")


def test_sec_to_financials_point_in_time_integration():
    from app.sec_financials import sec_to_financials
    from decimal import Decimal

    def fact(value, filed):
        return {
            "val": value,
            "start": "2024-09-29",
            "end": "2025-09-27",
            "form": "10-K",
            "filed": filed,
            "accn": "TEST-001",
            "fy": 2025,
            "fp": "FY",
        }

    data = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            fact(100000000, "2025-10-31"),
                            fact(110000000, "2025-11-15"),
                        ]
                    }
                }
            }
        }
    }

    cases = [
        ("2025-10-30", None),
        ("2025-11-01", Decimal("100000000")),
        ("2025-11-16", Decimal("110000000")),
    ]

    for as_of, expected in cases:
        result = sec_to_financials(
            data,
            "TEST",
            "2025-09-27",
            as_of_date=as_of,
        )
        assert result.revenue == expected
