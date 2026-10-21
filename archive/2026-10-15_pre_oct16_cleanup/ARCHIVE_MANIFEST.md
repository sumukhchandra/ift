# Safe Project Archive Manifest — 2026-10-15

This archive preserves obsolete, duplicate, and legacy non-production artifacts removed from active source directories prior to the October 16, 2026 trading session.
All files in this archive have zero dependencies in the active AlphaNSE V3 production pipeline (`run_live_trader.py`, `v3/`, `run_tests.py`).

| Original File Path | Archived Path | Reason for Archiving | Verified Safe |
| :--- | :--- | :--- | :--- |
| `QA/execution/broker_bridge.py` | `archive/2026-10-15_pre_oct16_cleanup/broker_bridge.py` | Legacy v1 mock broker bridge; superseded by `v3/execution/kotak_adapter.py`. | 🟢 Yes (0 references) |
| `QA/execution/risk_guard.py` | `archive/2026-10-15_pre_oct16_cleanup/risk_guard.py` | Legacy v1 risk guard; superseded by `v3/execution/edge_friction_gate.py` and `v2/risk/cost_engine.py`. | 🟢 Yes (0 references) |
| `QA/scripts/check_radar.py` | `archive/2026-10-15_pre_oct16_cleanup/check_radar.py` | Scratch multi-agent inspection tool from Phase 1; superseded by `run_live_trader.py --inspect-signals`. | 🟢 Yes (0 references) |
| `QA/scripts/multi_agent_inspector.py` | `archive/2026-10-15_pre_oct16_cleanup/multi_agent_inspector.py` | Legacy multi-agent CLI inspector from Phase 1. | 🟢 Yes (0 references) |
| `.env.angel.example` | `archive/2026-10-15_pre_oct16_cleanup/.env.angel.example` | Deprecated Angel One configuration template; superseded by Kotak Neo `.env`. | 🟢 Yes (0 references) |
| `reports/forward_evaluation_results_unconstrained_flawed_20261015.json` | `reports/archive/forward_evaluation_results_unconstrained_flawed_20261015.json` | Flawed unconstrained parallel evaluation report preserved as historical forensic evidence. | 🟢 Yes (Audit evidence) |

### Active Production Architecture Preservation:
- Single Canonical Production Runner: [run_live_trader.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/run_live_trader.py)
- Active Execution Engine: [v3/execution/live_trader.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/live_trader.py)
- Broker Adapter: [v3/execution/kotak_adapter.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/kotak_adapter.py)
- Opportunity Scanner: [v3/intelligence/opportunity_engine.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/intelligence/opportunity_engine.py)
- Cost Engine: [v2/risk/cost_engine.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v2/risk/cost_engine.py)
- Pre-Trade Gate: [v3/execution/edge_friction_gate.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/edge_friction_gate.py)
- Authoritative Paper Trading Ledger: [reports/live/paper_trading_ledger.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/paper_trading_ledger.json)
- Live Orders Stream: [reports/live/orders_stream.jsonl](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/orders_stream.jsonl)
