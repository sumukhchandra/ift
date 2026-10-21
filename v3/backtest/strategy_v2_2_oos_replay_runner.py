#!/usr/bin/env python3
"""
v3/backtest/strategy_v2_2_oos_replay_runner.py
Executes the FROZEN Strategy V2.2 on the Out-of-Sample Replay window (Sep 28 – Oct 1, 2026).
Classification: HISTORICAL OUT-OF-SAMPLE REPLAY (Not Live Forward Paper).
Strictly air-gapped: LIVE_TRADING=False, ALLOW_REAL_ORDERS=False.
"""

import os
import sys
import csv
import json
from datetime import datetime, time
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Windows UTF-8 configuration
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker
from v3.execution.edge_friction_gate import EdgeFrictionGate, EdgeFrictionEvaluation
from v3.strategy.v2_1_relative_strength_trend import StrategyV2_1RelativeStrength
from v3.analytics.performance import PerformanceAnalytics


class StrategyV2_2OOSReplayEngine:
    def __init__(
        self,
        symbols: List[str],
        data_dir: str,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        max_positions: int = 2,
        trade_id_offset: int = 7,  # Trades #01-#07 are in baseline
    ):
        self.symbols = symbols
        self.data_dir = data_dir
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions
        self.trade_id_offset = trade_id_offset

        # Enforce air-gap safety check
        env_live = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
        env_allow = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"
        if env_live or env_allow:
            raise RuntimeError("[CRITICAL_SAFETY] Live trading flags detected! Aborting.")

        # Broker configured exactly as baseline V2.2
        self.broker = RealisticSimulatedBroker(
            scenario="BASE",
            starting_cash=self.starting_capital,
            max_daily_loss=self.max_daily_loss,
            seed=505,
            max_positions=self.max_positions,
            allow_short=False,
            leverage=1.0,
        )

        # Cost Gate matching baseline V2.2
        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=3.0,
            slippage_bps=4.0,
            safety_margin_rs=0.50,
            min_net_expectancy_rs=0.25,
        )

        # Frozen strategy parameters (Target +1.50%, SL -0.75%, Trailing +0.80% -> +0.25%, Window 09:30-12:45)
        self.strategies: Dict[str, StrategyV2_1RelativeStrength] = {
            s: StrategyV2_1RelativeStrength(
                target_profit_pct=0.0150,
                stop_loss_pct=0.0075,
                trail_breakeven_pct=0.0080,
                volume_mult=1.25,
                entry_start=time(9, 30),
                entry_cutoff=time(12, 45),
            )
            for s in self.symbols
        }

        self.symbol_bars: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.recent_bars: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.all_timestamps: List[str] = []
        self._load_data()

    def _load_data(self):
        ts_set = set()
        for sym in self.symbols:
            fname = os.path.join(self.data_dir, f"{sym}_1m_oos.csv")
            if not os.path.exists(fname):
                print(f"[WARN] File not found: {fname}")
                continue
            self.symbol_bars[sym] = {}
            with open(fname, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row["timestamp"]
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    bar = {
                        "timestamp": dt,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(float(row["volume"])),
                        "symbol": sym,
                    }
                    self.symbol_bars[sym][ts] = bar
                    ts_set.add(ts)
        self.all_timestamps = sorted(list(ts_set))
        print(f"[+] Loaded {len(self.all_timestamps)} chronological timestamps across {len(self.symbols)} symbols.")

    def run_replay(self) -> Dict[str, Any]:
        equity_curve = [self.starting_capital]
        current_day = None

        total_signals_seen = 0
        signals_filtered_by_gate = 0
        signals_filtered_by_selection = 0

        # Detailed audit logging with entry/exit reasons
        enriched_trade_logs = []

        for ts in self.all_timestamps:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            bar_date = dt.date()

            # Daily rollover
            if current_day != bar_date:
                current_day = bar_date
                self.broker.realized_pnl_today = 0.0
                self.broker.circuit_breaker_tripped = False
                self.broker.circuit_breaker_reason = ""

            # Update bars for current minute
            current_minute_bars: Dict[str, Dict[str, Any]] = {}
            for sym in self.symbols:
                if sym in self.symbol_bars and ts in self.symbol_bars[sym]:
                    bar = self.symbol_bars[sym][ts]
                    current_minute_bars[sym] = bar
                    self.recent_bars[sym].append(bar)

            # 1. Position Management & Exits
            open_symbols = list(self.broker.positions.keys())
            for held_sym in open_symbols:
                if held_sym in current_minute_bars and held_sym in self.broker.positions:
                    pos = self.broker.positions[held_sym]
                    bar = current_minute_bars[held_sym]
                    setattr(pos, "last_price", bar["close"])

                    strat = self.strategies[held_sym]
                    dec = strat.evaluate_1m_bar(
                        bar_1m=bar,
                        recent_1m_bars=self.recent_bars[held_sym][-25:],
                        position=pos,
                    )
                    if dec.get("action") == "SELL":
                        exit_reason = dec.get("reason", "EXIT_SIGNAL")
                        order = self.broker.execute_order(
                            symbol=held_sym,
                            side="SELL",
                            requested_qty=pos.quantity,
                            mid_price=bar["close"],
                            bar_volume=bar["volume"],
                            signal_timestamp=dt,
                        )
                        # Find the trade log just closed
                        if self.broker.trade_logs:
                            last_t = self.broker.trade_logs[-1]
                            last_t["exit_reason"] = exit_reason
                            last_t["session_date"] = str(bar_date)

            # 2. Candidate Evaluation & Entries
            current_pos_count = len(self.broker.positions)
            if current_pos_count < self.max_positions and not self.broker.circuit_breaker_tripped:
                buy_candidates = []
                for sym, bar in current_minute_bars.items():
                    if sym in self.broker.positions:
                        continue

                    strat = self.strategies[sym]
                    dec = strat.evaluate_1m_bar(
                        bar_1m=bar,
                        recent_1m_bars=self.recent_bars[sym][-25:],
                        position=None,
                    )
                    if dec.get("action") == "BUY":
                        total_signals_seen += 1
                        mid_px = bar["close"]

                        # V2.2 Sizing: 50% allocation cap (Rs. 750) or remaining cash
                        allocation_cap = self.starting_capital / self.max_positions
                        max_cash_for_pos = min(self.broker.cash, allocation_cap if current_pos_count == 0 else self.broker.cash)
                        qty = int(max_cash_for_pos // mid_px)

                        if qty == 0 and current_pos_count == 0 and self.broker.cash >= mid_px:
                            qty = 1

                        if qty >= 1:
                            eval_res: EdgeFrictionEvaluation = self.edge_gate.evaluate_signal(
                                symbol=sym,
                                side="BUY",
                                quantity=qty,
                                mid_price=mid_px,
                                expected_move_pct=0.0150,
                            )
                            if eval_res.approved:
                                buy_candidates.append({
                                    "symbol": sym,
                                    "mid_price": mid_px,
                                    "quantity": qty,
                                    "volume": bar["volume"],
                                    "rs_score": dec.get("rs_score", 0.0),
                                    "entry_reason": dec.get("reason", "V2_1_QUALIFIED_LEADER_SIGNAL"),
                                })
                            else:
                                signals_filtered_by_gate += 1

                # 3. Relative Strength Selection
                if buy_candidates:
                    buy_candidates.sort(key=lambda x: x["rs_score"], reverse=True)
                    slots_avail = self.max_positions - len(self.broker.positions)
                    leaders = buy_candidates[:slots_avail]
                    signals_filtered_by_selection += max(0, len(buy_candidates) - len(leaders))

                    for leader in leaders:
                        req_cost = leader["mid_price"] * leader["quantity"]
                        if self.broker.cash >= req_cost:
                            order = self.broker.execute_order(
                                symbol=leader["symbol"],
                                side="BUY",
                                requested_qty=leader["quantity"],
                                mid_price=leader["mid_price"],
                                bar_volume=leader["volume"],
                                signal_timestamp=dt,
                            )
                            # Tag the pending position with entry metadata
                            if leader["symbol"] in self.broker.positions:
                                pos = self.broker.positions[leader["symbol"]]
                                setattr(pos, "entry_reason", leader["entry_reason"])
                                setattr(pos, "rs_score", leader["rs_score"])

            # 4. Mark to market equity
            state = self.broker.get_portfolio_state()
            equity_curve.append(state["true_equity"])

        # Number trades starting from offset + 1
        for idx, t in enumerate(self.broker.trade_logs, start=self.trade_id_offset + 1):
            t["trade_number"] = idx
            t["trade_id"] = f"TRD_V2_2_{idx:02d}"
            t["classification"] = "HISTORICAL_OUT_OF_SAMPLE_REPLAY"

        # Calculate metrics
        metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
            trade_logs=self.broker.trade_logs,
            starting_capital=self.starting_capital,
            equity_curve=equity_curve,
            total_spread=self.broker.total_spread_paid,
            total_slippage=self.broker.total_slippage_paid,
            total_brokerage=self.broker.total_brokerage_paid,
            total_taxes=self.broker.total_taxes_paid,
        )
        metrics["total_signals_seen"] = total_signals_seen
        metrics["signals_filtered_by_gate"] = signals_filtered_by_gate
        metrics["signals_filtered_by_selection"] = signals_filtered_by_selection
        metrics["trade_logs"] = self.broker.trade_logs
        metrics["equity_curve"] = equity_curve
        return metrics


def main():
    universe = ["HDFCBANK", "SBIN", "RELIANCE", "INFY", "AXISBANK", "TATASTEEL", "ICICIBANK", "BAJFINANCE"]
    data_dir = os.path.join(WORKSPACE_ROOT, "QA", "data", "oos_replay_sep28_oct01")

    print("=" * 88)
    print("  ALPHA NSE V2.2 — HISTORICAL OUT-OF-SAMPLE REPLAY ENGINE")
    print("  PERIOD: 2026-09-28 to 2026-10-01 (Sessions 6, 7, 8, 9)")
    print("  CLASSIFICATION: HISTORICAL OUT-OF-SAMPLE REPLAY (NOT LIVE FORWARD PAPER)")
    print("  AIR-GAP: LIVE_TRADING=False | ALLOW_REAL_ORDERS=False | REAL CAPITAL AT RISK: Rs. 0")
    print("=" * 88)

    engine = StrategyV2_2OOSReplayEngine(
        symbols=universe,
        data_dir=data_dir,
        starting_capital=1500.0,
        max_daily_loss=30.0,
        max_positions=2,
        trade_id_offset=7,  # Appending after baseline Trade #07
    )

    res = engine.run_replay()

    print("\n[HISTORICAL OUT-OF-SAMPLE REPLAY RESULTS (SEP 28 - OCT 01)]")
    print(f"  New OOS Replay Trades Executed: {res['total_trades']}")
    print(f"  Winning Trades / Losing:         {res['winning_trades']}W / {res['losing_trades']}L")
    print(f"  Win Rate (%):                    {res['win_rate_pct']:.2f}%")
    print(f"  Profit Factor:                   {res['profit_factor']:.2f}")
    print(f"  Gross Theoretical P&L:           Rs. {res['gross_pnl_rs']:+.2f}")
    print(f"  Total Friction Paid:             Rs. {res['total_friction_rs']:.2f}")
    print(f"    - Spread Cost:                 Rs. {res['spread_cost_rs']:.2f}")
    print(f"    - Slippage Cost:               Rs. {res['slippage_cost_rs']:.2f}")
    print(f"    - Brokerage:                   Rs. {res['brokerage_rs']:.2f}")
    print(f"    - Statutory Taxes:             Rs. {res['statutory_taxes_rs']:.2f}")
    print(f"  Net Realized P&L:                Rs. {res['net_pnl_rs']:+.2f}")
    print(f"  Net Expectancy Per Trade:        Rs. {res['net_expectancy_rs']:+.2f} / trade")
    print(f"  Max Drawdown (Rs. / %):          Rs. {res['max_drawdown_rs']:.2f} ({res['max_drawdown_pct']:.2f}%)")
    print(f"  Average Holding Time:            {res['avg_holding_minutes']:.1f} minutes")

    print("\nDETAILED NEW REPLAY TRADES (Trades #08 onward):")
    for t in res["trade_logs"]:
        exit_r = t.get("exit_reason", "EOD_OR_SIGNAL")
        print(f"  Trade #{t['trade_number']:02d} [{t['symbol']:10s}]: {t['entry_time']} -> {t['exit_time']} | Qty: {t['quantity']} | Gross: Rs. {t['gross_pnl']:+6.2f} | Fric: Rs. {t['total_friction']:4.2f} | Net: Rs. {t['net_pnl']:+6.2f} | Hold: {t['holding_minutes']}m | Exit: {exit_r}")

    # Load baseline ledger (Trades 1-7) to produce unified master ledger with separate classification
    baseline_ledger_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "STRATEGY_V2_2_TRADE_LEDGER.json")
    with open(baseline_ledger_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    baseline_trades = baseline_data.get("trade_logs", [])
    for idx, t in enumerate(baseline_trades, start=1):
        t["trade_number"] = idx
        t["trade_id"] = f"TRD_V2_2_{idx:02d}"
        t["classification"] = "HISTORICAL_VALIDATION_BASELINE"

    combined_trades = baseline_trades + res["trade_logs"]

    # Save comprehensive master ledger
    master_ledger = {
        "metadata": {
            "strategy": "AlphaNSE V2.2",
            "frozen_parameters": {
                "target_profit_pct": 0.0150,
                "stop_loss_pct": 0.0075,
                "trail_breakeven_pct": 0.0080,
                "entry_window": "09:30 - 12:45 IST",
                "square_off": "15:15 IST",
                "max_positions": 2,
                "capital": 1500.0,
            },
            "sample_counts": {
                "category_a_historical_oos_replay_trades": len(res["trade_logs"]),
                "category_a_baseline_historical_trades": len(baseline_trades),
                "category_b_genuine_live_forward_paper_trades": 0,
                "total_observations_across_all_categories": len(combined_trades),
            },
            "safety_status": {
                "live_trading": False,
                "allow_real_orders": False,
                "_is_live_authorized": False,
                "real_capital_at_risk": 0.0,
            }
        },
        "oos_replay_metrics": {
            "trades": res["total_trades"],
            "wins": res["winning_trades"],
            "losses": res["losing_trades"],
            "win_rate_pct": res["win_rate_pct"],
            "gross_pnl_rs": res["gross_pnl_rs"],
            "total_friction_rs": res["total_friction_rs"],
            "net_pnl_rs": res["net_pnl_rs"],
            "net_expectancy_rs": res["net_expectancy_rs"],
            "profit_factor": res["profit_factor"],
            "max_drawdown_rs": res["max_drawdown_rs"],
            "avg_holding_minutes": res["avg_holding_minutes"],
        },
        "all_trade_records": combined_trades,
    }

    out_ledger_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "STRATEGY_V2_2_HISTORICAL_OOS_LEDGER.json")
    with open(out_ledger_path, "w", encoding="utf-8") as f:
        json.dump(master_ledger, f, indent=2)

    print(f"\n[SUCCESS] Master ledger saved to: {out_ledger_path}")


if __name__ == "__main__":
    main()
