"""
AlphaNSE V2 Adaptive Research Matrix Engine.
Implements the 3-Phase Scientific Protocol:
  Phase A: Exploratory Research Matrix across Track, Horizon, Conviction, Direction, and Cost Scenarios.
           Identifies the "Selected Candidate" based on risk-adjusted net expectancy and unit economics.
  Phase B: Cryptographic Freeze of Selected Candidate into an immutable FrozenCandidateManifest.
  Phase C: Fresh Out-of-Sample Validation Engine with strict sample gates (min 30 trades, min 10 sessions, 3 folds)
           and mandatory INCONCLUSIVE verdict if opportunity count is insufficient.
"""

import os
import json
import hashlib
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

from .audit_ledger import DailyModelManifest, TradeAuditRecord
from .opportunity_ranker import OpportunityRanker, ConvictionTier
from .session_trader import SessionTrader
from .futures_trader import FuturesSessionTrader, FuturesCostScenario, FuturesTradeAuditRecord
from v2.risk.dynamic_cost_model import DynamicCostModel

logger = logging.getLogger(__name__)


class TrackType(str, Enum):
    CASH_EQUITY = "CASH_EQUITY"
    EQUITY_FUTURES = "EQUITY_FUTURES"


@dataclass(frozen=True)
class ResearchSliceConfig:
    track: TrackType
    horizon_bars: int                 # 3 (15m), 6 (30m), 12 (60m), 999 (EOD)
    conviction_tier: ConvictionTier
    direction_filter: Optional[int]   # None (Both), 1 (Longs only), -1 (Shorts only)
    cost_scenario: str                # "BASE", "STRESSED", "STATUTORY_ONLY"
    capital: float = 5000.0


@dataclass(frozen=True)
class SliceDistributionMetrics:
    slice_id: str
    track: str
    horizon_name: str
    horizon_bars: int
    conviction: str
    direction: str
    cost_scenario: str
    total_trades: int
    sessions_run: int
    trades_per_session: float
    directional_accuracy_pct: float
    gross_win_rate_pct: float
    net_win_rate_pct: float
    mean_gross_bps: float
    mean_cost_bps: float
    mean_net_bps: float
    total_gross_pnl_inr: float
    total_net_pnl_inr: float
    mean_net_pnl_per_trade_inr: float
    avg_winner_inr: float
    avg_loser_inr: float
    profit_factor: float
    expectancy_inr: float
    max_drawdown_inr: float
    ci_95_lower_inr: float
    ci_95_upper_inr: float
    session_win_rate_pct: float       # Percentage of sessions with positive net P&L
    target_hurdle_cleared: bool       # Net ₹/trade >= ₹0.80

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenCandidateManifest:
    """Cryptographic specification of the Selected Candidate frozen after Phase A exploration."""
    candidate_id: str
    created_at: str
    config: Dict[str, Any]
    config_hash: str                  # SHA-256 of configuration
    feature_version: str
    model_version: str
    model_hash: str
    dataset_hash: str
    phase_a_metrics: Dict[str, Any]
    status: str = "FROZEN_FOR_VALIDATION"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ValidationVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class PhaseCValidationReport:
    candidate_id: str
    total_trades: int
    total_sessions: int
    total_folds: int
    mean_net_pnl_per_trade: float
    net_expectancy: float
    stressed_expectancy: float
    ci_lower: float
    ci_upper: float
    max_drawdown_pct: float
    sample_sufficient: bool
    verdict: ValidationVerdict
    verdict_rationale: str


