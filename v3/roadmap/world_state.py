"""
AlphaNSE V3 — Pre-Market Market World State Builder (Section 19).
Synthesizes market regime, sector dynamics, candidate universe, execution conditions,
and risk/capital boundaries into an immutable PREMARKET_WORLD_STATE prior to model execution.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import json
import os


@dataclass
class CandidateStockSummary:
    symbol: str
    last_price: float
    rank_score: float
    liquidity_score: float
    sector: str
    relative_strength_bps: float
    atr_14: float
    expected_spread_bps: float
    expected_slippage_bps: float


@dataclass
class MarketWorldState:
    """Authoritative pre-market world state representation (Section 19)."""
    session_date: str
    cutoff_timestamp: str
    market_regime: str                # "LOW_VOL", "NORMAL_VOL", "HIGH_VOL"
    market_direction: int             # +1, -1, 0
    volatility_index: float           # India VIX
    liquidity_environment: str       # "AMPLIFIED", "NORMAL", "CONSTRAINED"
    candidate_universe: List[str]
    candidate_summaries: Dict[str, Dict[str, Any]]
    sector_regimes: Dict[str, str]
    available_capital: float
    risk_budget_rupees: float
    min_net_hurdle_rupees: float = 0.80
    min_net_hurdle_bps: float = 0.0
    execution_friction_bps: float = 14.7
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorldStateBuilderV3:
    """
    Constructs MarketWorldState from the frozen pre-market snapshot and capital parameters.
    """

    def build_world_state(
        self,
        frozen_snapshot: Dict[str, Any],
        available_capital: float = 5000.0,
        risk_budget_pct: float = 0.01,
        output_path: Optional[str] = None
    ) -> MarketWorldState:
        """Constructs canonical MarketWorldState."""
        m_state = frozen_snapshot.get("market_state", {})
        session_date = frozen_snapshot.get("session_date", "2026-09-25")
        cutoff = frozen_snapshot.get("cutoff_timestamp", f"{session_date}T09:05:00+05:30")

        m_wide = m_state.get("market_wide", {})
        per_sym = m_state.get("per_symbol_intelligence", {})

        candidate_universe = list(per_sym.keys())
        candidate_summaries = {}

        # Rank candidates dynamically based on liquidity and momentum
        for sym, intel in per_sym.items():
            price_info = intel.get("price", {})
            depth_info = intel.get("depth", {})
            sec_info = intel.get("sector_peer", {})

            last_p = price_info.get("last_close", 500.0)
            mom = price_info.get("momentum_60m_bps", 0.0)
            liq = depth_info.get("liquidity_score", 80.0)
            rel_str = sec_info.get("stock_vs_nifty_strength_bps", 0.0)

            # Combined ranking score: momentum + relative strength + liquidity
            rank = (mom * 0.4) + (rel_str * 0.4) + (liq * 0.2)

            cand = CandidateStockSummary(
                symbol=sym,
                last_price=last_p,
                rank_score=round(rank, 2),
                liquidity_score=liq,
                sector=sec_info.get("sector_name", "UNKNOWN"),
                relative_strength_bps=rel_str,
                atr_14=price_info.get("atr_14", 10.0),
                expected_spread_bps=depth_info.get("spread_bps", 1.0),
                expected_slippage_bps=2.0
            )
            candidate_summaries[sym] = asdict(cand)

        # Sort universe by ranking
        sorted_universe = sorted(
            candidate_universe,
            key=lambda s: candidate_summaries[s]["rank_score"],
            reverse=True
        )

        sector_regimes = {
            "NIFTY_FIN_SERVICE": "BULLISH_TREND",
            "NIFTY_IT": "RANGE_BOUND"
        }

        risk_budget = available_capital * risk_budget_pct

        world_state = MarketWorldState(
            session_date=session_date,
            cutoff_timestamp=cutoff,
            market_regime=m_wide.get("market_regime", "NORMAL_VOL"),
            market_direction=m_wide.get("market_direction", 1),
            volatility_index=m_wide.get("india_vix", 14.5),
            liquidity_environment="NORMAL",
            candidate_universe=sorted_universe,
            candidate_summaries=candidate_summaries,
            sector_regimes=sector_regimes,
            available_capital=available_capital,
            risk_budget_rupees=round(risk_budget, 2),
            min_net_hurdle_rupees=0.80,
            min_net_hurdle_bps=0.0,
            execution_friction_bps=14.7,
            created_at=frozen_snapshot.get("frozen_at", "")
        )

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(world_state.to_dict(), f, indent=2)

        return world_state
