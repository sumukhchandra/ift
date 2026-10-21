"""
v3/analytics/performance.py
AlphaNSE Performance & Friction Analytics Engine.
Calculates deep execution statistics, risk-adjusted metrics, and Net Expectancy.
"""

import math
from typing import Dict, List, Any
import numpy as np


class PerformanceAnalytics:
    @staticmethod
    def calculate_comprehensive_metrics(
        trade_logs: List[Dict[str, Any]],
        starting_capital: float = 1500.0,
        equity_curve: List[float] = None,
        total_spread: float = 0.0,
        total_slippage: float = 0.0,
        total_brokerage: float = 0.0,
        total_taxes: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Computes the complete suite of trading, friction, and risk-adjusted metrics.
        """
        if not trade_logs:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "breakeven_trades": 0,
                "win_rate_pct": 0.0,
                "gross_pnl_rs": 0.0,
                "spread_cost_rs": round(total_spread, 2),
                "slippage_cost_rs": round(total_slippage, 2),
                "brokerage_rs": round(total_brokerage, 2),
                "statutory_taxes_rs": round(total_taxes, 2),
                "total_friction_rs": round(total_spread + total_slippage + total_brokerage + total_taxes, 2),
                "net_pnl_rs": 0.0,
                "roi_on_capital_pct": 0.0,
                "average_trade_rs": 0.0,
                "median_trade_rs": 0.0,
                "profit_factor": 0.0,
                "net_expectancy_rs": 0.0,
                "max_drawdown_rs": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "avg_holding_minutes": 0.0,
                "turnover_rs": 0.0,
                "cost_to_gross_pct": 0.0,
                "largest_winner_rs": 0.0,
                "largest_loser_rs": 0.0,
                "longest_loss_streak": 0,
                "message": "No trades executed."
            }

        net_pnls = [t["net_pnl"] for t in trade_logs]
        gross_pnls = [t["gross_pnl"] for t in trade_logs]
        frictions = [t["total_friction"] for t in trade_logs]
        holding_times = [t.get("holding_minutes", 0.0) for t in trade_logs]
        turnover = sum((t["entry_price"] + t["exit_price"]) * t["quantity"] for t in trade_logs)

        total_trades = len(trade_logs)
        wins = [p for p in net_pnls if p > 0]
        losses = [p for p in net_pnls if p < 0]
        breakevens = [p for p in net_pnls if p == 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        total_gross = sum(gross_pnls)
        total_net = sum(net_pnls)
        total_fric = sum(frictions)

        avg_trade = float(np.mean(net_pnls)) if net_pnls else 0.0
        median_trade = float(np.median(net_pnls)) if net_pnls else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(abs(np.mean(losses))) if losses else 0.0
        avg_friction = float(np.mean(frictions)) if frictions else 0.0

        # Profit Factor
        gross_wins = sum(p for p in gross_pnls if p > 0)
        gross_losses = abs(sum(p for p in gross_pnls if p < 0))
        profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)

        # Largest win & loss
        largest_winner = max(net_pnls) if net_pnls else 0.0
        largest_loser = min(net_pnls) if net_pnls else 0.0

        # Longest losing streak
        max_loss_streak = 0
        current_streak = 0
        for p in net_pnls:
            if p < 0:
                current_streak += 1
                max_loss_streak = max(max_loss_streak, current_streak)
            else:
                current_streak = 0

        # Net Expectancy Per Trade
        # E = (P_win * Avg_Win) - (P_loss * Avg_Loss) - Avg_Friction
        p_win = win_count / total_trades if total_trades > 0 else 0.0
        p_loss = loss_count / total_trades if total_trades > 0 else 0.0
        net_expectancy = (p_win * avg_win) - (p_loss * avg_loss)

        # Max Drawdown from equity curve
        max_dd_rs = 0.0
        max_dd_pct = 0.0
        if equity_curve and len(equity_curve) > 1:
            peak = equity_curve[0]
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
                if dd > max_dd_rs:
                    max_dd_rs = dd
                    max_dd_pct = dd_pct
        else:
            # Fallback calculate from cumulative net P&L
            cum = np.cumsum([0.0] + net_pnls)
            eq_series = starting_capital + cum
            peak = eq_series[0]
            for eq in eq_series:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
                if dd > max_dd_rs:
                    max_dd_rs = dd
                    max_dd_pct = dd_pct

        # Sharpe & Sortino (per-trade basis annualized or normalized)
        std_net = float(np.std(net_pnls)) if len(net_pnls) > 1 else 0.0
        sharpe_ratio = round((avg_trade / std_net) * math.sqrt(252), 2) if std_net > 0 else 0.0

        downside_returns = [p for p in net_pnls if p < 0]
        downside_std = float(np.std(downside_returns)) if len(downside_returns) > 1 else 0.0
        sortino_ratio = round((avg_trade / downside_std) * math.sqrt(252), 2) if downside_std > 0 else (999.0 if avg_trade > 0 else 0.0)

        # Cost-to-Gross Ratio
        cost_to_gross_pct = round((total_fric / total_gross) * 100.0, 1) if total_gross > 0 else 999.0

        return {
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "breakeven_trades": len(breakevens),
            "win_rate_pct": round(win_rate, 2),
            "gross_pnl_rs": round(total_gross, 2),
            "spread_cost_rs": round(total_spread, 2),
            "slippage_cost_rs": round(total_slippage, 2),
            "brokerage_rs": round(total_brokerage, 2),
            "statutory_taxes_rs": round(total_taxes, 2),
            "total_friction_rs": round(total_fric, 2),
            "net_pnl_rs": round(total_net, 2),
            "roi_on_capital_pct": round((total_net / starting_capital) * 100.0, 2),
            "average_trade_rs": round(avg_trade, 2),
            "median_trade_rs": round(median_trade, 2),
            "profit_factor": profit_factor,
            "net_expectancy_rs": round(net_expectancy, 2),
            "max_drawdown_rs": round(max_dd_rs, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "avg_holding_minutes": round(float(np.mean(holding_times)), 1) if holding_times else 0.0,
            "turnover_rs": round(turnover, 2),
            "cost_to_gross_pct": cost_to_gross_pct,
            "largest_winner_rs": round(largest_winner, 2),
            "largest_loser_rs": round(largest_loser, 2),
            "longest_loss_streak": max_loss_streak,
        }
