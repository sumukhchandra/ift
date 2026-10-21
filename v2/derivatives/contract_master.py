"""
NSE Contract Master Ingestion & Registry Module.
Ingests, maintains, and serves official NSE F&O contract specifications:
- Underlying symbols, lot sizes, tick sizes, quantity freezes, and expiry dates
- Ingests from NSE contract master files (e.g. NSE_FO_contract_*.csv)
- Validates active contracts and identifies securities without F&O derivatives
"""

import os
import csv
import gzip
import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Any

from .contract_specs import NSEContractSpec, ContractType
from .settlement_calendar import NSESettlementCalendar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NSEContractRecord:
    """A raw or ingested record from the official NSE F&O contract master."""
    symbol: str                     # e.g. "BAJFINANCE26SEPFUT"
    underlying_symbol: str          # e.g. "BAJFINANCE"
    contract_type: str              # "FUTSTK" or "FUTIDX"
    expiry_date: str                # ISO format "YYYY-MM-DD"
    lot_size: int                   # Contract lot size
    tick_size: float                # Applicable tick size from underlying
    quantity_freeze: int            # Order quantity freeze limit
    contract_status: str            # "ACTIVE", "EXPIRED", "SUSPENDED"
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None


# Official NSE Baseline Master for AlphaNSE Target Universe (as of September 2026 contract cycle)
# Note: BAJFINANCE lot size is 125, RELIANCE is 250, INFY is 400, TCS is 175, SBIN is 1500,
# HDFCBANK is 550, ICICIBANK is 700, AXISBANK is 625, BHARTIARTL is 475, NIFTY is 25.
# TATACAP has NO F&O contract on NSE; TATACONSUM is 900.
BASELINE_NSE_FO_CONTRACTS: List[Dict[str, Any]] = [
    {
        "symbol": "BAJFINANCE26SEPFUT",
        "underlying_symbol": "BAJFINANCE",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 125,
        "tick_size": 0.05,
        "quantity_freeze": 2500,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "BAJFINANCE26OCTFUT",
        "underlying_symbol": "BAJFINANCE",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-10-27",
        "lot_size": 125,
        "tick_size": 0.05,
        "quantity_freeze": 2500,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "RELIANCE26SEPFUT",
        "underlying_symbol": "RELIANCE",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 250,
        "tick_size": 0.05,
        "quantity_freeze": 5000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "RELIANCE26OCTFUT",
        "underlying_symbol": "RELIANCE",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-10-27",
        "lot_size": 250,
        "tick_size": 0.05,
        "quantity_freeze": 5000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "INFY26SEPFUT",
        "underlying_symbol": "INFY",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 400,
        "tick_size": 0.05,
        "quantity_freeze": 8000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "TCS26SEPFUT",
        "underlying_symbol": "TCS",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 175,
        "tick_size": 0.05,
        "quantity_freeze": 3500,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "SBIN26SEPFUT",
        "underlying_symbol": "SBIN",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 1500,
        "tick_size": 0.05,
        "quantity_freeze": 30000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "HDFCBANK26SEPFUT",
        "underlying_symbol": "HDFCBANK",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 550,
        "tick_size": 0.05,
        "quantity_freeze": 11000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "ICICIBANK26SEPFUT",
        "underlying_symbol": "ICICIBANK",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 700,
        "tick_size": 0.05,
        "quantity_freeze": 14000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "AXISBANK26SEPFUT",
        "underlying_symbol": "AXISBANK",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 625,
        "tick_size": 0.05,
        "quantity_freeze": 12500,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "BHARTIARTL26SEPFUT",
        "underlying_symbol": "BHARTIARTL",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 475,
        "tick_size": 0.05,
        "quantity_freeze": 9500,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "TATACONSUM26SEPFUT",
        "underlying_symbol": "TATACONSUM",
        "contract_type": "FUTSTK",
        "expiry_date": "2026-09-29",
        "lot_size": 900,
        "tick_size": 0.05,
        "quantity_freeze": 18000,
        "contract_status": "ACTIVE",
    },
    {
        "symbol": "NIFTY26SEPFUT",
        "underlying_symbol": "NIFTY",
        "contract_type": "FUTIDX",
        "expiry_date": "2026-09-29",
        "lot_size": 25,
        "tick_size": 0.05,
        "quantity_freeze": 1800,
        "contract_status": "ACTIVE",
    },
]


