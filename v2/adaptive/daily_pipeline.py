"""
AlphaNSE V2 — Adaptive Daily Retraining & Trading Pipeline Orchestrator.
Coordinates the end-to-end 9-step daily adaptive cycle:
  1. Data Acquisition (all sessions <= D-1)
  2. Dataset Update & Deduplication
  3. Preprocessing & Feature Engineering
  4. Daily Model Retraining
  5. Pre-Market Model Validation & Sanity Gates
  6. Day-D Model Freezing & Manifest Serialization
  7. Sequential Intraday Bar Streaming
  8. Point-in-Time Prediction & Opportunity Ranking
  9. Risk Sizing, Execution & Trade Audit Lineage
"""

import os
import pickle
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

from .audit_ledger import DailyModelManifest, TradeAuditRecord, AuditLedger
from .dataset_updater import DatasetUpdater
from .model_updater import ModelUpdater
from .opportunity_ranker import OpportunityRanker
from .session_trader import SessionTrader
from v2.features.feature_pipeline import FeaturePipeline

logger = logging.getLogger(__name__)


@dataclass
class DailySessionResult:
    session_date: str
    manifest: DailyModelManifest
    trades: List[TradeAuditRecord]
    total_trades: int
    gross_pnl_rupees: float
    net_pnl_rupees: float
    avg_net_profit_per_trade_rupees: float
    avg_net_return_bps: float
    win_rate_pct: float
    ending_capital: float
    target_net_profit_passed: bool   # avg >= ₹0.80 per trade
    target_trades_passed: bool       # trades >= 30 per day


