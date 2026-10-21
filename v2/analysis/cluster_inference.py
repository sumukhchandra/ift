"""
Cluster-Robust Statistical Inference & Session Block Bootstrap for AlphaNSE V2.
Addresses cross-sectional and temporal cluster dependence across trading sessions and symbols:
  1. Session Block-Bootstrap: Resamples whole trading sessions with replacement (primary robustness check).
  2. Session-Clustered Standard Errors (59 clusters).
  3. Symbol-Clustered Standard Errors (10 clusters, noted as small-N).
  4. Two-Way Clustered Standard Errors (Cameron, Gelbach & Miller, 2011).
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapCIResult:
    metric_name: str
    observed_mean: float
    ci_lower_95: float
    ci_upper_95: float
    bootstrap_std: float
    n_sessions: int
    n_trades: int
    is_positive_significant: bool


@dataclass(frozen=True)
class ClusteredSEStats:
    observed_mean: float
    pooled_se: float
    session_clustered_se: float
    symbol_clustered_se: float
    twoway_clustered_se: float
    session_t_stat: float
    twoway_t_stat: float
    n_sessions: int
    n_symbols: int
    n_observations: int


class SessionBlockBootstrap:
    """
    Nonparametric block bootstrap that resamples entire trading sessions with replacement.
    Preserves all intraday cross-sectional and temporal correlation structures.
    """

    def __init__(self, n_bootstrap_iterations: int = 1000, random_seed: int = 42):
        self.n_bootstrap = n_bootstrap_iterations
        self.random_seed = random_seed

    def run_session_bootstrap(
        self,
        trades_df: pd.DataFrame,
        metric_col: str,
        session_col: str = "date"
    ) -> BootstrapCIResult:
        """
        Runs session block bootstrap on trades dataframe.
        """
        if trades_df.empty or metric_col not in trades_df.columns:
            return BootstrapCIResult(
                metric_name=metric_col,
                observed_mean=0.0,
                ci_lower_95=0.0,
                ci_upper_95=0.0,
                bootstrap_std=0.0,
                n_sessions=0,
                n_trades=0,
                is_positive_significant=False
            )

        df = trades_df.copy()
        if session_col not in df.columns:
            df[session_col] = pd.to_datetime(df["timestamp"]).dt.date

        unique_sessions = np.array(sorted(df[session_col].unique()))
        n_sessions = len(unique_sessions)
        observed_mean = float(df[metric_col].mean())

        if n_sessions <= 2:
            return BootstrapCIResult(
                metric_name=metric_col,
                observed_mean=observed_mean,
                ci_lower_95=observed_mean,
                ci_upper_95=observed_mean,
                bootstrap_std=0.0,
                n_sessions=n_sessions,
                n_trades=len(df),
                is_positive_significant=(observed_mean > 0)
            )

        # Pre-group trade values by session for fast bootstrap vectorized aggregation
        session_values = [df[df[session_col] == s][metric_col].values for s in unique_sessions]

        rng = np.random.default_rng(self.random_seed)
        boot_means = np.empty(self.n_bootstrap)

        for b in range(self.n_bootstrap):
            sampled_indices = rng.integers(0, n_sessions, size=n_sessions)
            sampled_values = np.concatenate([session_values[i] for i in sampled_indices if len(session_values[i]) > 0])
            boot_means[b] = np.mean(sampled_values) if len(sampled_values) > 0 else 0.0

        ci_lower = float(np.percentile(boot_means, 2.5))
        ci_upper = float(np.percentile(boot_means, 97.5))
        boot_std = float(np.std(boot_means))

        return BootstrapCIResult(
            metric_name=metric_col,
            observed_mean=round(observed_mean, 2),
            ci_lower_95=round(ci_lower, 2),
            ci_upper_95=round(ci_upper, 2),
            bootstrap_std=round(boot_std, 2),
            n_sessions=n_sessions,
            n_trades=len(df),
            is_positive_significant=(ci_lower > 0.0)
        )


class ClusterRobustInference:
    """
    Computes analytical cluster-robust standard errors for mean expectancy and returns.
    Implements session-clustered, symbol-clustered, and two-way clustered formulas.
    """

    @staticmethod
    def compute_clustered_stats(
        df: pd.DataFrame,
        value_col: str,
        session_col: str = "date",
        symbol_col: str = "symbol"
    ) -> ClusteredSEStats:
        """
        Computes pooled, session-clustered, symbol-clustered, and two-way clustered SEs.
        """
        clean_df = df.copy()
        if session_col not in clean_df.columns:
            clean_df[session_col] = pd.to_datetime(clean_df["timestamp"]).dt.date

        vals = clean_df[value_col].dropna().values
        n_obs = len(vals)
        if n_obs < 5:
            return ClusteredSEStats(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, n_obs)

        mean_val = float(np.mean(vals))
        u = vals - mean_val  # de-meaned residuals

        # 1. Pooled OLS variance
        pooled_var = np.sum(u ** 2) / (n_obs * (n_obs - 1))
        pooled_se = float(np.sqrt(max(0.0, pooled_var)))

        # 2. Session-Clustered Variance (G_session = n_sessions)
        session_groups = clean_df.groupby(session_col)[value_col].apply(lambda s: np.sum(s - mean_val)).values
        n_sess = len(session_groups)
        if n_sess > 1:
            dfc_sess = (n_sess / (n_sess - 1)) * ((n_obs - 1) / n_obs)
            sess_var = dfc_sess * (np.sum(session_groups ** 2) / (n_obs ** 2))
            sess_se = float(np.sqrt(max(0.0, sess_var)))
        else:
            sess_var = pooled_var
            sess_se = pooled_se

        # 3. Symbol-Clustered Variance (G_symbol = n_symbols)
        symbol_groups = clean_df.groupby(symbol_col)[value_col].apply(lambda s: np.sum(s - mean_val)).values
        n_syms = len(symbol_groups)
        if n_syms > 1:
            dfc_sym = (n_syms / (n_syms - 1)) * ((n_obs - 1) / n_obs)
            sym_var = dfc_sym * (np.sum(symbol_groups ** 2) / (n_obs ** 2))
            sym_se = float(np.sqrt(max(0.0, sym_var)))
        else:
            sym_var = pooled_var
            sym_se = pooled_se

        # 4. Intersection Variance (session x symbol)
        inter_groups = clean_df.groupby([session_col, symbol_col])[value_col].apply(lambda s: np.sum(s - mean_val)).values
        n_inter = len(inter_groups)
        if n_inter > 1:
            dfc_inter = (n_inter / (n_inter - 1)) * ((n_obs - 1) / n_obs)
            inter_var = dfc_inter * (np.sum(inter_groups ** 2) / (n_obs ** 2))
        else:
            inter_var = pooled_var

        # Two-Way Variance: V_twoway = V_session + V_symbol - V_inter
        twoway_var = max(1e-12, sess_var + sym_var - inter_var)
        twoway_se = float(np.sqrt(twoway_var))

        sess_t = mean_val / sess_se if sess_se > 0 else 0.0
        twoway_t = mean_val / twoway_se if twoway_se > 0 else 0.0

        return ClusteredSEStats(
            observed_mean=round(mean_val, 4),
            pooled_se=round(pooled_se, 4),
            session_clustered_se=round(sess_se, 4),
            symbol_clustered_se=round(sym_se, 4),
            twoway_clustered_se=round(twoway_se, 4),
            session_t_stat=round(sess_t, 2),
            twoway_t_stat=round(twoway_t, 2),
            n_sessions=n_sess,
            n_symbols=n_syms,
            n_observations=n_obs
        )
