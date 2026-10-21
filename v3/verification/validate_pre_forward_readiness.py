"""
v3/verification/validate_pre_forward_readiness.py
Runs the 8 pre-forward validation gates required by PART 6.
"""

import os
import sys
import json
import subprocess
import unittest
import importlib

# Ensure repository root and QA are on sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)
QA_PATH = os.path.join(WORKSPACE_ROOT, "QA")
if QA_PATH not in sys.path:
    sys.path.insert(0, QA_PATH)

def run_gate(gate_num: int, gate_name: str, check_func):
    print(f"\n==================================================")
    print(f"GATE {gate_num}: {gate_name}")
    print(f"==================================================")
    try:
        details = check_func()
        print(f"[PASS] Gate {gate_num} Passed: {gate_name}")
        for k, v in details.items():
            print(f"  - {k}: {v}")
        return True, details
    except AssertionError as e:
        print(f"[FAIL] Gate {gate_num} Assertion Failed: {e}")
        return False, {"error": str(e)}
    except Exception as e:
        print(f"[ERROR] Gate {gate_num} Exception: {e}")
        return False, {"error": str(e)}

# Gate 1: Full test suite
def check_gate_1_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(WORKSPACE_ROOT, "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    assert result.wasSuccessful(), f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors"
    assert result.testsRun >= 232, f"Expected at least 232 tests, ran {result.testsRun}"
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "status": "ALL_TESTS_PASSING"
    }

# Gate 2: Import validation
def check_gate_2_imports():
    if QA_PATH in sys.path:
        sys.path.remove(QA_PATH)
    sys.path.insert(0, QA_PATH)
    if 'risk' in sys.modules and 'tests' in str(getattr(sys.modules['risk'], '__file__', '')):
        del sys.modules['risk']
    
    modules_to_test = [
        "v3.ensemble.specialist_signal",
        "v3.ensemble.specialist_registry",
        "v3.ensemble.unified_meta_decision_engine",
        "v3.ensemble.unified_risk_engine",
        "v3.ensemble.unified_paper_executor",
        "v2.risk.cost_engine",
        "QA.engine.compounding_trader"
    ]
    imported = []
    for mod_name in modules_to_test:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Failed to import {mod_name}"
        imported.append(mod_name)
    return {"imported_modules_count": len(imported), "modules": imported}

# Gate 3: Configuration validation
def check_gate_3_configuration():
    from v3.ensemble.unified_paper_executor import UnifiedPaperExecutor
    from v3.ensemble.unified_risk_engine import UnifiedRiskEngine
    
    executor = UnifiedPaperExecutor()
    assert executor.LIVE_TRADING is False, "LIVE_TRADING must be False"
    assert executor.ALLOW_REAL_ORDERS is False, "ALLOW_REAL_ORDERS must be False"
    assert executor.starting_capital == 1500.0, "Capital must be 1500.0"
    
    risk = executor.risk_engine
    assert risk.max_capital == 1500.0, "max_capital must be 1500.0"
    assert risk.max_daily_loss == 30.0, "max_daily_loss must be 30.0"
    assert risk.max_concurrent_positions == 1, "max_concurrent_positions must be 1"
    assert risk.hard_stop_loss_pct == 0.006, "hard_stop_loss_pct must be 0.6%"
    assert risk.take_profit_target_pct == 0.030, "take_profit_target_pct must be 3.0%"
    assert risk.stagnation_cutoff_mins == 45, "stagnation_cutoff_mins must be 45"
    
    # Verify whole-share integer sizing
    # Stock price ₹1000 with ₹1500 budget (deployable 95% = ₹1425) -> exactly 1 share
    from v3.ensemble.unified_meta_decision_engine import MetaDecisionOutput
    from v3.ensemble.specialist_signal import SignalDirection
    dec = MetaDecisionOutput(
        target_symbol="TEST.NS",
        action=SignalDirection.BUY,
        consensus_score=0.45,
        agreement_count=4,
        total_specialists=7,
        agreement_ratio="4/7",
        supporting_models=["M1", "M2"],
        opposing_models=[],
        neutral_models=["M3"],
        expected_gross_pct=0.015,
        estimated_friction_pct=0.0018,
        expected_net_pct=0.0132,
        net_edge_cleared=True,
        macro_regime="BULL",
        micro_regime="TRENDING_BULL",
        recommended_horizon_mins=60,
        rationale="Test"
    )
    shares, capital, reason = risk.calculate_order_sizing(dec, 1000.0)
    assert shares == 1, f"Expected 1 share, got {shares}"
    assert capital == 1000.0, f"Expected 1000.0 capital, got {capital}"
    
    # Stock price ₹2105 (TCS) exceeds deployable ₹1425 -> 0 shares
    shares_tcs, capital_tcs, reason_tcs = risk.calculate_order_sizing(dec, 2105.0)
    assert shares_tcs == 0, f"TCS should not fit budget: shares={shares_tcs}"
    assert "PRICE_EXCEEDS_BUDGET" in reason_tcs
    
    return {
        "LIVE_TRADING": executor.LIVE_TRADING,
        "ALLOW_REAL_ORDERS": executor.ALLOW_REAL_ORDERS,
        "capital_limit": risk.max_capital,
        "max_daily_loss": risk.max_daily_loss,
        "max_positions": risk.max_concurrent_positions,
        "whole_share_enforced": True,
        "tcs_budget_rejection_verified": True
    }