class AdaptiveDailyPipeline:
    """
    Production orchestrator for daily model retraining, validation, and session trading.
    """

    def __init__(
        self,
        base_raw_path: str = "v2/data/storage/normalized/historical_5m_raw.parquet",
        base_adj_path: str = "v2/data/storage/adjusted/historical_5m_adjusted.parquet",
        fresh_dir: str = "v2/data/storage/fresh",
        ledger_dir: str = "v2/adaptive/ledger",
        models_dir: str = "v2/models/adaptive_models",
        initial_capital: float = 5000.0,
        horizon_bars: int = 3,
        alpha_ridge: float = 20.0
    ):
        self.dataset_updater = DatasetUpdater(
            base_raw_path=base_raw_path,
            base_adj_path=base_adj_path,
            fresh_dir=fresh_dir
        )
        self.model_updater = ModelUpdater(
            models_dir=models_dir,
            horizon_bars=horizon_bars,
            alpha_ridge=alpha_ridge
        )
        self.audit_ledger = AuditLedger(ledger_dir=ledger_dir)
        self.fresh_dir = fresh_dir
        self.initial_capital = initial_capital
        self.horizon_bars = horizon_bars

    def get_session_environment(
        self,
        target_day: Any,
        session_df: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, DailyModelManifest, Any]:
        """
        Prepares or retrieves cached session data, features, model manifest, and retrained model for Day D.
        Supports target_day as datetime.date or str ("YYYY-MM-DD" or "YYYYMMDD").
        """
        if isinstance(target_day, str):
            target_str_clean = target_day.replace("-", "")
            target_date = datetime.strptime(target_str_clean, "%Y%m%d").date()
        else:
            target_date = target_day

        target_str = target_date.strftime("%Y%m%d")
        day_hyphen = target_date.strftime("%Y-%m-%d")

        # 1. Load session market data if not passed directly
        if session_df is None:
            session_file = os.path.join(self.fresh_dir, f"session_{target_str}_5m.parquet")
            if not os.path.exists(session_file):
                raise FileNotFoundError(f"Session market data not found: {session_file}")
            session_df = pd.read_parquet(session_file)

        session_df["timestamp"] = pd.to_datetime(session_df["timestamp"])
        session_df = session_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

        # 2. Manifest and Retrained Model: Check if already created or retrain point-in-time
        manifest = self.audit_ledger.load_manifest(day_hyphen)
        model_path = os.path.join(self.model_updater.models_dir, f"model_{target_str}.pkl")

        if manifest is not None and os.path.exists(model_path):
            with open(model_path, "rb") as f:
                model = pickle.load(f)
        else:
            # --- STEP 1 & 2: DATA ACQUISITION & DATASET UPDATE (strictly <= D-1) ---
            dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)

            # --- STEP 3, 4, 5, 6: PREPROCESSING, RETRAINING, SANITY GATES, FREEZING ---
            model, manifest = self.model_updater.train_and_freeze_for_day(target_date, dataset_meta)
            self.audit_ledger.save_manifest(manifest)

        # 3. Session Features: Check cache or generate point-in-time features
        features_cache_path = os.path.join(self.fresh_dir, f"features_{target_str}.parquet")
        if os.path.exists(features_cache_path):
            session_features = pd.read_parquet(features_cache_path)
            session_features["timestamp"] = pd.to_datetime(session_features["timestamp"])
        else:
            # Reconstruct training dataset meta if needed
            dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)
            df_train_raw = pd.read_parquet(dataset_meta["raw_path"])
            df_train_adj = pd.read_parquet(dataset_meta["adj_path"])

            # Combine historical up to D-1 with Day D for feature calculation continuity,
            # then slice strictly for Day D bars.
            combined_raw = pd.concat([df_train_raw, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            combined_adj = pd.concat([df_train_adj, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            tmp_raw = os.path.join(self.fresh_dir, f"_eval_raw_{target_str}.parquet")
            tmp_adj = os.path.join(self.fresh_dir, f"_eval_adj_{target_str}.parquet")
            combined_raw.to_parquet(tmp_raw)
            combined_adj.to_parquet(tmp_adj)

            feat_pipeline = FeaturePipeline(
                raw_parquet_path=tmp_raw,
                adj_parquet_path=tmp_adj
            )
            full_features = feat_pipeline.compute_all_features()

            # Clean temporary files
            for f in [tmp_raw, tmp_adj]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            # Slice strictly for Day D bars
            full_features["timestamp"] = pd.to_datetime(full_features["timestamp"])
            session_features = full_features[full_features["timestamp"].dt.strftime("%Y-%m-%d") == day_hyphen].copy()
            session_features.to_parquet(features_cache_path)

        return session_df, session_features, manifest, model

    _prepare_session_environment = get_session_environment

    def run_day(
        self,
        target_day: date,
        session_df: Optional[pd.DataFrame] = None,
        capital_override: Optional[float] = None
    ) -> DailySessionResult:
        """
        Executes the full adaptive pipeline for a single trading day D.
        """
        logger.info("=" * 80)
        logger.info(f"  ALPHANSE ADAPTIVE DAILY PIPELINE — SESSION: {target_day}  ")
        logger.info("=" * 80)

        session_df, session_features, manifest, model = self.get_session_environment(target_day, session_df)

        # --- STEP 8 & 9: SEQUENTIAL INTRADAY TRADING & AUDIT RECORDING ---
        capital = capital_override or self.initial_capital
        trader = SessionTrader(
            manifest=manifest,
            initial_capital=capital,
            horizon_bars=self.horizon_bars
        )
        trades = trader.run_session(session_df, session_features, model)

        # Save trades to audit ledger
        self.audit_ledger.save_trades(manifest.session_date, trades)

        # Performance summary
        n_trades = len(trades)
        gross_pnl = sum(t.net_pnl_rupees + (t.cost_bps * t.entry_price * t.quantity / 10000.0) for t in trades)
        net_pnl = sum(t.net_pnl_rupees for t in trades)
        avg_net_profit = (net_pnl / n_trades) if n_trades > 0 else 0.0
        avg_net_bps = (sum(t.net_return_bps for t in trades) / n_trades) if n_trades > 0 else 0.0
        wins = sum(1 for t in trades if t.net_pnl_rupees > 0)
        win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0

        target_net_profit_passed = avg_net_profit >= 0.80
        target_trades_passed = n_trades >= 30

        result = DailySessionResult(
            session_date=manifest.session_date,
            manifest=manifest,
            trades=trades,
            total_trades=n_trades,
            gross_pnl_rupees=round(gross_pnl, 2),
            net_pnl_rupees=round(net_pnl, 2),
            avg_net_profit_per_trade_rupees=round(avg_net_profit, 2),
            avg_net_return_bps=round(avg_net_bps, 2),
            win_rate_pct=round(win_rate, 2),
            ending_capital=round(trader.total_capital, 2),
            target_net_profit_passed=target_net_profit_passed,
            target_trades_passed=target_trades_passed
        )

        logger.info("-" * 80)
        logger.info(f"DAILY RESULT SUMMARY: {manifest.session_date}")
        logger.info(f"  Model Version:        {manifest.model_version}")
        logger.info(f"  Regime at Open:       {manifest.regime_at_open}")
        logger.info(f"  Total Trades:         {n_trades} (Target >= 30: {'PASS' if target_trades_passed else 'PENDING_ACCUMULATION'})")
        logger.info(f"  Net PnL:              ₹{net_pnl:.2f}")
        logger.info(f"  Avg Net Profit/Trade: ₹{avg_net_profit:.2f} (Target >= ₹0.80: {'PASS' if target_net_profit_passed else 'FAIL'})")
        logger.info(f"  Avg Net Return:       {avg_net_bps:.2f} bps")
        logger.info(f"  Win Rate:             {win_rate:.1f}%")
        logger.info(f"  Ending Capital:       ₹{trader.total_capital:.2f}")
        logger.info("-" * 80)

        return result

    def run_walk_forward(
        self,
        session_dates: List[date]
    ) -> List[DailySessionResult]:
        """
        Executes sequential daily walk-forward across multiple trading days:
        Each day D retrains on all prior days, executes day D, then day D is available for day D+1.
        """
        results = []
        running_capital = self.initial_capital

        logger.info("=" * 80)
        logger.info(f"  STARTING MULTI-DAY ADAPTIVE WALK-FORWARD ({len(session_dates)} SESSIONS)  ")
        logger.info("=" * 80)

        for d in sorted(session_dates):
            res = self.run_day(d, capital_override=running_capital)
            results.append(res)
            running_capital = res.ending_capital

        return results
