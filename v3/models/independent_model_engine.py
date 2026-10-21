"""
AlphaNSE V3 — Independent Model Trading Engine & Tournament Leaderboard.

Allows every model to trade independently using its own unique brain, timeframe,
and decision criteria:
  - Model 01: V2_15M       (15-Minute Intraday Momentum Regressor)
  - Model 02: HYPO001      (30-Minute Midday Trend Follower)
  - Model 03: HYPO002      (60-Minute High-Beta Volatility Expansion)
  - Model 04: HYPO003      (15-Minute Downside Short-Sparsity Regressor)
  - Model 05: V3_60M       (60-Minute Adaptive Multi-Factor Master)
  - Model 06: SMC_4CONF_920 (5-Minute SMC 4-Confirmation & 9:20 Straddle)

Tracks independent sub-portfolios, trade records, win rates, net P&L,
and produces a competitive tournament leaderboard to determine which model performs best.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from v3.config.multimodel_config import ACTIVE_MODEL_SPECS
from v2.risk.cost_engine import IndiaCostEngine

logger = logging.getLogger(__name__)


@dataclass
class IndependentTradeRecord:
    trade_id: str
    model_id: str
    symbol: str
    direction: int                      # +1 for BUY, -1 for SELL
    entry_time: str
    exit_time: str
    holding_minutes: int
    entry_price: float
    exit_price: float
    quantity: int
    notional: float
    gross_return_bps: float
    gross_pnl_rupees: float
    brokerage_rupees: float
    statutory_fees_rupees: float
    slippage_rupees: float
    total_friction_rupees: float
    net_pnl_rupees: float
    net_return_pct: float
    exit_reason: str
    is_win: bool


@dataclass
class ModelTournamentScorecard:
    rank: int
    model_id: str
    model_name: str
    strategy_type: str
    timeframe: str
    starting_capital: float
    ending_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    gross_pnl_rupees: float
    total_friction_rupees: float
    net_pnl_rupees: float
    roi_pct: float
    profit_factor: float
    best_symbol: str
    trades: List[Dict[str, Any]]


class IndependentModelTradingEngine:
    """
    Simulates and tracks independent trading accounts for each model.
    """

    def __init__(
        self,
        capital_per_model: float = 5000.0,
        min_net_edge_rupees: float = 0.80,
        max_positions_per_model: int = 2
    ):
        self.capital_per_model = capital_per_model
        self.min_net_edge_rupees = min_net_edge_rupees
        self.max_positions_per_model = max_positions_per_model
        self.cost_engine = IndiaCostEngine()

    def run_session_tournament(
        self,
        session_date: str,
        predictions_by_model: Dict[str, Any],
        intraday_market_slices: Optional[Dict[str, Any]] = None,
        artifacts_output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes independent trading decisions for each active model and returns the leaderboard.
        """
        model_results: Dict[str, ModelTournamentScorecard] = {}
        all_model_trades: Dict[str, List[IndependentTradeRecord]] = {}

        # Default intraday market price movements if not passed (e.g. from Session 6 actuals)
        # Includes equities + ^NSEI (NIFTY 50 Index)
        default_market_moves = {
            # Symbol: {price, 15m_return_bps, 30m_return_bps, 60m_return_bps}
            "INFY.NS":       {"base_price": 1040.50, "15m": 15.1, "30m": 27.3, "60m": 38.5},
            "TATACAP.NS":    {"base_price": 344.55,  "15m": 12.6, "30m": 22.7, "60m": 32.0},
            "RELIANCE.NS":   {"base_price": 1246.40, "15m": 10.2, "30m": 18.5, "60m": 26.2},
            "^NSEI":         {"base_price": 24850.0, "15m": 8.5,  "30m": 14.2, "60m": 22.5},
            "BAJFINANCE.NS": {"base_price": 7120.00, "15m": 4.1,  "30m": 6.5,  "60m": 8.0},
            "SBIN.NS":       {"base_price": 782.50,  "15m": 3.2,  "30m": 5.1,  "60m": 7.5},
            "ICICIBANK.NS":  {"base_price": 1215.00, "15m": 3.0,  "30m": 4.8,  "60m": 7.2},
            "TCS.NS":        {"base_price": 3890.00, "15m": 1.5,  "30m": 2.2,  "60m": 3.5},
            "HDFCBANK.NS":   {"base_price": 1620.00, "15m": -2.0, "30m": -1.5, "60m": 1.0},
            "BHARTIARTL.NS": {"base_price": 1850.00, "15m": -8.5, "30m": -12.0, "60m": -15.5},
            "AXISBANK.NS":   {"base_price": 1180.00, "15m": -6.2, "30m": -8.5, "60m": -11.0},
        }
        market_moves = intraday_market_slices or default_market_moves

        for model_id, spec in ACTIVE_MODEL_SPECS.items():
            model_preds = predictions_by_model.get(model_id, {})
            horizon_mins = spec.get("target_horizon_minutes", 15)
            model_type = spec.get("model_type", "REGRESSOR")
            model_name = spec.get("name", model_id)
            strategy_desc = spec.get("description", "")

            # Filter candidates where this model has positive conviction
            candidate_list = []
            for sym, pred in model_preds.items():
                if isinstance(pred, dict):
                    direction = pred.get("direction", 0)
                    expected_bps = pred.get("predicted_return_bps") or pred.get("expected_gross_return_bps", 0.0)
                    conf = pred.get("confidence", 0.5)
                else:
                    direction = getattr(pred, "direction", 0)
                    expected_bps = getattr(pred, "predicted_return_bps", 0.0)
                    conf = getattr(pred, "confidence", 0.5)

                if direction == 0:
                    continue

                sym_market = market_moves.get(sym, {"base_price": 1000.0, "15m": 0.0, "30m": 0.0, "60m": 0.0})
                price = sym_market["base_price"]

                # Sizing: Whole-share integer allocation (up to 50% capital per position, max 2 positions)
                max_alloc = self.capital_per_model / float(self.max_positions_per_model)
                affordable_qty = int(max_alloc // price)
                if affordable_qty < 1:
                    # If single share exceeds max_alloc but is <= total capital, allow 1 share
                    if price <= self.capital_per_model * 0.95:
                        affordable_qty = 1
                    else:
                        continue

                notional = affordable_qty * price
                expected_gross_rupees = notional * (abs(expected_bps) / 10000.0)
                cost_breakdown = self.cost_engine.calculate_roundtrip_cost(
                    capital=notional,
                    gross_return=abs(expected_bps) / 10000.0
                )
                expected_friction = cost_breakdown.total_cost + (notional * 0.0002) # plus realistic slippage
                expected_net_rupees = expected_gross_rupees - expected_friction

                if expected_net_rupees >= self.min_net_edge_rupees:
                    candidate_list.append({
                        "symbol": sym,
                        "direction": direction,
                        "expected_bps": expected_bps,
                        "expected_net_rupees": expected_net_rupees,
                        "confidence": conf,
                        "quantity": affordable_qty,
                        "price": price,
                        "notional": notional
                    })

            # Sort candidate opportunities by expected net return descending
            candidate_list.sort(key=lambda x: x["expected_net_rupees"], reverse=True)
            chosen_allocations = candidate_list[:self.max_positions_per_model]

            # Execute independent trades for this model
            executed_trades: List[IndependentTradeRecord] = []
            available_cash = self.capital_per_model

            for t_idx, alloc in enumerate(chosen_allocations):
                sym = alloc["symbol"]
                direction = alloc["direction"]
                qty = alloc["quantity"]
                entry_p = alloc["price"]
                notional = qty * entry_p

                if notional > available_cash:
                    qty = int(available_cash // entry_p)
                    if qty < 1:
                        continue
                    notional = qty * entry_p

                available_cash -= notional

                # Horizon determine exit price
                sym_data = market_moves.get(sym, {"base_price": entry_p, "15m": 15.0, "30m": 25.0, "60m": 35.0})
                if horizon_mins <= 5:
                    realized_bps = sym_data.get("15m", 15.0) * 0.6  # 5-min fast scalp
                    exit_time_str = "09:20:00"
                elif horizon_mins <= 15:
                    realized_bps = sym_data.get("15m", 15.0)
                    exit_time_str = "09:30:00"
                elif horizon_mins <= 30:
                    realized_bps = sym_data.get("30m", 25.0)
                    exit_time_str = "09:45:00"
                else:
                    realized_bps = sym_data.get("60m", 35.0)
                    exit_time_str = "10:15:00"

                # If short, directional return is reversed
                actual_move_bps = realized_bps * direction
                exit_p = entry_p * (1.0 + actual_move_bps / 10000.0)
                gross_rupees = notional * (actual_move_bps / 10000.0)

                cost_res = self.cost_engine.calculate_roundtrip_cost(
                    capital=notional,
                    gross_return=actual_move_bps / 10000.0
                )
                brokerage = cost_res.brokerage
                statutory = cost_res.proportional_statutory_cost
                slippage = notional * 0.0002
                friction = brokerage + statutory + slippage
                net_rupees = gross_rupees - friction
                net_pct = (net_rupees / notional) * 100.0

                trade_rec = IndependentTradeRecord(
                    trade_id=f"TRD_{model_id}_{session_date}_{t_idx+1:02d}",
                    model_id=model_id,
                    symbol=sym,
                    direction=direction,
                    entry_time="09:15:00",
                    exit_time=exit_time_str,
                    holding_minutes=horizon_mins,
                    entry_price=round(entry_p, 2),
                    exit_price=round(exit_p, 2),
                    quantity=qty,
                    notional=round(notional, 2),
                    gross_return_bps=round(actual_move_bps, 2),
                    gross_pnl_rupees=round(gross_rupees, 2),
                    brokerage_rupees=round(brokerage, 2),
                    statutory_fees_rupees=round(statutory, 2),
                    slippage_rupees=round(slippage, 2),
                    total_friction_rupees=round(friction, 2),
                    net_pnl_rupees=round(net_rupees, 2),
                    net_return_pct=round(net_pct, 3),
                    exit_reason=f"HORIZON_COMPLETED_{horizon_mins}M",
                    is_win=net_rupees > 0.0
                )
                executed_trades.append(trade_rec)

            all_model_trades[model_id] = executed_trades

            # Compute Model Scorecard
            tot_trades = len(executed_trades)
            wins = sum(1 for t in executed_trades if t.is_win)
            losses = tot_trades - wins
            win_rate = (wins / tot_trades * 100.0) if tot_trades > 0 else 0.0
            tot_gross = sum(t.gross_pnl_rupees for t in executed_trades)
            tot_fric = sum(t.total_friction_rupees for t in executed_trades)
            tot_net = sum(t.net_pnl_rupees for t in executed_trades)
            ending_cap = self.capital_per_model + tot_net
            roi_pct = (tot_net / self.capital_per_model) * 100.0

            gross_wins = sum(t.gross_pnl_rupees for t in executed_trades if t.is_win)
            gross_losses = abs(sum(t.gross_pnl_rupees for t in executed_trades if not t.is_win))
            profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (99.0 if tot_net > 0 else 0.0)

            best_sym = executed_trades[0].symbol if executed_trades else "N/A"

            scorecard = ModelTournamentScorecard(
                rank=0,  # Will be ranked below
                model_id=model_id,
                model_name=model_name,
                strategy_type=strategy_desc,
                timeframe=f"{horizon_mins}m",
                starting_capital=self.capital_per_model,
                ending_capital=round(ending_cap, 2),
                total_trades=tot_trades,
                winning_trades=wins,
                losing_trades=losses,
                win_rate_pct=round(win_rate, 1),
                gross_pnl_rupees=round(tot_gross, 2),
                total_friction_rupees=round(tot_fric, 2),
                net_pnl_rupees=round(tot_net, 2),
                roi_pct=round(roi_pct, 2),
                profit_factor=round(profit_factor, 2),
                best_symbol=best_sym,
                trades=[asdict(t) for t in executed_trades]
            )
            model_results[model_id] = scorecard

        # Rank models by net_pnl_rupees descending, then by win_rate_pct
        ranked_models = sorted(
            model_results.values(),
            key=lambda x: (x.net_pnl_rupees, x.win_rate_pct, x.total_trades),
            reverse=True
        )
        for rank_idx, m_card in enumerate(ranked_models):
            m_card.rank = rank_idx + 1

        leaderboard_data = {
            "session_date": session_date,
            "capital_per_model": self.capital_per_model,
            "min_net_edge_hurdle": self.min_net_edge_rupees,
            "total_models": len(ranked_models),
            "top_performer": ranked_models[0].model_id if ranked_models else "N/A",
            "leaderboard": [asdict(m) for m in ranked_models]
        }

        # Write artifacts if directory specified
        if artifacts_output_dir:
            os.makedirs(artifacts_output_dir, exist_ok=True)

            # 1. Master Tournament Leaderboard JSON
            board_json_path = os.path.join(artifacts_output_dir, "MODEL_INDEPENDENT_LEADERBOARD.json")
            with open(board_json_path, "w", encoding="utf-8") as f:
                json.dump(leaderboard_data, f, indent=2)

            # 2. Master Tournament Leaderboard Markdown Report
            board_md_path = os.path.join(artifacts_output_dir, "MODEL_INDEPENDENT_LEADERBOARD.md")
            with open(board_md_path, "w", encoding="utf-8") as f:
                f.write(self._generate_leaderboard_markdown(leaderboard_data))

            # 3. Individual Model Trades JSON
            for m_id, trades in all_model_trades.items():
                m_trades_path = os.path.join(artifacts_output_dir, f"INDIVIDUAL_TRADES_{m_id}.json")
                with open(m_trades_path, "w", encoding="utf-8") as f:
                    json.dump([asdict(t) for t in trades], f, indent=2)

        return leaderboard_data

    def _generate_leaderboard_markdown(self, data: Dict[str, Any]) -> str:
        """Generates an executive markdown report for the independent model tournament."""
        md = []
        md.append(f"# 🏆 Independent Model Trading Tournament Leaderboard")
        md.append(f"**Session Date:** `{data['session_date']}` | **Starting Capital per Model:** `₹{data['capital_per_model']:,.2f}` | **Min Economic Hurdle:** `≥ ₹{data['min_net_edge_hurdle']:.2f}`\n")
        md.append(f"> **Champion Model:** **`{data['top_performer']}`** (Highest Verified Net P&L)\n")
        md.append("## Overall Rankings & Performance\n")
        md.append("| Rank | Model ID | Strategy / Timeframe | Trades | Win Rate | Gross P&L | Friction | **Net Profit (₹)** | ROI (%) | Top Symbol |")
        md.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

        for m in data["leaderboard"]:
            badge = "🥇" if m["rank"] == 1 else ("🥈" if m["rank"] == 2 else ("🥉" if m["rank"] == 3 else f"#{m['rank']}"))
            md.append(
                f"| {badge} | **`{m['model_id']}`** | {m['strategy_type'][:35]} ({m['timeframe']}) | "
                f"{m['total_trades']} | {m['win_rate_pct']:.1f}% | ₹{m['gross_pnl_rupees']:+.2f} | "
                f"₹{m['total_friction_rupees']:.2f} | **₹{m['net_pnl_rupees']:+.2f}** | "
                f"{m['roi_pct']:+.2f}% | `{m['best_symbol']}` |"
            )

        md.append("\n---\n")
        md.append("## Detailed Model Execution Breakdown\n")

        for m in data["leaderboard"]:
            md.append(f"### Rank #{m['rank']}: `{m['model_id']}` — {m['model_name']}")
            md.append(f"- **Timeframe / Horizon:** `{m['timeframe']}`")
            md.append(f"- **Trades Executed:** `{m['total_trades']}` (Wins: `{m['winning_trades']}`, Losses: `{m['losing_trades']}`)")
            md.append(f"- **Realized Net Profit:** **`₹{m['net_pnl_rupees']:+.2f}`** (Ending Capital: `₹{m['ending_capital']:,.2f}`)")

            if m["trades"]:
                md.append("\n| Trade ID | Symbol | Direction | Entry | Exit | Qty | Gross P&L | Friction | Net P&L | Win? |")
                md.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
                for t in m["trades"]:
                    d_str = "BUY" if t["direction"] == 1 else "SELL"
                    win_str = "✅ WIN" if t["is_win"] else "❌ LOSS"
                    md.append(
                        f"| `{t['trade_id']}` | `{t['symbol']}` | {d_str} | ₹{t['entry_price']:.2f} | "
                        f"₹{t['exit_price']:.2f} | {t['quantity']} | ₹{t['gross_pnl_rupees']:+.2f} | "
                        f"₹{t['total_friction_rupees']:.2f} | **₹{t['net_pnl_rupees']:+.2f}** | {win_str} |"
                    )
            else:
                md.append("\n*Model preserved 100% cash (no trade met the economic hurdle or valid setup).*")
            md.append("\n")

        return "\n".join(md)
