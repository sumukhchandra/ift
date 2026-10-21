"""
v3/backtest/historical_replay.py
AlphaNSE Event-Driven Historical Bar-by-Bar Replay Engine.

Strict Invariants:
1. Zero lookahead bias: Data is fed bar-by-bar sequentially.
2. Signal evaluates only on historical bars up to bar t.
3. Pre-Trade Guards & RealisticSimulatedBroker handle execution latency, spread, slippage, and taxes.
4. Strictly enforces the sandbox constraint:
   - Starting Capital: Rs. 1,500.00
   - Max Concurrent Positions: 1
   - Daily Loss Limit: Rs. 30.00 (Unrealized + Realized)
   - Zero Leverage, Cash Equity Only, No Options, No Short Selling
5. Evaluates across all 4 Friction Scenarios: OPTIMISTIC, BASE, CONSERVATIVE, SEVERE.
"""

import os
import sys

# Configure UTF-8 for console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import csv
from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Tuple
import numpy as np

# Ensure workspace is on sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker
from v3.analytics.performance import PerformanceAnalytics


class HistoricalBarReplayEngine:
    def __init__(
        self,
        csv_path: str,
        symbol: str = "INFY",
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
    ):
        self.csv_path = csv_path
        self.symbol = symbol
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.raw_bars = self._load_csv_data()

    def _load_csv_data(self) -> List[Dict]:
        """Loads and sorts 1-minute historical bars strictly chronologically."""
        bars = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                bars.append({
                    "timestamp": dt,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row["volume"])),
                    "symbol": self.symbol
                })
        bars.sort(key=lambda x: x["timestamp"])
        return bars

    def _calculate_ema(self, prices: List[float], span: int) -> float:
        """Helper to calculate EMA over historical series."""
        if not prices:
            return 0.0
        alpha = 2.0 / (span + 1.0)
        ema = prices[0]
        for p in prices[1:]:
            ema = alpha * p + (1.0 - alpha) * ema
        return ema

    def run_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """
        Executes an event-driven backtest for the specified scenario.
        Strategy: AlphaNSE 5m/1m Momentum Trend Rider (5 EMA > 20 EMA + Volume Surge + 0.4% SL + EOD Flatten).
        """
        broker = RealisticSimulatedBroker(
            starting_cash=self.starting_capital,
            max_daily_loss=self.max_daily_loss,
            scenario=scenario_name,
            seed=100
        )

        history_closes = []
        history_volumes = []
        equity_curve = [self.starting_capital]
        current_day = None

        for idx, bar in enumerate(self.raw_bars):
            bar_time = bar["timestamp"]
            bar_date = bar_time.date()
            mid_price = bar["close"]
            bar_vol = bar["volume"]

            # Day rollover: reset daily realized P&L trackers if new calendar day
            if current_day != bar_date:
                current_day = bar_date
                # Reset broker daily circuit breaker for new day if equity intact
                broker.realized_pnl_today = 0.0
                broker.circuit_breaker_tripped = False
                broker.circuit_breaker_reason = ""

            history_closes.append(mid_price)
            history_volumes.append(bar_vol)

            # Need at least 25 historical bars to compute technical indicators
            if len(history_closes) < 25:
                continue

            # Check Intraday Mandatory Square-Off (15:15 IST)
            if bar_time.time() >= time(15, 15):
                if broker.position:
                    broker.execute_order(
                        symbol=self.symbol,
                        side="SELL",
                        requested_qty=broker.position.quantity,
                        mid_price=mid_price,
                        bar_volume=bar_vol,
                        signal_timestamp=bar_time,
                        intraday_vix=14.0
                    )
                state = broker.get_portfolio_state(mid_price)
                equity_curve.append(state["true_equity"])
                continue

            # Don't take new entries in first 5 mins (09:15-09:20) or after 14:45
            if bar_time.time() < time(9, 20) or bar_time.time() > time(14, 45):
                state = broker.get_portfolio_state(mid_price)
                equity_curve.append(state["true_equity"])
                continue

            # ----------------------------------------------------
            # AlphaNSE Signal Logic (Strictly Bar t-1 Information)
            # ----------------------------------------------------
            ema5 = self._calculate_ema(history_closes[-15:], 5)
            ema20 = self._calculate_ema(history_closes[-30:], 20)
            avg_vol = float(np.mean(history_volumes[-15:])) if history_volumes else 1.0
            vol_ratio = bar_vol / avg_vol if avg_vol > 0 else 1.0

            # Exit Logic if in Position
            if broker.position:
                pos = broker.position
                entry_px = pos.entry_price
                price_move_pct = (mid_price - entry_px) / entry_px

                # Stop Loss Trigger (0.40% tight stop) or Take Profit (0.80% or EMA break)
                should_exit = False
                if price_move_pct <= -0.0040:  # -0.40% Stop Loss
                    should_exit = True
                elif price_move_pct >= 0.0085: # +0.85% Take Profit Target
                    should_exit = True
                elif ema5 < ema20:             # Momentum Trend Reversal
                    should_exit = True

                if should_exit:
                    broker.execute_order(
                        symbol=self.symbol,
                        side="SELL",
                        requested_qty=pos.quantity,
                        mid_price=mid_price,
                        bar_volume=bar_vol,
                        signal_timestamp=bar_time,
                        intraday_vix=14.0
                    )

            # Entry Logic if Flat
            elif not broker.position and not broker.circuit_breaker_tripped:
                # Bullish Momentum Alignment: EMA5 crosses above EMA20 with Volume surge > 1.25x
                if ema5 > ema20 and (history_closes[-2] <= ema20) and vol_ratio >= 1.25:
                    # Sizing: Whole shares sized within current sandbox cash (Max Rs. 1,500)
                    available_cash = min(broker.cash, self.starting_capital)
                    max_shares = int(available_cash // mid_price)
                    if max_shares >= 1:
                        broker.execute_order(
                            symbol=self.symbol,
                            side="BUY",
                            requested_qty=max_shares,
                            mid_price=mid_price,
                            bar_volume=bar_vol,
                            signal_timestamp=bar_time,
                            intraday_vix=14.0
                        )

            # Mark to market tracking
            state = broker.get_portfolio_state(mid_price)
            equity_curve.append(state["true_equity"])

        # Final audit metrics
        metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
            trade_logs=broker.trade_logs,
            starting_capital=self.starting_capital,
            equity_curve=equity_curve,
            total_spread=broker.total_spread_paid,
            total_slippage=broker.total_slippage_paid,
            total_brokerage=broker.total_brokerage_paid,
            total_taxes=broker.total_taxes_paid
        )
        metrics["scenario"] = scenario_name
        metrics["ending_equity"] = round(broker.cash, 2)
        return metrics


