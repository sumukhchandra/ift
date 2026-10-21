"""
AlphaNSE V3 — Daily Adaptive 60-Minute Pipeline Orchestrator.
Orchestrates the complete 9-step daily adaptive research lifecycle:

  D-1 complete
     ↓
  update dataset (strictly <= D-1)
     ↓
  train 60m model (horizon_bars=12)
     ↓
  validate (leakage, feature integrity, regime)
     ↓
  freeze model + cryptographic SHA-256 hash
     ↓
  market opens
     ↓
  5m sequential data stream
     ↓
  rank opportunities (Rupee Net-Edge formula)
     ↓
  cost + capital + risk gates
     ↓
  trade OR remain cash
     ↓
  post-market audit ledger
     ↓
  next day's retraining

STATUS: EXPERIMENT / VALIDATION
Explicitly segregates HISTORICAL REPLAY / BASELINE (Sessions 1-4) from
FRESH FORWARD VALIDATION (Session 5 onward).
"""

import os
import pickle
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

from v2.adaptive.dataset_updater import DatasetUpdater
from v2.features.feature_pipeline import FeaturePipeline
from v3.config.v3_config import (
    HORIZON_BARS,
    ALPHA_RIDGE,
    INITIAL_CAPITAL,
    V3_MODELS_DIR,
    V3_LEDGER_DIR,
    BASE_RAW_PATH,
    BASE_ADJ_PATH,
    FRESH_DIR,
    REPLAY_DISCLAIMER,
    FORWARD_VALIDATION_LABEL,
    EXPERIMENT_MODE,
    PROFITABILITY_CLAIM
)
from v3.adaptive.audit_ledger_v3 import DailyModelManifestV3, TradeAuditRecordV3, AuditLedgerV3, CandidateDecisionAuditRecordV3
from v3.adaptive.model_updater_v3 import ModelUpdaterV3
from v3.adaptive.session_trader_v3 import SessionTraderV3
from v3.models.model_registry import MultiModelRegistryV3
from v3.models.model_trainers import MultiModelTrainerV3

logger = logging.getLogger(__name__)


@dataclass
class DailySessionResultV3:
    """Consolidated performance and audit report for a single session under V3."""
    session_date: str
    manifest: DailyModelManifestV3
    trades: List[TradeAuditRecordV3]
    total_trades: int
    gross_pnl_rupees: float
    net_pnl_rupees: float
    avg_net_profit_per_trade_rupees: float
    avg_net_return_bps: float
    win_rate_pct: float
    ending_capital: float
    cash_holding_session: bool
    execution_type: str
    disclaimer: str

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "session_date": self.session_date,
            "execution_type": self.execution_type,
            "total_trades": self.total_trades,
            "gross_pnl_rupees": self.gross_pnl_rupees,
            "net_pnl_rupees": self.net_pnl_rupees,
            "avg_net_profit_rupees": self.avg_net_profit_per_trade_rupees,
            "avg_net_bps": self.avg_net_return_bps,
            "win_rate_pct": self.win_rate_pct,
            "ending_capital": self.ending_capital,
            "cash_holding_session": self.cash_holding_session,
            "model_version": self.manifest.model_version,
            "disclaimer": self.disclaimer
        }


