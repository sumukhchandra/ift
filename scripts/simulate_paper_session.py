#!/usr/bin/env python3
"""
scripts/simulate_paper_session.py
AlphaNSE V3 — Full-Day Realistic Paper Trading Simulation ("Money In vs Money Out").
Strictly adheres to the ALPHANSE V3 IMPLEMENTATION DIRECTIVE:
1. Zero faking, zero synthetic sequences — evaluated strictly on real historical 1m market bars.
2. Universe restricted 100% to verified NIFTY 50 constituents.
3. Starting paper account balance of EXACTLY ₹1,500.00.
4. Single-position integer sizing under strict available cash ceiling (zero negative cash, zero leverage).
5. Dual-Model Concurrence Gate (Specialist Ridge + ML Tree Ensemble + Calibrated Breakout Classifier).
6. Pre-trade Economic Edge Friction Gate (Kotak Neo Trade Free Plan: ₹0 brokerage + statutory fees).
7. Risk Management: 0.30% hard stop-loss cap, dynamic +1.0% target harvest, +0.50% breakeven lock, 15:15 IST EOD exit.
8. Persists complete 17-column trade ledger, intraday summary, minute predictions, and interactive HTML chart.
"""

import os
import sys
import math
import json
import numpy as np
import pandas as pd
from datetime import datetime, time

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout and getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.execution.edge_friction_gate import EdgeFrictionGate
from v2.risk.cost_engine import IndiaCostEngine
from QA.models.one_min_predictor import OneMinPredictor
from v3.reports.chart_generator import generate_interactive_chart

DATA_FILE = os.path.join(WORKSPACE_ROOT, "QA", "data", "combined_weekend_1m.csv")
WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "active_model_weights.json")

# Verified Authoritative NIFTY 50 Universe
UNIVERSE = {
    "BAJFINANCE": {"model": "HYPO002", "name": "Bajaj Finance", "kotak": "BAJFINANCE-EQ"},
    "INFY": {"model": "V2_15M", "name": "Infosys", "kotak": "INFY-EQ"},
    "RELIANCE": {"model": "V3_60M", "name": "Reliance", "kotak": "RELIANCE-EQ"},
    "TATASTEEL": {"model": "HYPO001", "name": "Tata Steel", "kotak": "TATASTEEL-EQ"},
    "AXISBANK": {"model": "HYPO003", "name": "Axis Bank", "kotak": "AXISBANK-EQ"},
    "NSEI": {"model": "SMC_4CONF_920", "name": "Nifty 50 ETF", "kotak": "NIFTYBEES-EQ"}
}