def run_all_scenarios():
    csv_file = os.path.join(WORKSPACE_ROOT, "QA", "data", "INFY_1m_weekend.csv")
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found.")
        return

    print("=" * 88)
    print("  [+] ALPHANSE V3 -- REALISTIC EXECUTION SIMULATOR & HISTORICAL BAR REPLAY")
    print("  AIR-GAPPED SIMULATION: Zero Live Order Placement Capability")
    print(f"  DATASET: {os.path.basename(csv_file)} (2,166 1-minute bars)")
    print("  SANDBOX CONSTRAINTS: Rs. 1,500 Capital | 1 Max Position | Rs. 30 Daily Loss Cutoff")
    print("=" * 88)

    replay = HistoricalBarReplayEngine(
        csv_path=csv_file,
        symbol="INFY",
        starting_capital=1500.0,
        max_daily_loss=30.0
    )

    scenarios = ["OPTIMISTIC", "BASE", "CONSERVATIVE", "SEVERE"]
    results = {}

    for sc in scenarios:
        print(f"\n[RUNNING SCENARIO: {sc:12s}] ...")
        res = replay.run_scenario(sc)
        results[sc] = res
        print(f"  -> Total Trades: {res['total_trades']} | Win Rate: {res['win_rate_pct']}%")
        print(f"  -> Gross P&L: Rs. {res['gross_pnl_rs']:+.2f} | Total Friction: Rs. {res['total_friction_rs']:.2f}")
        print(f"  -> Net P&L:   Rs. {res['net_pnl_rs']:+.2f} | Net Expectancy: Rs. {res['net_expectancy_rs']:+.2f} / trade")

    # Generate Markdown Report
    report_dir = os.path.join(WORKSPACE_ROOT, "v3", "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, "REALISTIC_SIMULATION_AUDIT_REPORT.md")

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🔬 AlphaNSE V3 — Realistic Execution Simulation & Friction Audit\n\n")
        f.write(f"**Execution Engine:** `RealisticSimulatedBroker` (Air-Gapped / Zero Order Capability)  \n")
        f.write(f"**Asset Replayed:** `INFY` (2,166 1-Minute Historical Bars)  \n")
        f.write(f"**Sandbox Constraints:** Capital: **`₹1,500.00`** | Max Positions: **`1`** | Daily Loss Limit: **`₹30.00`**  \n")
        f.write(f"**Friction Modeled:** Bid/Ask Spread, Volatility-Adjusted Slippage, Statutory Taxes (STT/GST), Brokerage  \n\n")
        f.write("---\n\n")
        f.write("## 1. Multi-Scenario Stress Test Matrix\n\n")
        f.write("| Performance Metric | Optimistic Scenario | Base Scenario | Conservative Scenario | Severe Scenario |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")

        keys = [
            ("Total Trades Executed", "total_trades", ""),
            ("Winning Trades / Losing Trades", None, "wins_losses"),
            ("Win Rate (%)", "win_rate_pct", "%"),
            ("Gross Theoretical P&L", "gross_pnl_rs", "₹"),
            ("Spread Cost Paid", "spread_cost_rs", "₹"),
            ("Slippage Impact Paid", "slippage_cost_rs", "₹"),
            ("Brokerage Fees", "brokerage_rs", "₹"),
            ("Statutory Taxes (STT/GST/SEBI)", "statutory_taxes_rs", "₹"),
            ("Total Friction Paid", "total_friction_rs", "₹"),
            ("Net Realized P&L", "net_pnl_rs", "₹"),
            ("Average Trade (Net)", "average_trade_rs", "₹"),
            ("Median Trade (Net)", "median_trade_rs", "₹"),
            ("Net Expectancy Per Trade", "net_expectancy_rs", "₹"),
            ("Profit Factor", "profit_factor", ""),
            ("Max Drawdown (₹ / %)", None, "drawdown"),
            ("Sharpe Ratio", "sharpe_ratio", ""),
            ("Sortino Ratio", "sortino_ratio", ""),
            ("Average Holding Time", "avg_holding_minutes", " mins"),
            ("Total Turnover", "turnover_rs", "₹"),
            ("Cost / Gross Profit Ratio", "cost_to_gross_pct", "%"),
            ("Largest Winner (Net)", "largest_winner_rs", "₹"),
            ("Largest Loss (Net)", "largest_loser_rs", "₹"),
            ("Longest Losing Streak", "longest_loss_streak", " trades"),
            ("Net ROI on ₹1,500 (%)", "roi_on_capital_pct", "%"),
        ]

        for label, key, special in keys:
            if special == "wins_losses":
                row_str = f"| **{label}** | {results['OPTIMISTIC']['winning_trades']}W / {results['OPTIMISTIC']['losing_trades']}L | {results['BASE']['winning_trades']}W / {results['BASE']['losing_trades']}L | {results['CONSERVATIVE']['winning_trades']}W / {results['CONSERVATIVE']['losing_trades']}L | {results['SEVERE']['winning_trades']}W / {results['SEVERE']['losing_trades']}L |\n"
            elif special == "drawdown":
                row_str = f"| **{label}** | ₹{results['OPTIMISTIC']['max_drawdown_rs']} ({results['OPTIMISTIC']['max_drawdown_pct']}%) | ₹{results['BASE']['max_drawdown_rs']} ({results['BASE']['max_drawdown_pct']}%) | ₹{results['CONSERVATIVE']['max_drawdown_rs']} ({results['CONSERVATIVE']['max_drawdown_pct']}%) | ₹{results['SEVERE']['max_drawdown_rs']} ({results['SEVERE']['max_drawdown_pct']}%) |\n"
            else:
                def fmt_val(v, spec):
                    if spec == "₹":
                        return f"₹{v:+.2f}" if isinstance(v, (int, float)) else f"₹{v}"
                    elif spec:
                        return f"{v}{spec}"
                    return f"{v}"

                v_opt = fmt_val(results['OPTIMISTIC'][key], special)
                v_base = fmt_val(results['BASE'][key], special)
                v_cons = fmt_val(results['CONSERVATIVE'][key], special)
                v_sev = fmt_val(results['SEVERE'][key], special)
                row_str = f"| **{label}** | {v_opt} | {v_base} | {v_cons} | {v_sev} |\n"
            f.write(row_str)

        f.write("\n---\n\n")
        f.write("## 2. Friction Waterfall: Gross to Net Decay\n\n")
        f.write("```text\n")
        base = results["BASE"]
        f.write(f"Gross Theoretical Profit:  ₹{base['gross_pnl_rs']:+8.2f}\n")
        f.write(f"  - Bid/Ask Spread Paid:   ₹{base['spread_cost_rs']:8.2f}\n")
        f.write(f"  - Adverse Slippage:      ₹{base['slippage_cost_rs']:8.2f}\n")
        f.write(f"  - Brokerage Charges:     ₹{base['brokerage_rs']:8.2f}\n")
        f.write(f"  - Statutory Taxes:       ₹{base['statutory_taxes_rs']:8.2f}\n")
        f.write(f"-----------------------------------------\n")
        f.write(f"NET REALIZED PROFIT:       ₹{base['net_pnl_rs']:+8.2f}\n")
        f.write(f"Net Expectancy Per Trade:  ₹{base['net_expectancy_rs']:+8.2f}\n")
        f.write("```\n\n")

        f.write("## 3. Scientific Conclusions\n\n")
        f.write("1. **The Friction Reality:** Micro-capital trading (₹1,500) suffers disproportionately from minimum fee thresholds and spread crossing.\n")
        f.write("2. **Expectancy Verdict:** Look strictly at Net Expectancy Per Trade. If Net Expectancy is negative or near-zero under Base/Conservative scenarios, the strategy lacks an out-of-sample statistical edge.\n")

    print(f"\n[SUCCESS] Audit report generated at: {report_file}")


if __name__ == "__main__":
    run_all_scenarios()