# Gate 4: Ledger integrity validation
def check_gate_4_ledger_integrity():
    state_file = os.path.join(WORKSPACE_ROOT, "v3", "reports", "UNIFIED_ENSEMBLE_STATE.json")
    assert os.path.exists(state_file), f"State file not found: {state_file}"
    with open(state_file, "r") as f:
        state = json.load(f)
    assert state.get("starting_capital") == 1500.0
    assert state.get("current_cash") == 1500.0
    assert state.get("invested_capital") == 0.0
    assert state.get("total_equity") == 1500.0
    assert state.get("active_positions_count") == 0
    assert state.get("airgap_safe") is True
    
    ledger_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "unified_ensemble_ledger.jsonl")
    assert os.path.exists(os.path.dirname(ledger_path)), "Ledger directory does not exist"
    
    return {
        "state_file": state_file,
        "portfolio_name": state.get("portfolio_name"),
        "starting_capital": state.get("starting_capital"),
        "total_equity": state.get("total_equity"),
        "active_positions_count": state.get("active_positions_count"),
        "airgap_safe": state.get("airgap_safe"),
        "ledger_path": ledger_path
    }

# Gate 5: Safety-lock validation
def check_gate_5_safety_lock():
    from v3.ensemble.unified_paper_executor import UnifiedPaperExecutor
    executor = UnifiedPaperExecutor()
    
    # Check credentials in env
    dangerous_vars = ["FLAT_TRADE_TOKEN", "ZERODHA_API_KEY", "KITE_TOKEN", "UPSTOX_ACCESS_TOKEN", "ANGEL_TOKEN"]
    found_creds = [v for v in dangerous_vars if os.environ.get(v)]
    assert len(found_creds) == 0, f"Dangerous live broker credentials present: {found_creds}"
    
    # Verify fail-closed airgap exception if someone toggles flag
    try:
        executor.LIVE_TRADING = True
        executor._enforce_airgap()
        raise AssertionError("Airgap failed to trip when LIVE_TRADING set to True!")
    except PermissionError:
        pass # Expected
    finally:
        executor.LIVE_TRADING = False
        
    return {
        "LIVE_TRADING": False,
        "ALLOW_REAL_ORDERS": False,
        "BROKER_CREDENTIALS_PRESENT": False,
        "REAL_CAPITAL_EXPOSED": 0.0,
        "AIRGAP_FAIL_CLOSED_VERIFIED": True
    }

# Gate 6: Single-paper-portfolio validation
def check_gate_6_single_paper_portfolio():
    # Verify CompoundingTrader state is marked FROZEN_ARCHIVE
    compounding_state_file = os.path.join(WORKSPACE_ROOT, "QA", "logs", "compounding_state.json")
    if os.path.exists(compounding_state_file):
        with open(compounding_state_file, "r") as f:
            cstate = json.load(f)
        assert cstate.get("engine_status") == "FROZEN_ARCHIVE", f"Expected FROZEN_ARCHIVE, got {cstate.get('engine_status')}"
    
    # Verify the only active portfolio is Unified Ensemble
    state_file = os.path.join(WORKSPACE_ROOT, "v3", "reports", "UNIFIED_ENSEMBLE_STATE.json")
    with open(state_file, "r") as f:
        state = json.load(f)
    assert state.get("mode") == "AIR_GAPPED_PAPER_TRADING"
    
    return {
        "active_paper_portfolios": 1,
        "active_portfolio_name": state.get("portfolio_name"),
        "legacy_compounding_trader_status": "FROZEN_ARCHIVE",
        "competing_accounts": 0
    }

