import unittest
from decimal import Decimal
from central_ai.paper_ledger_decimal import simulate_fill

class DecimalPaperLedgerTests(unittest.TestCase):
    def test_exact_arithmetic(self):
        result=simulate_fill(cash="100.00",held="0",side="BUY",quantity="0.1",price="0.10",fee="0")
        self.assertEqual(result["cash"],Decimal("99.99"))
        self.assertEqual(result["shares"],Decimal("0.1"))

    def test_round_trip_with_fees(self):
        bought=simulate_fill(cash="1000.00",held="0",side="BUY",quantity="2",price="10.25",fee="0.50")
        sold=simulate_fill(cash=bought["cash"],held=bought["shares"],side="SELL",quantity="2",price="10.25",fee="0.50")
        self.assertEqual(sold["cash"],Decimal("999.00"))
        self.assertEqual(sold["shares"],Decimal("0"))

    def test_cannot_overdraw(self):
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_CASH"):
            simulate_fill(cash="10.00",held=0,side="BUY",quantity=1,price="10.00",fee="0.01")

    def test_no_short_selling(self):
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_SHARES"):
            simulate_fill(cash="100.00",held=0,side="SELL",quantity=1,price="10.00")

    def test_fee_exceeds_proceeds(self):
        with self.assertRaisesRegex(ValueError,"SELL_FEE_EXCEEDS_PROCEEDS"):
            simulate_fill(cash="100.00",held=1,side="SELL",quantity=1,price="0.01",fee="0.02")

    def test_invalid_float_special_value(self):
        with self.assertRaises(ValueError):
            simulate_fill(cash="NaN",held=0,side="BUY",quantity=1,price=1)

    def test_precision_restricted(self):
        with self.assertRaisesRegex(ValueError,"INVALID_MONEY_PRECISION"):
            simulate_fill(cash="100.00",held=0,side="BUY",quantity=1,price="1.001")

    def test_fractional_rounding_is_deterministic(self):
        result=simulate_fill(cash="1.00",held=0,side="BUY",quantity="0.5",price="0.01")
        self.assertEqual(result["cash"],Decimal("1.00"))

if __name__=="__main__":
    unittest.main()
