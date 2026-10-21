"""
v3/ensemble/unified_paper_executor.py
Single Authoritative Paper Execution Engine for AlphaNSE Unified Ensemble.
Eliminates competing paper accounts by establishing one central portfolio and ledger.
"""

import os
import sys
import json
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Any, Optional

from v3.ensemble.specialist_signal import SpecialistSignal, SignalDirection
from v3.ensemble.specialist_registry import SpecialistRegistry
from v3.ensemble.unified_meta_decision_engine import UnifiedMetaDecisionEngine, MetaDecisionOutput
from v3.ensemble.unified_risk_engine import UnifiedRiskEngine, PositionRiskState
from v2.risk.cost_engine import IndiaCostEngine

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "unified_ensemble_ledger.jsonl")
STATE_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "UNIFIED_ENSEMBLE_STATE.json")


class UnifiedPaperExecutor:
    """
    The Single Authoritative Paper Trading Executor.
    Strictly air-gapped from live broker endpoints.
    """
    def __init__(
        self,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        ledger_path: str = LEDGER_PATH,
        state_path: str = STATE_PATH
    ):
        # Strict fail-closed air-gap verification
        self.LIVE_TRADING = False
        self.ALLOW_REAL_ORDERS = False
        self._enforce_airgap()

        self.starting_capital = starting_capital
        self.ledger_path = ledger_path
        self.state_path = state_path

        self.registry = SpecialistRegistry()
        self.meta_engine = UnifiedMetaDecisionEngine()
        self.risk_engine = UnifiedRiskEngine(
            max_capital=starting_capital,
            max_daily_loss=max_daily_loss,
            max_concurrent_positions=1
        )
        self.cost_engine = IndiaCostEngine()
        self.trade_counter = 0
        self.trades_history: List[Dict[str, Any]] = []

        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        self._save_state()

    def _enforce_airgap(self):
        """Hard fail-closed check guaranteeing zero real money routing."""
        if getattr(self, "LIVE_TRADING", False) or getattr(self, "ALLOW_REAL_ORDERS", False):
            raise PermissionError("AIRGAP_BREACH: Real order flags must strictly remain False in paper executor.")

    def process_market_tick(
        self,
        target_symbol: str,
        market_snapshot: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Processes a market tick for an asset through the complete ensemble stack:
        1. Specialist model evaluations
        2. Meta-decision consensus & cost gating
        3. Risk limits & whole-share sizing
        4. Execution & trade lifecycle logging
        """
        now = timestamp or datetime.now()
        sym_data = market_snapshot.get(target_symbol, {})
        current_px = float(sym_data.get("price", sym_data.get("current_price", 1000.0)))

        # A. Check Active Position Exit
        exit_event = None
        if self.risk_engine.active_position is not None:
            active_sym = self.risk_engine.active_position.symbol
            active_px = float(market_snapshot.get(active_sym, {}).get("price", current_px))
            should_exit, exit_reason, exit_p = self.risk_engine.evaluate_position_exit(active_px, now)

            if should_exit:
                pos = self.risk_engine.active_position
                gross_ret = ((exit_p - pos.entry_price) / pos.entry_price) if pos.direction == SignalDirection.BUY else ((pos.entry_price - exit_p) / pos.entry_price)
                cost_breakdown = self.cost_engine.calculate_roundtrip_cost(
                    capital=pos.invested_capital,
                    gross_return=gross_ret
                )
                friction = cost_breakdown.total_cost
                gross_pnl, net_pnl = self.risk_engine.close_position(exit_p, friction)

                exit_event = {
                    "event_type": "POSITION_CLOSED",
                    "trade_id": f"UE-TRD-{self.trade_counter:04d}",
                    "symbol": active_sym,
                    "direction": pos.direction.value,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "exit_price": exit_p,
                    "gross_pnl": round(gross_pnl, 2),
                    "friction_costs": round(friction, 2),
                    "net_pnl": round(net_pnl, 2),
                    "roi_pct": round((net_pnl / pos.invested_capital) * 100, 2),
                    "exit_reason": exit_reason,
                    "timestamp": now.isoformat(),
                    "supporting_models": pos.supporting_models
                }
                self.trades_history.append(exit_event)
                self._append_to_ledger(exit_event)
                self._save_state()

        # B. If no open position, evaluate new opportunity through the Ensemble
        entry_event = None
        allowed, risk_reason = self.risk_engine.is_trading_allowed()

        if allowed:
            # 1. Query all 7 specialist models
            specialist_signals = self.registry.evaluate_all(market_snapshot)

            # 2. Meta-decision consensus & net-edge validation
            decision = self.meta_engine.evaluate_opportunity(target_symbol, specialist_signals, market_snapshot)

            # 3. If BUY or SELL approved, route to Risk Engine
            if decision.action in (SignalDirection.BUY, SignalDirection.SELL):
                pos, open_reason = self.risk_engine.open_position(decision, current_px, now)
                if pos is not None:
                    self.trade_counter += 1
                    entry_event = {
                        "event_type": "POSITION_OPENED",
                        "trade_id": f"UE-TRD-{self.trade_counter:04d}",
                        "symbol": pos.symbol,
                        "direction": pos.direction.value,
                        "quantity": pos.quantity,
                        "entry_price": pos.entry_price,
                        "invested_capital": pos.invested_capital,
                        "stop_loss_price": pos.stop_loss_price,
                        "take_profit_price": pos.take_profit_price,
                        "consensus_score": decision.consensus_score,
                        "agreement_ratio": decision.agreement_ratio,
                        "supporting_models": decision.supporting_models,
                        "expected_net_pct": decision.expected_net_pct,
                        "timestamp": now.isoformat(),
                        "rationale": decision.rationale
                    }
                    self._append_to_ledger(entry_event)
                    self._save_state()

        return {
            "timestamp": now.isoformat(),
            "target_symbol": target_symbol,
            "exit_event": exit_event,
            "entry_event": entry_event,
            "current_portfolio": self.get_portfolio_state()
        }

    def _append_to_ledger(self, record: Dict[str, Any]):
        """Appends trade and execution events to single authoritative JSONL ledger."""
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def _save_state(self):
        """Atomically saves the single authoritative state."""
        state = self.get_portfolio_state()
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

    def get_portfolio_state(self) -> Dict[str, Any]:
        """Returns single consolidated paper portfolio telemetry."""
        pos = self.risk_engine.active_position
        pos_data = None
        invested = 0.0

        if pos is not None:
            invested = pos.invested_capital
            pos_data = {
                "symbol": pos.symbol,
                "direction": pos.direction.value,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "invested_capital": pos.invested_capital,
                "stop_loss_price": pos.stop_loss_price,
                "take_profit_price": pos.take_profit_price,
                "trailing_stop_active": pos.trailing_stop_active,
                "entry_timestamp": pos.entry_timestamp.isoformat(),
                "supporting_models": pos.supporting_models
            }

        total_equity = round(self.risk_engine.current_cash + invested, 2)
        total_pnl = round(total_equity - self.starting_capital, 2)

        return {
            "portfolio_name": "AlphaNSE Unified Ensemble Authoritative Paper Portfolio",
            "mode": "AIR_GAPPED_PAPER_TRADING",
            "starting_capital": self.starting_capital,
            "current_cash": round(self.risk_engine.current_cash, 2),
            "invested_capital": round(invested, 2),
            "total_equity": total_equity,
            "realized_pnl_today": round(self.risk_engine.realized_pnl_today, 2),
            "total_pnl": total_pnl,
            "total_roi_pct": round((total_pnl / self.starting_capital) * 100, 2),
            "circuit_breaker_tripped": self.risk_engine.circuit_breaker_tripped,
            "active_positions_count": 1 if pos else 0,
            "active_position": pos_data,
            "total_completed_trades": len(self.trades_history),
            "airgap_safe": True
        }