class AdaptiveResearchMatrixEngine:
    """
    Executes multi-dimensional matrix evaluations and manages Phase A -> B -> C protocol.
    """

    def __init__(
        self,
        frozen_dir: str = "v2/adaptive/frozen_candidates",
        reports_dir: str = "v2/adaptive/reports"
    ):
        self.frozen_dir = frozen_dir
        self.reports_dir = reports_dir
        os.makedirs(frozen_dir, exist_ok=True)
        os.makedirs(reports_dir, exist_ok=True)

    def evaluate_slice(
        self,
        config: ResearchSliceConfig,
        sessions_data: Dict[str, Dict[str, Any]]
    ) -> Tuple[SliceDistributionMetrics, List[Any]]:
        """
        Executes a single ResearchSliceConfig across all provided sessions.
        `sessions_data` format: {session_date: {"session_df": df, "feature_df": df, "manifest": m, "model": model}}
        """
        all_trades: List[Any] = []
        session_pnls: List[float] = []

        horizon_label = (
            "15m" if config.horizon_bars == 3 else
            "30m" if config.horizon_bars == 6 else
            "60m" if config.horizon_bars == 12 else
            "EOD" if config.horizon_bars >= 900 else
            f"{config.horizon_bars}bars"
        )

        for s_date, s_info in sorted(sessions_data.items()):
            session_df = s_info["session_df"]
            feature_df = s_info["feature_df"]
            manifest = s_info["manifest"]
            model = s_info["model"]

            if config.track == TrackType.CASH_EQUITY:
                ranker = OpportunityRanker(
                    conviction_filter=config.conviction_tier,
                    min_env_bps=2.0,
                    min_net_rupees_target=0.0  # Measure full distribution during research
                )
                trader = SessionTrader(
                    manifest=manifest,
                    initial_capital=config.capital,
                    horizon_bars=config.horizon_bars,
                    ranker=ranker,
                    direction_filter=config.direction_filter
                )
                day_trades = trader.run_session(session_df, feature_df, model)

                # Filter by direction if requested
                if config.direction_filter is not None:
                    day_trades = [t for t in day_trades if t.direction == config.direction_filter]

                # Filter by conviction if needed
                if config.conviction_tier == ConvictionTier.EXTREME_TOP_15:
                    day_trades = [t for t in day_trades if t.conviction_tier == ConvictionTier.EXTREME_TOP_15.value]
                elif config.conviction_tier == ConvictionTier.Q4_TOP_CONVICTION:
                    day_trades = [t for t in day_trades if t.conviction_tier in [ConvictionTier.Q4_TOP_CONVICTION.value, ConvictionTier.EXTREME_TOP_15.value]]

                day_net_pnl = sum(t.net_pnl_rupees for t in day_trades)
                session_pnls.append(day_net_pnl)
                all_trades.extend(day_trades)

            elif config.track == TrackType.EQUITY_FUTURES:
                scenario_enum = (
                    FuturesCostScenario.STATUTORY_ONLY if config.cost_scenario == "STATUTORY_ONLY" else
                    FuturesCostScenario.STRESSED if config.cost_scenario == "STRESSED" else
                    FuturesCostScenario.BASE
                )
                trader = FuturesSessionTrader(
                    manifest=manifest,
                    capital=config.capital if config.capital > 50000 else 500000.0,
                    retail_capital_ref=5000.0,
                    horizon_bars=config.horizon_bars,
                    cost_scenario=scenario_enum,
                    conviction_filter=config.conviction_tier
                )
                day_trades = trader.run_session(session_df, feature_df, model)

                if config.direction_filter is not None:
                    day_trades = [t for t in day_trades if t.direction == config.direction_filter]

                day_net_pnl = sum(t.net_pnl_rupees for t in day_trades)
                session_pnls.append(day_net_pnl)
                all_trades.extend(day_trades)

        # Compute complete statistical distribution
        n_trades = len(all_trades)
        n_sessions = len(sessions_data)
        t_per_sess = n_trades / n_sessions if n_sessions > 0 else 0.0

        if n_trades == 0:
            slice_id = f"{config.track.value}_{horizon_label}_{config.conviction_tier.value}_{config.direction_filter}_{config.cost_scenario}"
            metrics = SliceDistributionMetrics(
                slice_id=slice_id,
                track=config.track.value,
                horizon_name=horizon_label,
                horizon_bars=config.horizon_bars,
                conviction=config.conviction_tier.value,
                direction="BOTH" if config.direction_filter is None else ("LONGS" if config.direction_filter == 1 else "SHORTS"),
                cost_scenario=config.cost_scenario,
                total_trades=0,
                sessions_run=n_sessions,
                trades_per_session=0.0,
                directional_accuracy_pct=0.0,
                gross_win_rate_pct=0.0,
                net_win_rate_pct=0.0,
                mean_gross_bps=0.0,
                mean_cost_bps=0.0,
                mean_net_bps=0.0,
                total_gross_pnl_inr=0.0,
                total_net_pnl_inr=0.0,
                mean_net_pnl_per_trade_inr=0.0,
                avg_winner_inr=0.0,
                avg_loser_inr=0.0,
                profit_factor=0.0,
                expectancy_inr=0.0,
                max_drawdown_inr=0.0,
                ci_95_lower_inr=0.0,
                ci_95_upper_inr=0.0,
                session_win_rate_pct=0.0,
                target_hurdle_cleared=False
            )
            return metrics, all_trades

        gross_returns = np.array([t.gross_return_bps for t in all_trades])
        cost_returns = np.array([t.cost_bps for t in all_trades])
        net_returns = np.array([t.net_return_bps for t in all_trades])
        net_pnls = np.array([t.net_pnl_rupees for t in all_trades])

        dir_acc = float(np.mean(gross_returns > 0) * 100.0)
        gross_win_rate = float(np.mean(gross_returns > 0) * 100.0)
        net_win_rate = float(np.mean(net_pnls > 0) * 100.0)

        mean_gross_bps = float(np.mean(gross_returns))
        mean_cost_bps = float(np.mean(cost_returns))
        mean_net_bps = float(np.mean(net_returns))

        total_net_pnl = float(np.sum(net_pnls))
        mean_net_pnl = float(np.mean(net_pnls))

        winners = net_pnls[net_pnls > 0]
        losers = net_pnls[net_pnls < 0]
        avg_winner = float(np.mean(winners)) if len(winners) > 0 else 0.0
        avg_loser = float(np.mean(losers)) if len(losers) > 0 else 0.0

        sum_win = np.sum(winners) if len(winners) > 0 else 0.0
        sum_loss = abs(np.sum(losers)) if len(losers) > 0 else 0.0
        profit_factor = float(sum_win / sum_loss) if sum_loss > 0 else (99.0 if sum_win > 0 else 0.0)

        # Expectancy formula: (Win% * AvgWin) - (Loss% * |AvgLoss|)
        win_prob = len(winners) / n_trades
        loss_prob = len(losers) / n_trades
        expectancy_inr = (win_prob * avg_winner) - (loss_prob * abs(avg_loser))

        # Max drawdown in INR
        cum_pnl = np.cumsum(net_pnls)
        peak = np.maximum.accumulate(cum_pnl)
        drawdowns = peak - cum_pnl
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # 95% Confidence Interval for Mean Net P&L (Bootstrap)
        if n_trades >= 5:
            boot_means = [np.mean(np.random.choice(net_pnls, size=n_trades, replace=True)) for _ in range(500)]
            ci_lower = float(np.percentile(boot_means, 2.5))
            ci_upper = float(np.percentile(boot_means, 97.5))
        else:
            ci_lower = mean_net_pnl
            ci_upper = mean_net_pnl

        session_win_rate = float(np.mean(np.array(session_pnls) > 0) * 100.0) if session_pnls else 0.0
        target_cleared = (mean_net_pnl >= 0.80) and (expectancy_inr > 0)

        slice_id = f"{config.track.value}_{horizon_label}_{config.conviction_tier.value}_{config.direction_filter}_{config.cost_scenario}"

        metrics = SliceDistributionMetrics(
            slice_id=slice_id,
            track=config.track.value,
            horizon_name=horizon_label,
            horizon_bars=config.horizon_bars,
            conviction=config.conviction_tier.value,
            direction="BOTH" if config.direction_filter is None else ("LONGS" if config.direction_filter == 1 else "SHORTS"),
            cost_scenario=config.cost_scenario,
            total_trades=n_trades,
            sessions_run=n_sessions,
            trades_per_session=round(t_per_sess, 1),
            directional_accuracy_pct=round(dir_acc, 1),
            gross_win_rate_pct=round(gross_win_rate, 1),
            net_win_rate_pct=round(net_win_rate, 1),
            mean_gross_bps=round(mean_gross_bps, 2),
            mean_cost_bps=round(mean_cost_bps, 2),
            mean_net_bps=round(mean_net_bps, 2),
            total_gross_pnl_inr=round(float(np.sum(gross_returns / 10000.0 * 1600.0)), 2),
            total_net_pnl_inr=round(total_net_pnl, 2),
            mean_net_pnl_per_trade_inr=round(mean_net_pnl, 2),
            avg_winner_inr=round(avg_winner, 2),
            avg_loser_inr=round(avg_loser, 2),
            profit_factor=round(profit_factor, 2),
            expectancy_inr=round(expectancy_inr, 2),
            max_drawdown_inr=round(max_dd, 2),
            ci_95_lower_inr=round(ci_lower, 2),
            ci_95_upper_inr=round(ci_upper, 2),
            session_win_rate_pct=round(session_win_rate, 1),
            target_hurdle_cleared=target_cleared
        )
        return metrics, all_trades

    def freeze_selected_candidate(
        self,
        candidate_config: ResearchSliceConfig,
        phase_a_metrics: SliceDistributionMetrics,
        latest_manifest: DailyModelManifest
    ) -> FrozenCandidateManifest:
        """
        Phase B: Immutably freezes the Selected Candidate into a cryptographically hashed manifest.
        """
        config_dict = asdict(candidate_config)
        # Ensure enums serialize to strings
        config_dict["track"] = candidate_config.track.value
        config_dict["conviction_tier"] = candidate_config.conviction_tier.value

        config_bytes = json.dumps(config_dict, sort_keys=True).encode("utf-8")
        config_hash = hashlib.sha256(config_bytes).hexdigest()

        candidate_id = f"Candidate_{candidate_config.track.value}_{candidate_config.horizon_bars}b_{config_hash[:8]}"

        manifest = FrozenCandidateManifest(
            candidate_id=candidate_id,
            created_at=pd.Timestamp.now(tz="UTC").isoformat(),
            config=config_dict,
            config_hash=config_hash,
            feature_version=latest_manifest.feature_version,
            model_version=latest_manifest.model_version,
            model_hash=latest_manifest.model_hash,
            dataset_hash=latest_manifest.dataset_hash,
            phase_a_metrics=phase_a_metrics.to_dict(),
            status="FROZEN_FOR_VALIDATION"
        )

        out_path = os.path.join(self.frozen_dir, f"{candidate_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        logger.info(f"Selected Candidate frozen successfully: {out_path} (Hash: {config_hash[:16]})")
        return manifest

    def evaluate_phase_c_validation(
        self,
        candidate_manifest: FrozenCandidateManifest,
        fresh_trades: List[Any],
        fresh_sessions_count: int,
        folds_count: int = 3,
        stressed_net_pnl: Optional[float] = None
    ) -> PhaseCValidationReport:
        """
        Phase C: Evaluates a frozen candidate strictly against out-of-sample criteria:
          - Minimum 30 trades
          - Minimum 10 sessions
          - Minimum 3 folds
          - Positive mean net expectancy & stressed cost expectancy
          - IF SAMPLE INSUFFICIENT -> INCONCLUSIVE (never premature PASS).
        """
        n_trades = len(fresh_trades)
        net_pnls = np.array([t.net_pnl_rupees for t in fresh_trades]) if n_trades > 0 else np.array([])
        mean_net = float(np.mean(net_pnls)) if n_trades > 0 else 0.0

        # Sample sufficiency check
        sample_sufficient = (n_trades >= 30) and (fresh_sessions_count >= 10) and (folds_count >= 3)

        if not sample_sufficient:
            verdict = ValidationVerdict.INCONCLUSIVE
            rationale = (
                f"INSUFFICIENT SAMPLE SIZE (INCONCLUSIVE / CONTINUE): Completed {n_trades} trades across {fresh_sessions_count} sessions "
                f"(requires >= 30 trades across >= 10 sessions and >= 3 folds). "
                f"Per AlphaNSE scientific protocol, small samples cannot declare PASS or FAIL. Phase C evidence accumulation continues."
            )
            return PhaseCValidationReport(
                candidate_id=candidate_manifest.candidate_id,
                total_trades=n_trades,
                total_sessions=fresh_sessions_count,
                total_folds=folds_count,
                mean_net_pnl_per_trade=round(mean_net, 2),
                net_expectancy=round(mean_net, 2),
                stressed_expectancy=round(stressed_net_pnl if stressed_net_pnl is not None else mean_net, 2),
                ci_lower=0.0,
                ci_upper=0.0,
                max_drawdown_pct=0.0,
                sample_sufficient=False,
                verdict=verdict,
                verdict_rationale=rationale
            )

        # Calculate bootstrap CI
        boot_means = [np.mean(np.random.choice(net_pnls, size=n_trades, replace=True)) for _ in range(1000)]
        ci_lower = float(np.percentile(boot_means, 2.5))
        ci_upper = float(np.percentile(boot_means, 97.5))

        stressed_exp = stressed_net_pnl if stressed_net_pnl is not None else (mean_net - 0.50)

        # Full PASS criteria
        clears_pnl = mean_net >= 0.80
        clears_exp = mean_net > 0 and stressed_exp > 0
        clears_ci = ci_lower > -0.50

        if clears_pnl and clears_exp and clears_ci:
            verdict = ValidationVerdict.PASS
            rationale = (
                f"PASSED VALIDATION: Completed {n_trades} trades across {fresh_sessions_count} sessions. "
                f"Mean Net PnL = ₹{mean_net:.2f}/trade (>= ₹0.80 target), Stressed Expectancy = ₹{stressed_exp:.2f}, "
                f"95% CI = [₹{ci_lower:.2f}, ₹{ci_upper:.2f}]."
            )
        else:
            verdict = ValidationVerdict.FAIL
            rationale = (
                f"FAILED VALIDATION: Completed {n_trades} trades. Mean Net PnL = ₹{mean_net:.2f}/trade (target ₹0.80), "
                f"Stressed Expectancy = ₹{stressed_exp:.2f}."
            )

        return PhaseCValidationReport(
            candidate_id=candidate_manifest.candidate_id,
            total_trades=n_trades,
            total_sessions=fresh_sessions_count,
            total_folds=folds_count,
            mean_net_pnl_per_trade=round(mean_net, 2),
            net_expectancy=round(mean_net, 2),
            stressed_expectancy=round(stressed_exp, 2),
            ci_lower=round(ci_lower, 2),
            ci_upper=round(ci_upper, 2),
            max_drawdown_pct=0.0,
            sample_sufficient=True,
            verdict=verdict,
            verdict_rationale=rationale
        )
