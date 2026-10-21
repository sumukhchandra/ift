"""
Indian Stock Market (NSE) Intraday Equity Cost Engine for AlphaNSE V2.
Accurate Zerodha intraday equity rate schedule (2025-2026).
Provides explicit decomposition: fixed/capped fees, proportional statutory taxes, and total friction.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class CostBreakdown:
    capital: float
    buy_value: float
    sell_value: float
    brokerage: float            # min(0.03%, Rs 20) per side
    stt: float                  # 0.025% on sell side
    exchange_charges: float     # 0.00307% per side
    sebi_fees: float            # Rs 10 per crore (0.0001%) per side
    gst: float                  # 18% on (brokerage + exchange + sebi)
    stamp_duty: float           # 0.003% on buy side
    slippage: float             # Modeled execution slippage
    fixed_or_capped_cost: float # Brokerage component
    proportional_statutory_cost: float # STT + Exchange + SEBI + GST + Stamp
    total_cost: float           # All friction combined
    gross_profit: float
    net_profit: float
    net_return_pct: float


class IndiaCostEngine:
    """
    Computes penny-for-penny frictions for NSE Cash Intraday trades.
    """

    def __init__(self, profit_tax_pct: float = 0.25):
        self.brokerage_pct = 0.0003          # 0.03%
        self.brokerage_flat_cap = 20.0       # Rs. 20 cap per order
        self.stt_sell_pct = 0.00025          # 0.025% on sell side
        self.exchange_pct = 0.0000307        # 0.00307% per side
        self.sebi_pct = 0.000001             # Rs. 10 per crore (0.0001%)
        self.gst_pct = 0.18                  # 18% on fees
        self.stamp_duty_buy_pct = 0.00003    # 0.003% on buy side
        self.default_slippage_bps = 2.5      # 2.5 bps (0.025%)
        self.profit_tax_pct = profit_tax_pct # STCG buffer

    def brokerage_per_side(self, trade_value: float) -> float:
        """min(trade_value * 0.03%, Rs. 20)."""
        return min(trade_value * self.brokerage_pct, self.brokerage_flat_cap)

    def calculate_roundtrip_cost(
        self,
        capital: float,
        gross_return: float,
        slippage_bps: float = 2.5
    ) -> CostBreakdown:
        """
        Calculate complete roundtrip cost breakdown for entering with `capital` and exiting with `gross_return`.
        """
        buy_value = capital
        sell_value = capital * (1.0 + gross_return)

        # 1. Brokerage (both sides)
        buy_brokerage = self.brokerage_per_side(buy_value)
        sell_brokerage = self.brokerage_per_side(sell_value)
        total_brokerage = buy_brokerage + sell_brokerage

        # 2. Statutory Proportional Charges
        stt = sell_value * self.stt_sell_pct
        exchange = (buy_value + sell_value) * self.exchange_pct
        sebi = (buy_value + sell_value) * self.sebi_pct
        gst = (total_brokerage + exchange + sebi) * self.gst_pct
        stamp = buy_value * self.stamp_duty_buy_pct

        # 3. Slippage
        slippage_pct = (slippage_bps / 10000.0)
        slippage = (buy_value + sell_value) * slippage_pct

        # Totals
        fixed_capped = total_brokerage
        proportional_statutory = stt + exchange + sebi + gst + stamp
        total_cost = fixed_capped + proportional_statutory + slippage

        gross_profit = sell_value - buy_value
        profit_after_costs = gross_profit - total_cost
        tax = max(0.0, profit_after_costs * self.profit_tax_pct)
        net_profit = profit_after_costs - tax
        net_return_pct = (net_profit / capital) * 100.0 if capital > 0 else 0.0

        return CostBreakdown(
            capital=round(capital, 2),
            buy_value=round(buy_value, 2),
            sell_value=round(sell_value, 2),
            brokerage=round(total_brokerage, 2),
            stt=round(stt, 2),
            exchange_charges=round(exchange, 4),
            sebi_fees=round(sebi, 4),
            gst=round(gst, 4),
            stamp_duty=round(stamp, 4),
            slippage=round(slippage, 2),
            fixed_or_capped_cost=round(fixed_capped, 2),
            proportional_statutory_cost=round(proportional_statutory, 2),
            total_cost=round(total_cost, 2),
            gross_profit=round(gross_profit, 2),
            net_profit=round(net_profit, 2),
            net_return_pct=round(net_return_pct, 4)
        )

    def is_trade_viable(self, capital: float, predicted_gross_return: float, min_net_pct: float = 0.0005) -> bool:
        """Viability gate: returns True only if predicted return yields positive net profit after ALL costs."""
        breakdown = self.calculate_roundtrip_cost(capital, predicted_gross_return)
        return breakdown.net_profit >= (capital * min_net_pct)
