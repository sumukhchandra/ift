"""
Unit Tests for NSE Contract Master Ingestion & Registry.
Verifies dynamic contract querying, lot sizes, tick sizes, and underlying symbol verification.
"""

import unittest
from datetime import date
from v2.derivatives.contract_master import NSEContractMaster
from v2.derivatives.contract_specs import ContractType


class TestNSEContractMaster(unittest.TestCase):

    def setUp(self):
        self.master = NSEContractMaster()

    def test_baseline_contracts_loaded(self):
        """Verify standard baseline contracts are registered."""
        underlyings = self.master.list_active_underlyings()
        self.assertIn("BAJFINANCE", underlyings)
        self.assertIn("RELIANCE", underlyings)
        self.assertIn("INFY", underlyings)
        self.assertIn("TCS", underlyings)
        self.assertIn("SBIN", underlyings)
        self.assertIn("NIFTY", underlyings)

    def test_bajfinance_contract_specs(self):
        """Verify BAJFINANCE lot size and tick size from contract master."""
        spec = self.master.get_near_month_contract("BAJFINANCE", as_of_date=date(2026, 9, 20))
        self.assertIsNotNone(spec)
        self.assertEqual(spec.underlying_symbol, "BAJFINANCE")
        self.assertEqual(spec.lot_size, 125)
        self.assertEqual(spec.tick_size, 0.05)
        self.assertEqual(spec.contract_type, ContractType.FUTSTK)
        self.assertEqual(spec.expiry_date, date(2026, 9, 29))

    def test_tatacap_is_not_fo_contract(self):
        """
        TATACAP has NO active F&O contracts on NSE.
        Verify that has_fo_contract returns False and contracts list is empty.
        """
        self.assertFalse(self.master.has_fo_contract("TATACAP"))
        contracts = self.master.get_contracts_for_underlying("TATACAP")
        self.assertEqual(len(contracts), 0)

        near_contract = self.master.get_near_month_contract("TATACAP", as_of_date=date(2026, 9, 20))
        self.assertIsNone(near_contract)

    def test_tataconsum_is_distinct(self):
        """TATACONSUM has active contracts (lot size 900) and is distinct from TATACAP."""
        self.assertTrue(self.master.has_fo_contract("TATACONSUM"))
        spec = self.master.get_near_month_contract("TATACONSUM", as_of_date=date(2026, 9, 20))
        self.assertIsNotNone(spec)
        self.assertEqual(spec.lot_size, 900)


if __name__ == "__main__":
    unittest.main()