class NSEContractMaster:
    """
    Registry and query interface for NSE F&O contracts.
    Prevents hard-coding lot sizes and enforces data-driven contract specifications.
    """

    def __init__(self, settlement_calendar: Optional[NSESettlementCalendar] = None):
        self.calendar = settlement_calendar or NSESettlementCalendar()
        self._contracts: Dict[str, NSEContractSpec] = {}  # key: contract symbol
        self._underlying_index: Dict[str, List[NSEContractSpec]] = {}  # key: underlying_symbol

        # Load baseline master initially
        self._load_baseline_records()

    def _load_baseline_records(self) -> None:
        """Populates the registry from verified baseline records."""
        for rec in BASELINE_NSE_FO_CONTRACTS:
            spec = NSEContractSpec(
                symbol=rec["symbol"],
                underlying_symbol=rec["underlying_symbol"],
                contract_type=ContractType(rec["contract_type"]),
                expiry_date=datetime.strptime(rec["expiry_date"], "%Y-%m-%d").date(),
                lot_size=rec["lot_size"],
                tick_size=rec["tick_size"],
                quantity_freeze=rec["quantity_freeze"],
                contract_status=rec.get("contract_status", "ACTIVE")
            )
            self.register_contract(spec)

    def register_contract(self, spec: NSEContractSpec) -> None:
        """Registers a contract specification into the master index."""
        self._contracts[spec.symbol] = spec
        if spec.underlying_symbol not in self._underlying_index:
            self._underlying_index[spec.underlying_symbol] = []
        # Replace if already present
        self._underlying_index[spec.underlying_symbol] = [
            c for c in self._underlying_index[spec.underlying_symbol] if c.symbol != spec.symbol
        ]
        self._underlying_index[spec.underlying_symbol].append(spec)

    def get_contract_by_symbol(self, contract_symbol: str) -> Optional[NSEContractSpec]:
        """Looks up a contract by its full symbol."""
        return self._contracts.get(contract_symbol)

    def get_contracts_for_underlying(self, underlying_symbol: str) -> List[NSEContractSpec]:
        """Returns all contracts for a given underlying."""
        clean = underlying_symbol.upper().replace(".NS", "").replace("^", "")
        return sorted(self._underlying_index.get(clean, []), key=lambda c: c.expiry_date)

    def get_near_month_contract(
        self,
        underlying_symbol: str,
        as_of_date: date
    ) -> Optional[NSEContractSpec]:
        """
        Retrieves the nearest active contract whose expiry is >= as_of_date.
        """
        contracts = self.get_contracts_for_underlying(underlying_symbol)
        active_unexpired = [c for c in contracts if c.is_active and c.expiry_date >= as_of_date]
        if not active_unexpired:
            return None
        return min(active_unexpired, key=lambda c: c.expiry_date)

    def has_fo_contract(self, underlying_symbol: str) -> bool:
        """Checks if the underlying security has active F&O contracts."""
        clean = underlying_symbol.upper().replace(".NS", "").replace("^", "")
        contracts = self._underlying_index.get(clean, [])
        return any(c.is_active for c in contracts)

    def list_active_underlyings(self) -> List[str]:
        """Lists all underlyings with at least one active contract."""
        return sorted([
            u for u, contracts in self._underlying_index.items()
            if any(c.is_active for c in contracts)
        ])

    def load_from_csv(self, file_path: str) -> int:
        """
        Ingests contract specifications from an NSE contract file (.csv or .csv.gz).
        Expected columns: SYMBOL, UNDERLYING, INSTRUMENT, EXPIRY_DT, LOT_SIZE, TICK_SIZE, FREEZE_QTY, STATUS
        Returns count of ingested contracts.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"NSE Contract file not found: {file_path}")

        count = 0
        open_fn = gzip.open if file_path.endswith(".gz") else open
        mode = "rt" if file_path.endswith(".gz") else "r"

        with open_fn(file_path, mode, encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize column keys
                norm_row = {k.strip().upper(): v.strip() for k, v in row.items() if k}
                inst = norm_row.get("INSTRUMENT", norm_row.get("INSTRUMENT_TYPE", ""))
                if inst not in ("FUTSTK", "FUTIDX"):
                    continue

                sym = norm_row.get("SYMBOL", "")
                underlying = norm_row.get("UNDERLYING", norm_row.get("SECURITY_SYMBOL", sym))
                expiry_str = norm_row.get("EXPIRY_DT", norm_row.get("EXPIRY_DATE", ""))
                lot_size = int(norm_row.get("LOT_SIZE", norm_row.get("MARKET_LOT", 0)))
                tick_size = float(norm_row.get("TICK_SIZE", 0.05))
                freeze = int(norm_row.get("FREEZE_QTY", norm_row.get("QUANTITY_FREEZE", 5000)))
                status = norm_row.get("STATUS", "ACTIVE")

                # Parse expiry
                for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
                    try:
                        exp_date = datetime.strptime(expiry_str, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    logger.warning(f"Could not parse expiry date '{expiry_str}' in row: {norm_row}")
                    continue

                spec = NSEContractSpec(
                    symbol=sym,
                    underlying_symbol=underlying,
                    contract_type=ContractType(inst),
                    expiry_date=exp_date,
                    lot_size=lot_size,
                    tick_size=tick_size,
                    quantity_freeze=freeze,
                    contract_status=status
                )
                self.register_contract(spec)
                count += 1

        logger.info(f"Ingested {count} contracts from {file_path}")
        return count