class AdaptiveDailyPipelineV3:
    """
    Production orchestrator for V3 60m adaptive pipeline.
    Maintains clean isolation from V2.
    """

    def __init__(
        self,
        base_raw_path: str = BASE_RAW_PATH,
        base_adj_path: str = BASE_ADJ_PATH,
        fresh_dir: str = FRESH_DIR,
        ledger_dir: str = V3_LEDGER_DIR,
        models_dir: str = V3_MODELS_DIR,
        initial_capital: float = INITIAL_CAPITAL,
        horizon_bars: int = HORIZON_BARS,
        alpha_ridge: float = ALPHA_RIDGE
    ):
        self.dataset_updater = DatasetUpdater(
            base_raw_path=base_raw_path,
            base_adj_path=base_adj_path,
            fresh_dir=fresh_dir
        )
        self.model_updater = ModelUpdaterV3(
            models_dir=models_dir,
            horizon_bars=horizon_bars,
            alpha_ridge=alpha_ridge
        )
        self.audit_ledger = AuditLedgerV3(ledger_dir=ledger_dir)
        self.multimodel_registry = MultiModelRegistryV3()
        self.multimodel_trainer = MultiModelTrainerV3(registry=self.multimodel_registry)
        self.fresh_dir = fresh_dir
        self.initial_capital = initial_capital
        self.horizon_bars = horizon_bars

    def get_session_environment(
        self,
        target_day: Any,
        session_df: Optional[pd.DataFrame] = None,
        is_forward_validation: bool = False
    ) -> Tuple[pd.DataFrame, pd.DataFrame, DailyModelManifestV3, Any]:
        """
        Prepares point-in-time session data, features, model manifest, and retrained 60m model.
        Guarantees strict D-1 training cutoff without lookahead.
        """
        if isinstance(target_day, str):
            target_str_clean = target_day.replace("-", "")
            target_date = datetime.strptime(target_str_clean, "%Y%m%d").date()
        else:
            target_date = target_day

        target_str = target_date.strftime("%Y%m%d")
        day_hyphen = target_date.strftime("%Y-%m-%d")

        # 1. Load session market data
        if session_df is None:
            session_file = os.path.join(self.fresh_dir, f"session_{target_str}_5m.parquet")
            if not os.path.exists(session_file):
                raise FileNotFoundError(f"Session market data not found: {session_file}")
            session_df = pd.read_parquet(session_file)

        session_df["timestamp"] = pd.to_datetime(session_df["timestamp"])
        session_df = session_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

        # 2. Manifest and Retrained 60m Model: Check if already created or retrain point-in-time
        manifest = self.audit_ledger.load_manifest(day_hyphen)
        model_path = os.path.join(self.model_updater.models_dir, f"model_v3_{target_str}.pkl")

        if manifest is not None and os.path.exists(model_path):
            with open(model_path, "rb") as f:
                model = pickle.load(f)
        else:
            # Prepare dataset strictly <= D-1
            dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)

            # Train 60m model, validate sanity gates, and freeze
            model, manifest = self.model_updater.train_and_freeze_for_day(
                target_day=target_date,
                dataset_meta=dataset_meta,
                is_forward_validation=is_forward_validation
            )
            self.audit_ledger.save_manifest(manifest)

        # 3. Session Features
        # Features use standard 26 features; check cache or generate point-in-time features
        features_cache_path = os.path.join(self.fresh_dir, f"features_{target_str}.parquet")
        if os.path.exists(features_cache_path):
            session_features = pd.read_parquet(features_cache_path)
            session_features["timestamp"] = pd.to_datetime(session_features["timestamp"])
        else:
            dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)
            df_train_raw = pd.read_parquet(dataset_meta["raw_path"])
            df_train_adj = pd.read_parquet(dataset_meta["adj_path"])

            combined_raw = pd.concat([df_train_raw, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            combined_adj = pd.concat([df_train_adj, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            tmp_raw = os.path.join(self.fresh_dir, f"_v3_eval_raw_{target_str}.parquet")
            tmp_adj = os.path.join(self.fresh_dir, f"_v3_eval_adj_{target_str}.parquet")
            combined_raw.to_parquet(tmp_raw)
            combined_adj.to_parquet(tmp_adj)

            feat_pipeline = FeaturePipeline(
                raw_parquet_path=tmp_raw,
                adj_parquet_path=tmp_adj
            )
            full_features = feat_pipeline.compute_all_features()

            for f in [tmp_raw, tmp_adj]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            full_features["timestamp"] = pd.to_datetime(full_features["timestamp"])
            session_features = full_features[full_features["timestamp"].dt.strftime("%Y-%m-%d") == day_hyphen].copy()

        return session_df, session_features, manifest, model

    def run_day(
        self,
        target_day: date,
        session_df: Optional[pd.DataFrame] = None,
        capital_override: Optional[float] = None,
        is_forward_validation: bool = False
    ) -> DailySessionResultV3:
        """
        Executes the full V3 adaptive pipeline for a single trading day D.
        """
        exec_label = FORWARD_VALIDATION_LABEL if is_forward_validation else "HISTORICAL REPLAY / BASELINE"
        disclaimer = FORWARD_VALIDATION_LABEL if is_forward_validation else REPLAY_DISCLAIMER

        logger.info("=" * 80)
        logger.info(f"  ALPHANSE V3 ADAPTIVE 60m PIPELINE — SESSION: {target_day}  ")
        logger.info(f"  MODE: {exec_label}")
        if not is_forward_validation:
            logger.info(f"  DISCLAIMER: {REPLAY_DISCLAIMER}")
        logger.info("=" * 80)

        session_df, session_features, manifest, model = self.get_session_environment(
            target_day=target_day,
            session_df=session_df,
            is_forward_validation=is_forward_validation
        )

        capital = capital_override or self.initial_capital
        trader = SessionTraderV3(
            manifest=manifest,
            initial_capital=capital,
            horizon_bars=self.horizon_bars,
            is_forward_validation=is_forward_validation
        )
        trades = trader.run_session(session_df, session_features, model)

        # Save trades to V3 audit ledger
        self.audit_ledger.save_trades(manifest.session_date, trades)

        n_trades = len(trades)
        gross_pnl = sum(t.gross_pnl_rupees for t in trades)
        net_pnl = sum(t.net_pnl_rupees for t in trades)
        avg_net_profit = (net_pnl / n_trades) if n_trades > 0 else 0.0
        avg_net_bps = (sum(t.net_return_bps for t in trades) / n_trades) if n_trades > 0 else 0.0
        wins = sum(1 for t in trades if t.net_pnl_rupees > 0)
        win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
        cash_holding = (n_trades == 0)

        result = DailySessionResultV3(
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
            cash_holding_session=cash_holding,
            execution_type="FORWARD_VALIDATION" if is_forward_validation else "HISTORICAL_REPLAY",
            disclaimer=disclaimer
        )

        logger.info("-" * 80)
        logger.info(f"V3 SESSION RESULT: {manifest.session_date} [{exec_label}]")
        logger.info(f"  Model Version:         {manifest.model_version}")
        logger.info(f"  Horizon:               {self.horizon_bars * 5}m ({self.horizon_bars} bars)")
        logger.info(f"  Regime at Open:        {manifest.regime_at_open}")
        logger.info(f"  Total Trades Executed: {n_trades} {'(CASH HELD)' if cash_holding else ''}")
        logger.info(f"  Gross PnL:             ₹{gross_pnl:.2f}")
        logger.info(f"  Net PnL:               ₹{net_pnl:.2f}")
        logger.info(f"  Avg Net Profit/Trade:  ₹{avg_net_profit:.2f}")
        logger.info(f"  Win Rate:              {win_rate:.1f}%")
        logger.info(f"  Ending Capital:        ₹{trader.total_capital:.2f}")
        if not is_forward_validation:
            logger.info(f"  Audit Disclaimer:      {REPLAY_DISCLAIMER}")
        logger.info("-" * 80)

        return result

    def run_historical_replay(
        self,
        session_dates: List[date]
    ) -> List[DailySessionResultV3]:
        """
        Executes sequential historical walk-forward replay across past sessions.
        STRICTLY LABELED AS HISTORICAL REPLAY / BASELINE — NOT FRESH VALIDATION.
        """
        results = []
        running_capital = self.initial_capital

        logger.info("=" * 80)
        logger.info("  STARTING V3 HISTORICAL REPLAY / BASELINE WALK-FORWARD  ")
        logger.info(f"  DISCLAIMER: {REPLAY_DISCLAIMER}")
        logger.info("=" * 80)

        for d in sorted(session_dates):
            res = self.run_day(d, capital_override=running_capital, is_forward_validation=False)
            results.append(res)
            running_capital = res.ending_capital

        return results

    def get_multimodel_session_environment(
        self,
        target_day: Any,
        session_df: Optional[pd.DataFrame] = None,
        is_forward_validation: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame, DailyModelManifestV3, MultiModelRegistryV3]:
        """
        Prepares session environment with ALL 5 active research models (V2_15M, HYPO001, HYPO002, HYPO003, V3_60M).
        Independently trains/loads each model, passes sanity gates, freezes artifacts, and generates master manifest.
        """
        if isinstance(target_day, str):
            target_str_clean = target_day.replace("-", "")
            target_date = datetime.strptime(target_str_clean, "%Y%m%d").date()
        else:
            target_date = target_day

        target_str = target_date.strftime("%Y%m%d")
        day_hyphen = target_date.strftime("%Y-%m-%d")

    def prepare_multimodel_premarket(
        self,
        target_day: Any,
        is_forward_validation: bool = True
    ) -> Tuple[DailyModelManifestV3, MultiModelRegistryV3]:
        """
        Executes pre-market retraining, validation, and freezing of all 5 research models
        strictly on D-1 data before the market opens (does not require session market data).
        """
        if isinstance(target_day, str):
            target_str_clean = target_day.replace("-", "")
            target_date = datetime.strptime(target_str_clean, "%Y%m%d").date()
        else:
            target_date = target_day

        target_str = target_date.strftime("%Y%m%d")
        day_hyphen = target_date.strftime("%Y-%m-%d")

        # Step 1: Prepare dataset strictly <= D-1
        dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)

        # Step 2: Train all 5 models independently with failure isolation
        self.multimodel_trainer.train_all_session_models(
            target_day=target_date,
            dataset_meta=dataset_meta
        )
        status_summary = self.multimodel_registry.get_status_summary()

        # Step 3: Create Master Session Manifest linking all models
        model_hashes_dict = {
            m_id: meta.model_hash
            for m_id, meta in self.multimodel_registry.metadata.items()
        }
        master_hash = hashlib.sha256("".join(sorted(model_hashes_dict.values())).encode()).hexdigest()

        first_key = list(self.multimodel_registry.metadata.keys())[0]
        regime = self.multimodel_registry.metadata[first_key].regime

        manifest = DailyModelManifestV3(
            session_date=day_hyphen,
            data_cutoff=dataset_meta["data_cutoff"],
            dataset_hash=dataset_meta["dataset_hash"],
            feature_version=self.multimodel_trainer.feature_schema_hash,
            model_version=f"AlphaNSE_V3_MultiModel_{target_str}_v1",
            model_hash=master_hash,
            target_column="multi_horizon_15m_30m_60m",
            horizon_bars=12,
            training_window=f"Historical to {dataset_meta['data_cutoff'][:10]}",
            training_rows=dataset_meta["training_rows"],
            validation_result={
                "multimodel_status": status_summary,
                "model_hashes": model_hashes_dict
            },
            regime_at_open=regime,
            created_at=datetime.now(timezone.utc).isoformat(),
            experiment_mode=EXPERIMENT_MODE,
            profitability_claim=PROFITABILITY_CLAIM,
            disclaimer=FORWARD_VALIDATION_LABEL if is_forward_validation else REPLAY_DISCLAIMER
        )
        self.audit_ledger.save_manifest(manifest)
        logger.info(f"[MULTIMODEL PREMARKET] Master manifest saved for {day_hyphen}. Hash: {master_hash[:16]}...")
        return manifest, self.multimodel_registry

    def get_multimodel_session_environment(
        self,
        target_day: Any,
        session_df: Optional[pd.DataFrame] = None,
        is_forward_validation: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame, DailyModelManifestV3, MultiModelRegistryV3]:
        """
        Prepares session environment with ALL 5 active research models (V2_15M, HYPO001, HYPO002, HYPO003, V3_60M).
        Loads market data, features, manifest, and active model registry for intraday bar streaming.
        """
        if isinstance(target_day, str):
            target_str_clean = target_day.replace("-", "")
            target_date = datetime.strptime(target_str_clean, "%Y%m%d").date()
        else:
            target_date = target_day

        target_str = target_date.strftime("%Y%m%d")
        day_hyphen = target_date.strftime("%Y-%m-%d")

        # 1. Load or prepare manifest and models
        manifest = self.audit_ledger.load_manifest(day_hyphen)
        self.multimodel_registry.load_registry()

        status_summary = self.multimodel_registry.get_status_summary()
        if manifest is None or status_summary["valid_model_count"] == 0:
            manifest, _ = self.prepare_multimodel_premarket(target_date, is_forward_validation=is_forward_validation)

        # 2. Load session market data
        if session_df is None:
            session_file = os.path.join(self.fresh_dir, f"session_{target_str}_5m.parquet")
            if not os.path.exists(session_file):
                raise FileNotFoundError(f"Session market data not found: {session_file}")
            session_df = pd.read_parquet(session_file)

        session_df["timestamp"] = pd.to_datetime(session_df["timestamp"])
        session_df = session_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

        # 3. Session Features
        features_cache_path = os.path.join(self.fresh_dir, f"features_{target_str}.parquet")
        if os.path.exists(features_cache_path):
            session_features = pd.read_parquet(features_cache_path)
            session_features["timestamp"] = pd.to_datetime(session_features["timestamp"])
        else:
            dataset_meta = self.dataset_updater.prepare_dataset_for_day(target_date)
            df_train_raw = pd.read_parquet(dataset_meta["raw_path"])
            df_train_adj = pd.read_parquet(dataset_meta["adj_path"])

            combined_raw = pd.concat([df_train_raw, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            combined_adj = pd.concat([df_train_adj, session_df], ignore_index=True).drop_duplicates(
                subset=["symbol", "timestamp"]
            ).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            tmp_raw = os.path.join(self.fresh_dir, f"_v3_eval_raw_{target_str}.parquet")
            tmp_adj = os.path.join(self.fresh_dir, f"_v3_eval_adj_{target_str}.parquet")
            combined_raw.to_parquet(tmp_raw)
            combined_adj.to_parquet(tmp_adj)

            feat_pipeline = FeaturePipeline(
                raw_parquet_path=tmp_raw,
                adj_parquet_path=tmp_adj
            )
            full_features = feat_pipeline.compute_all_features()

            for f in [tmp_raw, tmp_adj]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            full_features["timestamp"] = pd.to_datetime(full_features["timestamp"])
            session_features = full_features[full_features["timestamp"].dt.strftime("%Y-%m-%d") == day_hyphen].copy()

        return session_df, session_features, manifest, self.multimodel_registry

    def run_multimodel_day(
        self,
        target_day: date,
        session_df: Optional[pd.DataFrame] = None,
        capital_override: Optional[float] = None,
        is_forward_validation: bool = True
    ) -> DailySessionResultV3:
        """
        Executes multi-model trading for Day D using the 5 active models.
        Saves both executed trades and complete CandidateDecisionAuditRecordV3 records.
        """
        exec_label = FORWARD_VALIDATION_LABEL if is_forward_validation else "HISTORICAL REPLAY / BASELINE"
        disclaimer = FORWARD_VALIDATION_LABEL if is_forward_validation else REPLAY_DISCLAIMER

        logger.info("=" * 80)
        logger.info(f"  ALPHANSE V3 MULTI-MODEL 5-MODEL PIPELINE — SESSION: {target_day}  ")
        logger.info(f"  MODE: {exec_label}")
        logger.info("=" * 80)

        session_df, session_features, manifest, registry = self.get_multimodel_session_environment(
            target_day=target_day,
            session_df=session_df,
            is_forward_validation=is_forward_validation
        )

        capital = capital_override or self.initial_capital
        trader = SessionTraderV3(
            manifest=manifest,
            initial_capital=capital,
            horizon_bars=self.horizon_bars,
            is_forward_validation=is_forward_validation
        )
        trades = trader.run_session(session_df, session_features, registry)

        # Save executed trades to V3 audit ledger
        self.audit_ledger.save_trades(manifest.session_date, trades)

        # Save complete candidate decision audits (Section 13 forensic ledger)
        if trader.candidate_audits:
            audit_path = self.audit_ledger.save_candidate_audits(manifest.session_date, trader.candidate_audits)
            logger.info(f"[AUDIT] Saved {len(trader.candidate_audits)} candidate decision records to {audit_path}")

        n_trades = len(trades)
        gross_pnl = sum(t.gross_pnl_rupees for t in trades)
        net_pnl = sum(t.net_pnl_rupees for t in trades)
        avg_net_profit = (net_pnl / n_trades) if n_trades > 0 else 0.0
        avg_net_bps = (sum(t.net_return_bps for t in trades) / n_trades) if n_trades > 0 else 0.0
        wins = sum(1 for t in trades if t.net_pnl_rupees > 0)
        win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
        cash_holding = (n_trades == 0)

        status_summary = registry.get_status_summary()

        result = DailySessionResultV3(
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
            cash_holding_session=cash_holding,
            execution_type="FORWARD_VALIDATION" if is_forward_validation else "HISTORICAL_REPLAY",
            disclaimer=disclaimer
        )

        logger.info("-" * 80)
        logger.info(f"V3 MULTI-MODEL SESSION RESULT: {manifest.session_date} [{exec_label}]")
        logger.info(f"  Active Valid Models:   {status_summary['valid_model_count']}/5 ({', '.join(status_summary['valid_models'])})")
        logger.info(f"  Total Trades:          {n_trades} {'(CASH HELD)' if cash_holding else ''}")
        logger.info(f"  Evaluated Candidates:  {len(trader.candidate_audits)}")
        logger.info(f"  Gross PnL:             ₹{gross_pnl:.2f}")
        logger.info(f"  Net PnL:               ₹{net_pnl:.2f}")
        logger.info(f"  Ending Capital:        ₹{trader.total_capital:.2f}")
        logger.info("-" * 80)

        return result