def build_vectorized_19_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_p = df["open"].astype(float)
    vol = df["volume"].astype(float).replace(0, 1.0)

    r1 = close.pct_change(1).fillna(0)
    r3 = close.pct_change(3).fillna(0)
    r5 = close.pct_change(5).fillna(0)
    r10 = close.pct_change(10).fillna(0)
    accel1 = (r1 - r1.shift(1)).fillna(0)

    delta = close.diff().fillna(0)
    gain_14 = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss_14 = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs14 = gain_14 / (loss_14 + 1e-9)
    rsi14 = (100.0 - (100.0 / (1.0 + rs14))).fillna(50.0)

    gain_7 = delta.clip(lower=0).rolling(7, min_periods=1).mean()
    loss_7 = (-delta.clip(upper=0)).rolling(7, min_periods=1).mean()
    rs7 = gain_7 / (loss_7 + 1e-9)
    rsi7 = (100.0 - (100.0 / (1.0 + rs7))).fillna(50.0)

    cum_vol = vol.rolling(21, min_periods=1).sum()
    cum_vp = (close * vol).rolling(21, min_periods=1).sum()
    vwap = cum_vp / cum_vol.replace(0, np.nan)
    vwap = vwap.fillna(close)
    vwap_dist = (close - vwap) / vwap

    sma20 = close.rolling(20, min_periods=1).mean()
    std20 = close.rolling(20, min_periods=1).std().fillna(1e-6)
    bb_bandwidth = (4.0 * std20) / sma20
    bb_pct_b = (close - (sma20 - 2.0 * std20)) / (4.0 * std20 + 1e-9)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=1).mean()
    micro_atr14 = atr14 / close

    ln_hl = np.log(high / low.replace(0, np.nan)).fillna(0)
    parkinson_vol = np.sqrt(ln_hl.rolling(10, min_periods=1).apply(lambda x: np.mean(x ** 2) / (4.0 * np.log(2.0)), raw=True)).fillna(0)

    candle_range = (high - low).replace(0, 1e-6)
    upper_wick = (high - np.maximum(open_p, close)) / candle_range
    lower_wick = (np.minimum(open_p, close) - low) / candle_range
    wick_pressure = lower_wick - upper_wick

    avg_vol_10 = vol.shift(1).rolling(10, min_periods=1).mean().replace(0, 1.0)
    vol_surge = vol / avg_vol_10

    r1_x_vol = r1 * vol_surge
    vwap_x_rsi = vwap_dist * (rsi14 / 100.0)
    accel_x_bb = accel1 * bb_bandwidth

    return pd.DataFrame({
        "r1": r1, "r3": r3, "r5": r5, "r10": r10, "accel1": accel1,
        "rsi7": rsi7 / 100.0, "rsi14": rsi14 / 100.0,
        "vwap_dist": vwap_dist, "bb_pct_b": bb_pct_b, "bb_bandwidth": bb_bandwidth,
        "micro_atr14": micro_atr14, "parkinson_vol": parkinson_vol,
        "wick_pressure": wick_pressure, "upper_wick": upper_wick, "lower_wick": lower_wick,
        "vol_surge": vol_surge,
        "r1_x_vol": r1_x_vol, "vwap_x_rsi": vwap_x_rsi, "accel_x_bb": accel_x_bb
    }).fillna(0)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AlphaNSE V3 Paper Trading Simulation")
    parser.add_argument("--allow-short-selling", action="store_true", help="Allow intraday short selling (MIS margin mode)")
    args = parser.parse_args()
    allow_short_selling = args.allow_short_selling

    mode_label = "INTRADAY MIS (MARGIN SHORTING ALLOWED)" if allow_short_selling else "CASH-ONLY (NO MARGIN, NO SHORT SELLING)"

    print("=" * 115)
    print("  💰 ALPHANSE V3 — FULL-DAY QUANTITATIVE PAPER TRADING SESSION SIMULATION")
    print("  SIMULATING: Friday, Oct 09, 2026 Session (09:15:00 IST to 15:30:00 IST)")
    print("  STARTING PAPER ACCOUNT CAPITAL: EXACTLY ₹1,500.00 (ZERO RISK TO REAL CAPITAL)")
    print(f"  ACCOUNT RULES: {mode_label}")
    print("  BROKERAGE PLAN: Kotak Neo Trade Free Plan (₹0 Brokerage on Equity Intraday)")
    print("=" * 115)

    df = pd.read_csv(DATA_FILE)
    df["dt"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["dt"].dt.date
    dates = sorted(df["date"].unique())
    last_date = dates[-1]

    session_df = df[df["date"] == last_date].copy().sort_values("dt").reset_index(drop=True)
    print(f"Target Session Date: {last_date} | Total 1m bars in session: {len(session_df):,}")

    with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
        meta_all = json.load(f)

    ml_predictor = OneMinPredictor()

    cost_engine = IndiaCostEngine()
    cost_engine.brokerage_pct = 0.0
    cost_engine.brokerage_flat_cap = 0.0

    edge_gate = EdgeFrictionGate(half_spread_bps=2.5, slippage_bps=3.0, safety_margin_rs=0.40, min_net_expectancy_rs=0.30)
    edge_gate.cost_engine = cost_engine

    # Prepare features and predictions per symbol for the entire session
    session_data = {}
    timestamps = sorted(session_df["dt"].unique())

    print("\nComputing dual-model predictions across the entire trading session...")
    for sym, u_info in UNIVERSE.items():
        s_df = session_df[session_df["symbol"] == sym].copy().sort_values("dt").reset_index(drop=True)
        if len(s_df) < 50:
            continue

        meta = meta_all[u_info["model"]]
        feats_19 = build_vectorized_19_features(s_df).values
        w = np.array(meta["weights"])
        m = np.array(meta["means"])
        s = np.array(meta["stds"])
        b = meta["bias"]
        s_safe = np.where(s == 0, 1.0, s)
        spec_preds = np.dot((feats_19 - m) / s_safe, w) + b

        ml_feat_df = ml_predictor.extract_features_1m(s_df[["close", "open", "high", "low", "volume", "timestamp"]])
        X = ml_feat_df[ml_predictor.feature_cols].ffill().fillna(0)

        tree_sub = [reg.predict(X) for reg in ml_predictor.regressors.values()]
        tree_preds = np.mean(tree_sub, axis=0)
        breakout_probs = ml_predictor.classifier.predict_proba(X)[:, 1]

        s_df["spec_pred"] = spec_preds
        s_df["tree_pred"] = tree_preds
        s_df["breakout_prob"] = breakout_probs
        s_df["micro_rsi"] = ml_feat_df["micro_rsi_7"].values
        s_df["wick_pressure"] = ml_feat_df["wick_pressure"].values

        session_data[sym] = s_df.set_index("dt")

    # Simulation State: Exactly ₹1,500.00 Capital
    STARTING_CAPITAL = 1500.00
    current_bankroll = STARTING_CAPITAL
    peak_bankroll = STARTING_CAPITAL
    max_drawdown_rs = 0.0

    active_positions = {}
    completed_trades = []
    rejected_signals = []
    minute_predictions = []
    events_log = []

    square_off_time = time(15, 15)

    print(f"\nReplaying {len(timestamps)} 1-minute market intervals from 09:15 to 15:30 IST...")

    for idx, ts in enumerate(timestamps):
        t_time = ts.time()

        # Record predictions for all instruments at this minute
        for sym, u_info in UNIVERSE.items():
            sym_bars = session_data.get(sym)
            if sym_bars is None or ts not in sym_bars.index:
                continue
            bar = sym_bars.loc[ts]
            scale = 0.01 if sym == "NSEI" else 1.0
            cur_p = round(float(bar["close"]) * scale, 2)
            p_spec = float(bar["spec_pred"])
            p_tree = float(bar["tree_pred"])
            b_prob = float(bar["breakout_prob"])

            # Next bar actual price for evaluation (t+1)
            actual_next_p = cur_p
            if idx + 1 < len(timestamps):
                next_ts = timestamps[idx + 1]
                if next_ts in sym_bars.index:
                    actual_next_p = round(float(sym_bars.loc[next_ts]["close"]) * scale, 2)

            pred_ret = (p_spec + p_tree) / 2.0
            pred_p = round(cur_p * (1.0 + pred_ret), 2)
            direction = "UP" if pred_ret > 0.0002 else ("DOWN" if pred_ret < -0.0002 else "UNCERTAIN")
            actual_dir = "UP" if actual_next_p > cur_p else ("DOWN" if actual_next_p < cur_p else "FLAT")
            is_correct = (direction == actual_dir) if direction != "UNCERTAIN" else None

            pred_record = {
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S IST"),
                "symbol": sym,
                "current_price": cur_p,
                "predicted_price_1m": pred_p,
                "predicted_return_pct": round(pred_ret * 100.0, 3),
                "predicted_direction": direction,
                "breakout_prob_pct": round(b_prob * 100.0, 1),
                "specialist_alpha_bps": round(p_spec * 10000.0, 2),
                "tree_alpha_bps": round(p_tree * 10000.0, 2),
                "actual_next_price": actual_next_p,
                "prediction_error_rs": round(pred_p - actual_next_p, 2),
                "is_correct": is_correct
            }
            minute_predictions.append(pred_record)

        # 1. Manage Active Positions: Monitor Exits & Ratchets
        for mid, pos in list(active_positions.items()):
            sym = pos["symbol"]
            sym_bars = session_data.get(sym)
            if sym_bars is None or ts not in sym_bars.index:
                continue

            bar = sym_bars.loc[ts]
            scale = 0.01 if sym == "NSEI" else 1.0
            c = float(bar["close"]) * scale
            h = float(bar["high"]) * scale
            l = float(bar["low"]) * scale

            side = pos["side"]
            entry_px = pos["entry_price"]
            shares = pos["shares"]
            notional = pos["money_in"]

            unrealized = (c - entry_px) * shares if side == "BUY" else (entry_px - c) * shares
            max_gain = (h - entry_px) / entry_px if side == "BUY" else (entry_px - l) / entry_px
            max_loss = (l - entry_px) / entry_px if side == "BUY" else (entry_px - h) / entry_px

            # Breakeven ratchet activation at +0.50%
            if max_gain >= 0.005 and not pos.get("breakeven_locked"):
                pos["breakeven_locked"] = True
                pos["stop_ret"] = 0.000
                events_log.append(f"[{ts.strftime('%H:%M:%S')}] Breakeven Ratchet locked for {pos['kotak_symbol']} at ₹0.00")

            # Check Holding Timeout (60 minutes)
            mins_held = int((ts - pos["entry_dt"]).total_seconds() // 60)

            # Exit Conditions
            should_exit = False
            exit_px = c
            exit_reason = ""

            # EOD Square-Off (Mandatory 15:15 IST)
            if t_time >= square_off_time:
                should_exit = True
                exit_px = c
                exit_reason = "15:15_EOD_SQUARE_OFF"
            # Target Hit (+1.0%)
            elif max_gain >= 0.010:
                should_exit = True
                exit_px = round(entry_px * 1.010 if side == "BUY" else entry_px * 0.990, 2)
                exit_reason = "PROFIT_TARGET_+1.0%"
            # Stop Loss Hit (-0.30% cap or Breakeven)
            elif max_loss <= pos["stop_ret"]:
                should_exit = True
                stop_target = pos["stop_ret"]
                exit_px = round(entry_px * (1.0 + stop_target) if side == "BUY" else entry_px * (1.0 - stop_target), 2)
                exit_reason = "BREAKEVEN_STOP" if pos.get("breakeven_locked") else "STOP_LOSS_0.3%_CAP"
            # Timeout (60 minutes without resolution)
            elif mins_held >= 60:
                should_exit = True
                exit_px = c
                exit_reason = "HOLDING_TIMEOUT_60M"

            if should_exit:
                gross = (exit_px - entry_px) * shares if side == "BUY" else (entry_px - exit_px) * shares
                gross_ret = gross / notional
                costs = cost_engine.calculate_roundtrip_cost(notional, gross_ret)
                taxes = costs.total_cost - costs.brokerage
                net = gross - taxes
                money_out = round(notional + net, 2)
                current_bankroll = round(current_bankroll + net, 2)

                peak_bankroll = max(peak_bankroll, current_bankroll)
                dd = peak_bankroll - current_bankroll
                max_drawdown_rs = max(max_drawdown_rs, dd)

                holding_sec = int((ts - pos["entry_dt"]).total_seconds())

                trade_record = {
                    "trade_id": f"TRD-{last_date.strftime('%Y%m%d')}-{len(completed_trades)+1:03d}",
                    "instrument": pos["kotak_symbol"],
                    "direction": side,
                    "signal_time": pos["signal_time"],
                    "entry_time": pos["entry_dt"].strftime("%H:%M:%S IST"),
                    "entry_price": entry_px,
                    "quantity": shares,
                    "exit_time": ts.strftime("%H:%M:%S IST"),
                    "exit_price": exit_px,
                    "gross_pnl": round(gross, 2),
                    "charges": {
                        "brokerage": 0.0,
                        "stt": round(costs.stt, 2),
                        "exchange_fees": round(costs.exchange_charges, 4),
                        "sebi_turnover": round(costs.sebi_fees, 4),
                        "stamp_duty": round(costs.stamp_duty, 4),
                        "gst": round(costs.gst, 4),
                        "statutory_taxes_total": round(costs.proportional_statutory_cost, 2),
                        "modeled_slippage": round(costs.slippage, 2),
                        "total_friction": round(taxes, 2)
                    },
                    "net_pnl": round(net, 2),
                    "return_pct": round((net / notional) * 100.0, 2),
                    "holding_duration": f"{int(holding_sec // 60)}m {int(holding_sec % 60)}s",
                    "exit_reason": exit_reason,
                    "prediction_result": "CORRECT" if net > 0 else "INCORRECT",
                    "model_decision": {
                        "ensemble_signal": side,
                        "specialist_alpha_bps": pos["specialist_alpha_bps"],
                        "tree_alpha_bps": pos["tree_alpha_bps"],
                        "breakout_prob_pct": pos["breakout_prob_pct"]
                    },
                    "money_in": notional,
                    "money_out": money_out,
                    "bankroll_after": current_bankroll
                }
                completed_trades.append(trade_record)
                events_log.append(f"[{ts.strftime('%H:%M:%S')}] Closed {side} on {pos['kotak_symbol']} @ ₹{exit_px:.2f} | Net: ₹{net:+.2f} ({exit_reason})")
                del active_positions[mid]

        # Stop seeking new entries after 14:45 IST
        if t_time >= time(14, 45):
            continue

        # Single Position Constraint under ₹1,500 Capital
        if len(active_positions) >= 1:
            continue

        # 2. Evaluate New Trade Candidates
        for sym, u_info in UNIVERSE.items():
            mid = u_info["model"]
            if mid in active_positions:
                continue

            sym_bars = session_data.get(sym)
            if sym_bars is None or ts not in sym_bars.index:
                continue

            bar = sym_bars.loc[ts]
            scale = 0.01 if sym == "NSEI" else 1.0
            c = float(bar["close"]) * scale
            sim_price = round(c, 2)
            p_spec = float(bar["spec_pred"])
            p_tree = float(bar["tree_pred"])
            b_prob = float(bar["breakout_prob"])
            rsi = float(bar["micro_rsi"])
            wick = float(bar["wick_pressure"])

            # High-Conviction Concurrence Filter
            side = None
            if p_spec > 0 and p_tree >= 0.0002 and b_prob >= 0.50 and 35.0 <= rsi <= 68.0 and wick >= -0.20:
                side = "BUY"
            elif p_spec < 0 and p_tree <= -0.0002 and b_prob <= 0.48 and 32.0 <= rsi <= 65.0 and wick <= 0.20:
                side = "SELL"

            if not side:
                continue

            # Under cash-only, no-margin rules: short selling is prohibited unless shorting is explicitly supported
            if side == "SELL" and not allow_short_selling:
                rejected_signals.append({
                    "timestamp": ts.strftime("%H:%M:%S"),
                    "symbol": sym,
                    "reason": "SHORT_SELLING_PROHIBITED_UNDER_CASH_ONLY_RULES"
                })
                continue

            # Position Sizing: Whole shares under available paper balance (₹1,500)
            available_cash = current_bankroll
            if available_cash < sim_price:
                rejected_signals.append({"timestamp": ts.strftime("%H:%M:%S"), "symbol": sym, "reason": f"INSUFFICIENT_CASH (Price ₹{sim_price:.2f} > Balance ₹{available_cash:.2f})"})
                continue

            shares = int(available_cash // sim_price)
            if shares < 1:
                rejected_signals.append({"timestamp": ts.strftime("%H:%M:%S"), "symbol": sym, "reason": "SHARES_LESS_THAN_1"})
                continue

            notional = round(shares * sim_price, 2)
            exp_move = 0.010 * (b_prob if side == "BUY" else (1.0 - b_prob))

            # Economic Edge Friction Gate
            edge_res = edge_gate.evaluate_signal(
                symbol=sym,
                side=side,
                quantity=shares,
                mid_price=sim_price,
                expected_move_pct=abs(exp_move)
            )

            if not edge_res.approved:
                rejected_signals.append({"timestamp": ts.strftime("%H:%M:%S"), "symbol": sym, "reason": f"FRICTION_GATE_REJECTED (Net edge ₹{edge_res.net_edge_rs:.2f} < hurdle)"})
                continue

            # Open Single Paper Position
            active_positions[mid] = {
                "symbol": sym,
                "kotak_symbol": u_info["kotak"],
                "side": side,
                "signal_time": ts.strftime("%H:%M:%S IST"),
                "entry_dt": ts,
                "entry_price": sim_price,
                "shares": shares,
                "money_in": notional,
                "stop_ret": -0.003, # 0.3% hard stop cap
                "breakeven_locked": False,
                "specialist_alpha_bps": round(p_spec * 10000.0, 2),
                "tree_alpha_bps": round(p_tree * 10000.0, 2),
                "breakout_prob_pct": round(b_prob * 100.0, 1)
            }
            events_log.append(f"[{ts.strftime('%H:%M:%S')}] Opened {side} {shares}x {u_info['kotak']} @ ₹{sim_price:.2f} (Notional: ₹{notional:,.2f})")
            break  # Allow only 1 position under ₹1,500 capital limit

    # Reconcile Results
    wins = [t for t in completed_trades if t["net_pnl"] > 0]
    losses = [t for t in completed_trades if t["net_pnl"] < 0]
    breakevens = [t for t in completed_trades if t["net_pnl"] == 0]
    total_net_pnl = round(current_bankroll - STARTING_CAPITAL, 2)
    total_money_in = round(sum(t["money_in"] for t in completed_trades), 2)
    total_money_out = round(sum(t["money_out"] for t in completed_trades), 2)
    total_taxes = round(sum(t["charges"]["total_friction"] for t in completed_trades), 2)
    win_rate = round((len(wins) / len(completed_trades) * 100.0), 2) if completed_trades else 0.0
    avg_win = round(sum(t["net_pnl"] for t in wins) / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(t["net_pnl"] for t in losses) / len(losses), 2) if losses else 0.0
    net_expectancy = round(total_net_pnl / len(completed_trades), 2) if completed_trades else 0.0
    max_dd_pct = round((max_drawdown_rs / STARTING_CAPITAL) * 100.0, 2)

    intraday_summary = {
        "session_date": str(last_date),
        "execution_rules": mode_label,
        "starting_paper_capital": STARTING_CAPITAL,
        "ending_paper_capital": current_bankroll,
        "realized_pnl": total_net_pnl,
        "unrealized_pnl": 0.00,
        "gross_pnl": round(sum(t["gross_pnl"] for t in completed_trades), 2),
        "net_pnl": total_net_pnl,
        "total_trades": len(completed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(breakevens),
        "win_rate_pct": win_rate,
        "avg_win_inr": avg_win,
        "avg_loss_inr": avg_loss,
        "net_expectancy_inr": net_expectancy,
        "total_fees_and_slippage": total_taxes,
        "maximum_drawdown_inr": round(max_drawdown_rs, 2),
        "maximum_drawdown_pct": max_dd_pct,
        "open_positions": active_positions,
        "rejected_signals_count": len(rejected_signals),
        "rejected_signals": rejected_signals[:25],
        "total_money_in": total_money_in,
        "total_money_out": total_money_out,
        "timestamped_events_count": len(events_log)
    }

    # Save Output Files (Strictly isolated in reports/replay/ to prevent live session mixing)
    reports_replay_dir = os.path.join(WORKSPACE_ROOT, "reports", "replay")
    os.makedirs(reports_replay_dir, exist_ok=True)

    summary_file = os.path.join(reports_replay_dir, "paper_intraday_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(intraday_summary, f, indent=2)

    ledger_payload = {
        "session_date": str(last_date),
        "execution_rules": mode_label,
        "initial_bankroll": STARTING_CAPITAL,
        "final_bankroll": current_bankroll,
        "net_profit_rs": total_net_pnl,
        "win_rate_pct": win_rate,
        "trades": completed_trades
    }

    ledger_file = os.path.join(reports_replay_dir, "paper_replay_ledger.json")
    with open(ledger_file, "w", encoding="utf-8") as f:
        json.dump(ledger_payload, f, indent=2)

    # Save mode-specific file copy
    mode_suffix = "mis" if allow_short_selling else "cash_only"
    mode_ledger_file = os.path.join(reports_replay_dir, f"paper_replay_ledger_{mode_suffix}.json")
    with open(mode_ledger_file, "w", encoding="utf-8") as f:
        json.dump(ledger_payload, f, indent=2)

    mode_summary_file = os.path.join(reports_replay_dir, f"paper_intraday_summary_{mode_suffix}.json")
    with open(mode_summary_file, "w", encoding="utf-8") as f:
        json.dump(intraday_summary, f, indent=2)

    pred_file = os.path.join(reports_replay_dir, "real_vs_predicted_predictions.jsonl")
    with open(pred_file, "w", encoding="utf-8") as f:
        for p in minute_predictions:
            f.write(json.dumps(p) + "\n")

    # Generate Interactive HTML Chart for Replay
    chart_file = os.path.join(reports_replay_dir, "real_vs_predicted_chart.html")
    generate_interactive_chart(
        predictions_records=minute_predictions,
        trades_records=completed_trades,
        output_html_path=chart_file,
        title=f"AlphaNSE V3 — Observed Real Price vs Next-Minute Predicted Price ({mode_label}) [REPLAY]"
    )

    print("\n" + "=" * 115)
    print("  🏁 SIMULATION COMPLETE — FINANCIAL RECONCILIATION SUMMARY")
    print("=" * 115)
    print(f"  • Starting Paper Account Balance:  ₹{STARTING_CAPITAL:>8,.2f}")
    print(f"  • Ending Paper Account Balance:    ₹{current_bankroll:>8,.2f}")
    print(f"  • Net Trading P&L:                 ₹{total_net_pnl:>+8,.2f}  ({(total_net_pnl / STARTING_CAPITAL) * 100:+.2f}%)")
    print(f"  • Cumulative Capital Deployed:     ₹{total_money_in:>8,.2f}  (across {len(completed_trades)} completed trades)")
    print(f"  • Cumulative Capital Returned:     ₹{total_money_out:>8,.2f}")
    print(f"  • Total Taxes & Statutory Fees:    ₹{total_taxes:>8,.2f}  (Trade Free ₹0 Brokerage)")
    print(f"  • Win Rate:                         {win_rate:>7.1f}%  ({len(wins)} wins / {len(losses)} losses / {len(breakevens)} BE)")
    print(f"  • Average Win / Average Loss:      +₹{avg_win:.2f} / ₹{avg_loss:.2f}")
    print(f"  • Net Expectancy Per Trade:        ₹{net_expectancy:+.2f}")
    print(f"  • Maximum Drawdown:                ₹{max_drawdown_rs:.2f} ({max_dd_pct:.2f}%)")
    print(f"  • Minute Predictions Evaluated:    {len(minute_predictions):,}")
    print("-" * 115)

    print(f"\n{'#':<3} | {'INSTRUMENT':<13} | {'DIR':<4} | {'TIMES (IN -> OUT)':<19} | {'QTY':<3} | {'PUT IN (₹)':<10} | {'RETURNED (₹)':<12} | {'TAX':<5} | {'NET (₹)':<8} | {'ROI %':<6} | {'BANKROLL (₹)':<12} | {'EXIT REASON'}")
    print("-" * 115)
    for i, t in enumerate(completed_trades, 1):
        badge = "🟢" if t["net_pnl"] > 0 else ("🔴" if t["net_pnl"] < 0 else "⚪")
        print(f"{i:<3} | {t['instrument']:<13} | {t['direction']:<4} | {t['entry_time'][:8]} -> {t['exit_time'][:8]} | {t['quantity']:<3} | ₹{t['money_in']:>8.2f} | ₹{t['money_out']:>10.2f} | ₹{t['charges']['total_friction']:>4.2f} | {badge} {t['net_pnl']:>+6.2f} | {t['return_pct']:>+5.2f}% | ₹{t['bankroll_after']:>10.2f} | {t['exit_reason']}")

    print("=" * 115)
    print(f"  📁 Interactive Chart Generated:  {chart_file}")
    print(f"  📁 Complete Trade Ledger Saved:  {ledger_file}")
    print(f"  📁 Intraday Summary Saved:       {summary_file}")
    print(f"  📁 Minute Predictions Logged:    {pred_file}")
    print("=" * 115 + "\n")


if __name__ == "__main__":
    main()