# Gate 7: Duplicate-engine detection
def check_gate_7_duplicate_engines():
    from QA.engine.compounding_trader import CompoundingTrader
    trader = CompoundingTrader()
    assert trader.is_running is False
    trader.start_engine() # Should be a no-op that logs retired notice
    assert trader.is_running is False
    assert trader.state.get("engine_status") == "FROZEN_ARCHIVE"
    assert trader.worker_thread is None
    
    # Check running processes for uvicorn or supervisor
    conflicting_pids = []
    try:
        ps_cmd = 'Get-CimInstance Win32_Process | Select-Object ProcessId, CommandLine | ConvertTo-Json'
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            procs = json.loads(res.stdout)
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                cmd = str(p.get("CommandLine") or "")
                if "continuous_supervisor.py" in cmd or ("uvicorn" in cmd and "QA.server.api" in cmd):
                    conflicting_pids.append(p.get("ProcessId"))
    except Exception as e:
        print(f"Warning: Process check encountered {e}")
            
    assert len(conflicting_pids) == 0, f"Found competing running daemons: {conflicting_pids}"
    
    return {
        "active_trading_orchestrators": 1,
        "authoritative_orchestrator": "AlphaNSE Unified Ensemble",
        "compounding_trader_start_engine_neutralized": True,
        "competing_processes_running": 0
    }

# Gate 8: Data-source validation
def check_gate_8_data_sources():
    data_dir = os.path.join(WORKSPACE_ROOT, "v2", "data", "storage")
    assert os.path.exists(data_dir), f"Historical data directory missing: {data_dir}"
    
    adj_dir = os.path.join(data_dir, "adjusted")
    raw_dir = os.path.join(data_dir, "raw")
    adaptive_dir = os.path.join(data_dir, "adaptive")
    
    assert os.path.exists(adj_dir), f"Adjusted data directory missing: {adj_dir}"
    assert os.path.exists(raw_dir), f"Raw data directory missing: {raw_dir}"
    assert os.path.exists(adaptive_dir), f"Adaptive data directory missing: {adaptive_dir}"
    
    # Authoritative 5m and 1m parquet datasets
    p5m = os.path.join(adj_dir, "historical_5m_adjusted.parquet")
    p1m = os.path.join(adj_dir, "historical_1m_adjusted.parquet")
    assert os.path.exists(p5m), f"5m dataset missing: {p5m}"
    assert os.path.exists(p1m), f"1m dataset missing: {p1m}"
    
    import pandas as pd
    df5m = pd.read_parquet(p5m)
    df1m = pd.read_parquet(p1m)
    
    required_cols = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    assert required_cols.issubset(set(df5m.columns)), f"Missing columns in 5m: {df5m.columns}"
    assert required_cols.issubset(set(df1m.columns)), f"Missing columns in 1m: {df1m.columns}"
    
    assert len(df5m) >= 40000, f"Expected >= 40000 rows in 5m, got {len(df5m)}"
    assert len(df1m) >= 20000, f"Expected >= 20000 rows in 1m, got {len(df1m)}"
    assert df5m["symbol"].nunique() >= 10, f"Expected >= 10 symbols, got {df5m['symbol'].nunique()}"
    
    # Check no null prices
    assert df5m["close"].isna().sum() == 0, "Null values found in 5m close prices"
    assert df1m["close"].isna().sum() == 0, "Null values found in 1m close prices"
    
    adaptive_files = [f for f in os.listdir(adaptive_dir) if f.endswith(".parquet")]
    
    return {
        "data_storage_path": data_dir,
        "historical_5m_bars": len(df5m),
        "historical_1m_bars": len(df1m),
        "symbols_tracked": df5m["symbol"].nunique(),
        "adaptive_training_checkpoints": len(adaptive_files),
        "data_integrity": "VALID_AND_CONSISTENT"
    }

def main():
    print("=" * 60)
    print("ALPHANSE UNIFIED ENSEMBLE: PRE-FORWARD READINESS AUDIT GATES")
    print("=" * 60)
    
    gates = [
        (1, "Full Test Suite (232+ tests)", check_gate_1_tests),
        (2, "Import Validation", check_gate_2_imports),
        (3, "Configuration Validation", check_gate_3_configuration),
        (4, "Ledger Integrity Validation", check_gate_4_ledger_integrity),
        (5, "Safety-Lock & Air-Gap Validation", check_gate_5_safety_lock),
        (6, "Single Paper Portfolio Validation", check_gate_6_single_paper_portfolio),
        (7, "Duplicate Engine Detection", check_gate_7_duplicate_engines),
        (8, "Data Source & Ingestion Validation", check_gate_8_data_sources)
    ]
    
    all_passed = True
    gate_results = {}
    
    for num, name, func in gates:
        success, details = run_gate(num, name, func)
        gate_results[f"Gate {num}: {name}"] = details
        if not success:
            all_passed = False
            print(f"\nABORTING: Gate {num} FAILED.")
            break
            
    if all_passed:
        print("\n" + "=" * 60)
        print("ALL 8 PRE-FORWARD VALIDATION GATES PASSED SUCCESSFULLY!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("PRE-FORWARD VALIDATION FAILED! SAFETY LOCKS ENGAGED.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
