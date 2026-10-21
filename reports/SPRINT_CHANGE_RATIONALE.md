# AlphaNSE V3 — Accuracy & Readiness Sprint: Change Rationale & File Impact Analysis

**Date:** Wednesday, October 14, 2026  
**Auditor:** AlphaNSE Quantitative Trading Architecture Team  
**Scope:** Minimal Reliability and Model Correctness Fixes (Phases 1 & 2)

---

## 1. Summary of Identified Defects & Root Causes

### Defect 1: Daemon Suspended Prior to Market Open (Modern Standby)
- **Root Cause:** Host Windows machine entered Modern Standby (`Kernel-Power Event ID 506: Lid`) at 08:27:20 IST. The process lacked Windows thread execution state flags (`SetThreadExecutionState`), allowing the OS to suspend the python execution thread when the lid was closed.
- **Affected File:** `v3/execution/live_trader.py`
- **Proposed Fix:** Add `set_windows_keep_alive(enable: bool)` using `ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)` (`ES_CONTINUOUS | ES_SYSTEM_REQUIRED`) during daemon runtime, restoring `ES_CONTINUOUS` upon exit.

### Defect 2: Global Standard Output Redirection on Module Import
- **Root Cause:** In `v3/execution/live_trader.py:L105-106`, `sys.stdout = TeeLogger(LOG_FILE)` was invoked at module level upon file import. Any test suite (`run_tests.py`), verification script, or analysis tool importing `live_trader` redirected its stdout to `logs/live_trader.log`, corrupting the live trading audit log.
- **Affected File:** `v3/execution/live_trader.py`
- **Proposed Fix:** Remove module-level stdout reassignment; attach `TeeLogger` only inside `AlphaNSELiveTrader.run()` or under `if __name__ == '__main__':`.

### Defect 3: Standby Countdown Log Buffer Corruption
- **Root Cause:** In `v3/execution/live_trader.py:L1276`, the standby loop printed using `print(f"\r...", end="", flush=True)` every 10 seconds. In a log file, carriage returns without newlines create a single multi-megabyte unreadable string.
- **Affected File:** `v3/execution/live_trader.py`
- **Proposed Fix:** Emit heartbeat updates with standard `\n` once every 60 seconds (or when minute changes), keeping logs structured and readable.

### Defect 4: Lack of Cycle-Level Exception Shielding in Trading Loop
- **Root Cause:** `v3/execution/live_trader.py` had no `try...except` block wrapping individual iterations of the main `while True:` loop. A transient network timeout or unexpected response from quote fetching would terminate the entire daemon.
- **Affected File:** `v3/execution/live_trader.py`
- **Proposed Fix:** Wrap each cycle in `try...except Exception as e:` with fail-closed logging, state preservation, and a short backoff sleep.

### Defect 5: Semantic Conflation of Breakout Probability vs. Directional Confidence
- **Root Cause:** In `QA/models/one_min_predictor.py:L324`, `breakout_classifier_1m` was trained strictly on $y = (\text{return} \ge +0.0010)$ (+10 bps upward jump), an extreme positive tail event with an ~8% prior base rate. In `predict_next_1m()` and `predict_batch_1m()`, `calibrated_confidence` was set to `raw_breakout_prob`.
  - For SHORT trades, line 538 and 678 required `is_short = (pred_return <= -effective_threshold) and (calibrated_confidence >= 0.45)`. This mathematically demanded that a falling stock simultaneously possess a $\ge 45\%$ probability of a $>+10\text{ bps}$ upward breakout, an impossible condition that blocked 100% of short signals.
  - For LONG trades, requiring $P(\text{surge} \ge +10\text{ bps}) \ge 45\%$ demanded an event roughly $5\times$ above the base rate of 8%.
  - Meanwhile, `v3/research/walkforward_validation.py:L206` correctly defined directional confidence as $\text{clip}(0.50 + \text{tree\_alpha} \times 50.0, 0.10, 0.90)$, centered at 50% (neutral) and naturally achieving 53%–65% on valid directional moves.
- **Affected File:** `QA/models/one_min_predictor.py`
- **Proposed Fix:** Calculate directional confidence centered at 50%:
  - For BUY: $\text{clip}(0.50 + \text{pred\_return} \times 50.0, 0.10, 0.95)$
  - For SELL: $\text{clip}(0.50 + |\text{pred\_return}| \times 50.0, 0.10, 0.95)$
  - Multiply by `confidence_multiplier` (default 1.0) and clip to $[0.10, 0.99]$.
  - Keep the 45% threshold intact (`calibrated_confidence >= 0.45`); do NOT lower the threshold.
  - Preserve `"raw_breakout_prob": round(raw_breakout_prob * 100, 1)` in output dict for full backward compatibility.
  - Ensure `predict_batch_1m` and `predict_next_1m` implement identical logic.

### Defect 6: Historical Replay Ledgers Mixing with Live Reports
- **Root Cause:** Replay files (`paper_replay_ledger*.json`, `paper_intraday_summary*.json`, `real_vs_predicted_chart.html`) from October 9 historical simulations were residing in `reports/live/`.
- **Affected Files:** `view_paper_trades.py`, `reports/live/`
- **Proposed Fix:** Update `view_paper_trades.py` to point primarily to `reports/replay/` for replay sessions.

---

## 2. Safety Guarantees Maintained
1. `LIVE_TRADING = False` and `ALLOW_REAL_ORDERS = False` remain strictly enforced.
2. ₹1,500 bankroll limit, 0.30% (₹4.50) max loss per trade, and ₹15.00 daily loss killswitch remain active.
3. Cash equities only; whole shares only; maximum 1 open position.
4. Fail-closed safeguards remain active: candle buffers $< 15$ bars return `prediction_valid = False` and `confidence = 0.0`.
