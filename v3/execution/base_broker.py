#!/usr/bin/env python3
"""
v3/execution/base_broker.py
Abstract Base Broker Interface for AlphaNSE.

Provides a unified, broker-agnostic contract for:
1. RealisticSimulatedBroker (Paper / Historical Replay / Stress Testing)
2. LiveBrokerAdapter (e.g., DhanHQ, Zerodha, Fyers)

Guarantees that the AlphaNSE strategy logic remains 100% identical
regardless of whether it runs in simulated or live mode.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime


class BaseBroker(ABC):
    """
    Abstract interface for all AlphaNSE execution adapters.
    """

    @property
    @abstractmethod
    def is_live(self) -> bool:
        """
        Returns True if this broker places real money orders on an exchange.
        Must return False for all paper/simulation engines.
        """
        pass

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Identifier for the broker (e.g. 'RealisticSimulatedBroker', 'DhanHQ')."""
        pass

    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """
        Returns available cash and account balance.
        Format:
        {
            "available_cash": float,
            "collateral": float,
            "total_equity": float,
            "currency": "INR"
        }
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Returns list of currently open positions.
        Format:
        [
            {
                "symbol": str,
                "quantity": int,
                "entry_price": float,
                "current_price": float,
                "unrealized_pnl": float,
                "side": "BUY"
            }
        ]
        """
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,                  # "BUY" or "SELL"
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "MARKET",  # "MARKET" or "LIMIT"
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submits an order through the broker.
        Returns standardized execution dictionary.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancels an open order."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Queries status of an order."""
        pass

    @abstractmethod
    def get_audit_ledger(self) -> List[Dict[str, Any]]:
        """Returns the complete, immutable transaction ledger."""
        pass

    @abstractmethod
    def force_eod_square_off(self, symbol: str, quantity: int, mid_price: float) -> Dict[str, Any]:
        """Mandatory 15:15 IST intraday position liquidation."""
        pass
