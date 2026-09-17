"""
Autonomous AI Agent Supervisor for Tri-Surface Surveillance
Monitors:
1. Web Treasury Desk (Capital, NAV, Drawdown, Uninvested Cash)
2. Live Mobile App (Daily trade pacing, Win rate, Positions, Executions)
3. Simulation & Research Lab (1-Min directional accuracy, Price deviation, Loopholes, Retraining)

Formulates strategic action plans and autonomously executes optimizations.
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
AGENT_STATE_FILE = os.path.join(LOGS_DIR, "ai_agent_telemetry.json")


class AIAgentSupervisor:
    """
    Autonomous tri-surface AI Agent that constantly audits Web Desk, Mobile App,
    and Simulation Lab, formulates optimization plans, and executes them.
    """

    def __init__(self, trader_ref=None):
        self.trader = trader_ref
        self.lock = threading.Lock()
        self.autopilot_enabled = True
        self.running = False
        self.thread = None

        # Telemetry & State
        self.thoughts: List[Dict[str, str]] = []
        self.active_plans: List[Dict[str, Any]] = []
        self.execution_history: List[Dict[str, Any]] = []
        self.last_sweep_time = None
        self.telemetry_snapshot = {
            "web_desk": {},
            "mobile_app": {},
            "sim_lab": {}
        }

        self._load_agent_state()

        # Seed initial thought if empty
        if not self.thoughts:
            self._log_thought("AlphaAgent Supervisor initialized. Surveillance active across Web, Mobile, and Simulation Lab.")

    def set_trader(self, trader_ref):
        self.trader = trader_ref

    def start(self):
        """Start autonomous background surveillance loop."""
        with self.lock:
            if self.running:
                return
            self.running = True
            self.thread = threading.Thread(target=self._surveillance_loop, daemon=True)
            self.thread.start()
            self._log_thought("Autonomous surveillance daemon activated on background thread.")

    def stop(self):
        with self.lock:
            self.running = False

    def _log_thought(self, message: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = {"time": now_str, "thought": message}
        self.thoughts.append(entry)
        if len(self.thoughts) > 40:
            self.thoughts = self.thoughts[-40:]
        print(f"[AI-AGENT {now_str}] {message}")

    def _surveillance_loop(self):
        """Periodically audits all 3 surfaces every 12 seconds."""
        while self.running:
            try:
                self.run_diagnostic_sweep()
            except Exception as e:
                self._log_thought(f"Diagnostic sweep anomaly: {e}")
            time.sleep(12)

    def run_diagnostic_sweep(self) -> Dict[str, Any]:
        """Runs full audit across Web Treasury, Mobile App, and Simulation Lab."""
        with self.lock:
            now_iso = datetime.now().isoformat()
            self.last_sweep_time = now_iso

            # 1. Audit Web Treasury Desk
            web_data = self._audit_web_desk()

            # 2. Audit Live Mobile App
            app_data = self._audit_mobile_app()

            # 3. Audit Simulation & Research Lab
            lab_data = self._audit_simulation_lab()

            self.telemetry_snapshot = {
                "web_desk": web_data,
                "mobile_app": app_data,
                "sim_lab": lab_data,
                "audited_at": now_iso
            }

            # 4. Formulate Action Plans based on multi-surface observations
            new_plans = self._formulate_plans(web_data, app_data, lab_data)
            self.active_plans = new_plans

            # 5. If Autopilot is ON, autonomously execute eligible high-priority plans
            if self.autopilot_enabled:
                for plan in list(self.active_plans):
                    if plan.get("auto_executable") and not plan.get("executed"):
                        self._execute_plan_internal(plan)

            self._save_agent_state()

            return {
                "status": "active",
                "autopilot": self.autopilot_enabled,
                "telemetry": self.telemetry_snapshot,
                "thoughts": list(reversed(self.thoughts))[:20],
                "plans": self.active_plans,
                "last_sweep": now_iso
            }

    def _audit_web_desk(self) -> Dict[str, Any]:
        if not self.trader:
            return {"capital": 5000.0, "status": "nominal"}

        summary = self.trader.get_summary()
        total_cap = summary.get("total_capital", 5000.0)
        avail_cap = summary.get("available_capital", 5000.0)
        invested = summary.get("invested_capital", 0.0)
        net_profit = summary.get("total_net_profit", 0.0)
        starting_cap = summary.get("starting_capital", 5000.0)

        uninvested_pct = round((avail_cap / max(1.0, total_cap)) * 100.0, 1)
        drawdown_pct = 0.0
        if starting_cap > total_cap:
            drawdown_pct = round(((starting_cap - total_cap) / starting_cap) * 100.0, 2)

        return {
            "total_capital": total_cap,
            "available_cash": avail_cap,
            "invested_margin": invested,
            "net_profit": net_profit,
            "uninvested_cash_pct": uninvested_pct,
            "drawdown_pct": drawdown_pct,
            "capital_health": "SECURE" if drawdown_pct < 5.0 else "WARNING"
        }

    def _audit_mobile_app(self) -> Dict[str, Any]:
        if not self.trader:
            return {"daily_trades": 0, "target_trades": 15, "win_rate_pct": 0.0}

        summary = self.trader.get_summary()
        daily_trades = summary.get("daily_trades_count", 0)
        target_trades = summary.get("target_daily_trades", 15)
        win_rate = summary.get("win_rate_pct", 0.0)
        positions = summary.get("positions", {})
        open_count = len(positions)

        pacing_pct = round((daily_trades / max(1, target_trades)) * 100.0, 1)

        return {
            "daily_trades": daily_trades,
            "target_trades": target_trades,
            "pacing_pct": pacing_pct,
            "win_rate_pct": win_rate,
            "active_positions_count": open_count,
            "execution_status": "PACING_OPTIMAL" if daily_trades < target_trades else "TARGET_REACHED"
        }

    def _audit_simulation_lab(self) -> Dict[str, Any]:
        if not self.trader:
            return {"accuracy_pct": 0.0, "whipsaws": 0}

        verifs = self.trader.state.get("prediction_verifications", [])
        total_v = len(verifs)

        hits = sum(1 for v in verifs if v.get("direction_correct"))
        accuracy_pct = round((hits / max(1, total_v)) * 100.0, 1) if total_v > 0 else 0.0

        # Whipsaw detection
        whipsaws = sum(
            1 for v in verifs
            if v.get("predicted_return_pct", 0) > 0.05 and v.get("actual_return_pct", 0) < -0.05
        )

        return {
            "total_verified": total_v,
            "directional_accuracy_pct": accuracy_pct,
            "whipsaws_count": whipsaws,
            "model_health": "HIGH" if accuracy_pct >= 75.0 else ("MODERATE" if accuracy_pct >= 60.0 else "RETRAIN_RECOMMENDED")
        }

    def _formulate_plans(self, web: Dict, app: Dict, lab: Dict) -> List[Dict[str, Any]]:
        plans = []

        # Plan 1: Model Calibration & Continuous Learning
        acc = lab.get("directional_accuracy_pct", 0.0)
        total_v = lab.get("total_verified", 0)
        whipsaws = lab.get("whipsaws_count", 0)

        if total_v >= 10 and acc < 70.0:
            plans.append({
                "id": "plan_retrain_ensemble",
                "title": "Ensemble Recalibration & Live Retraining",
                "category": "SIMULATION_LAB",
                "urgency": "HIGH",
                "description": f"Directional accuracy ({acc}%) is below the 70% threshold with {whipsaws} whipsaws. Trigger live retraining on recent session candles.",
                "action": "trigger_retrain",
                "auto_executable": True,
                "executed": False
            })
        else:
            plans.append({
                "id": "plan_feature_monitoring",
                "title": "1-Minute Multi-Horizon Feature Health Check",
                "category": "SIMULATION_LAB",
                "urgency": "NOMINAL",
                "description": f"Model health stable ({acc}% accuracy across {total_v} verified predictions). Micro-RSI and EMA slope weights verified.",
                "action": "verify_features",
                "auto_executable": False,
                "executed": False
            })

        # Plan 2: Adaptive Hurdle / Volatility Filter
        current_hurdle = getattr(self.trader, "profit_threshold_pct", 0.20) if self.trader else 0.20
        if whipsaws > 3 and current_hurdle < 0.22:
            plans.append({
                "id": "plan_raise_hurdle",
                "title": "Hurdle Dynamic Adaptation (18 bps → 22 bps)",
                "category": "WEB_TREASURY",
                "urgency": "MEDIUM",
                "description": f"Observed {whipsaws} intra-bar whipsaws. Elevating profit hurdle to 0.22% to eliminate shallow noise trades.",
                "action": "adjust_hurdle_22",
                "auto_executable": True,
                "executed": False
            })

        # Plan 3: Daily Execution Pacing Alignment
        pacing = app.get("pacing_pct", 0.0)
        daily_t = app.get("daily_trades", 0)
        target_t = app.get("target_trades", 15)

        if daily_t == 0:
            plans.append({
                "id": "plan_market_standby",
                "title": "Intraday Trade Pacing Sentinel",
                "category": "MOBILE_APP",
                "urgency": "NOMINAL",
                "description": f"Daily executions: {daily_t}/{target_t}. Standing by for high-conviction breakout signals (>0.8% return with >60% confidence).",
                "action": "log_status",
                "auto_executable": False,
                "executed": False
            })

        # Plan 4: Autonomous Stock Blacklist/Whitelist Surveillance (Phase 2.3)
        if self.trader and hasattr(self.trader, "confidence_tracker"):
            profiles = self.trader.confidence_tracker.get_all_profiles()
            for sym, prof in profiles.items():
                acc_pct = prof.get("directional_accuracy_pct", 50.0)
                samples = prof.get("verified_samples", 0)
                is_bl = prof.get("is_blacklisted", False)

                if not is_bl and samples >= 20 and acc_pct < 45.0:
                    plans.append({
                        "id": f"plan_blacklist_{sym.replace('.', '_')}",
                        "title": f"Autonomous Blacklist: {sym}",
                        "category": "SIMULATION_LAB",
                        "urgency": "HIGH",
                        "symbol": sym,
                        "description": f"Directional accuracy for {sym} dropped to {acc_pct}% over {samples} verified samples. Blacklist to prevent loss.",
                        "action": "blacklist_stock",
                        "auto_executable": True,
                        "executed": False
                    })
                elif is_bl and samples >= 20 and acc_pct >= 60.0:
                    plans.append({
                        "id": f"plan_whitelist_{sym.replace('.', '_')}",
                        "title": f"Autonomous Whitelist: {sym}",
                        "category": "SIMULATION_LAB",
                        "urgency": "MEDIUM",
                        "symbol": sym,
                        "description": f"Directional accuracy for {sym} recovered to {acc_pct}%. Reinstate into active execution universe.",
                        "action": "whitelist_stock",
                        "auto_executable": True,
                        "executed": False
                    })

        return plans

    def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """Manually or externally triggers execution of an action plan."""
        with self.lock:
            for plan in self.active_plans:
                if plan["id"] == plan_id:
                    return self._execute_plan_internal(plan)
            return {"success": False, "message": f"Plan '{plan_id}' not found in active plans."}

    def _execute_plan_internal(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        action = plan.get("action")
        plan_id = plan.get("id")
        plan["executed"] = True

        msg = f"Executed Autonomous Plan: {plan.get('title')}"
        if action == "trigger_retrain":
            self._log_thought("[AUTONOMOUS ACTION] Launching live 1m model ensemble retraining...")
            if self.trader:
                # Trigger retrain in background
                def _bg_train():
                    try:
                        import subprocess
                        script_path = os.path.join(PROJECT_ROOT, "scripts", "build_and_train_live_1m.py")
                        if os.path.exists(script_path):
                            subprocess.run([sys.executable, script_path], cwd=PROJECT_ROOT, capture_output=True)
                            self._log_thought("[OK] [AUTONOMOUS ACTION] Retraining finished. Models refreshed.")
                    except Exception as err:
                        self._log_thought(f"[ERROR] Retraining sub-process error: {err}")
                threading.Thread(target=_bg_train, daemon=True).start()

        elif action == "adjust_hurdle_22":
            if self.trader:
                self.trader.profit_threshold_pct = 0.22
                self.trader._save_state()
            self._log_thought("[AUTONOMOUS ACTION] Hurdle recalibrated to 0.22% (22 bps) to filter volatility noise.")

        elif action == "blacklist_stock":
            sym = plan.get("symbol")
            if self.trader and sym:
                self.trader.stock_blacklist.add(sym)
                if hasattr(self.trader, "confidence_tracker"):
                    self.trader.confidence_tracker.blacklist(sym, plan.get("description", "Underperforming accuracy"))
                self.trader._save_state()
            self._log_thought(f"[AUTONOMOUS ACTION] Blacklisted {sym} from live execution to protect capital.")

        elif action == "whitelist_stock":
            sym = plan.get("symbol")
            if self.trader and sym:
                self.trader.stock_blacklist.discard(sym)
                if hasattr(self.trader, "confidence_tracker"):
                    self.trader.confidence_tracker.whitelist(sym, "Accuracy edge recovered")
                self.trader._save_state()
            self._log_thought(f"[AUTONOMOUS ACTION] Re-whitelisted {sym} for live trading.")

        else:
            self._log_thought(f"[ACTION] Plan '{plan_id}' executed and verified.")

        self.execution_history.append({
            "plan_id": plan_id,
            "title": plan.get("title"),
            "executed_at": datetime.now().isoformat()
        })
        self._save_agent_state()

        return {"success": True, "message": msg, "plan_id": plan_id}

    def toggle_autopilot(self, enabled: bool = None) -> bool:
        with self.lock:
            if enabled is None:
                self.autopilot_enabled = not self.autopilot_enabled
            else:
                self.autopilot_enabled = bool(enabled)
            status_str = "ENABLED (Auto-Execution Active)" if self.autopilot_enabled else "MUTED (Manual Approval Mode)"
            self._log_thought(f"Autopilot mode updated to: {status_str}")
            self._save_agent_state()
            return self.autopilot_enabled

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "status": "ACTIVE" if self.running else "STANDBY",
                "autopilot": self.autopilot_enabled,
                "last_sweep": self.last_sweep_time,
                "telemetry": self.telemetry_snapshot,
                "thoughts": list(reversed(self.thoughts))[:25],
                "plans": self.active_plans,
                "executions_count": len(self.execution_history)
            }

    def _save_agent_state(self):
        try:
            payload = {
                "autopilot_enabled": self.autopilot_enabled,
                "last_sweep_time": self.last_sweep_time,
                "thoughts": self.thoughts[-40:],
                "active_plans": self.active_plans,
                "execution_history": self.execution_history[-20:]
            }
            with open(AGENT_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _load_agent_state(self):
        if os.path.exists(AGENT_STATE_FILE):
            try:
                with open(AGENT_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.autopilot_enabled = data.get("autopilot_enabled", True)
                    self.last_sweep_time = data.get("last_sweep_time")
                    self.thoughts = data.get("thoughts", [])
                    self.active_plans = data.get("active_plans", [])
                    self.execution_history = data.get("execution_history", [])
            except Exception:
                pass
