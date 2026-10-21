# FORENSIC INVENTORY — ALPHANSE V3 REPOSITORY AUDIT
**Audit Execution Timestamp:** 2026-10-17T16:39:17.459464 IST
**Repository Root:** `c:\Users\sumuk\.gemini\antigravity-ide\scratch\ift`
**Current Branch:** `main`
**Commit Hash:** `7d125f996c6fe8e50788f6a12830c741143fb1b8`
**Git Working Tree Status:** Ahead of origin by 1 commit (`7d125f9`), uncommitted working tree modifications and untracked directories present.

## 1. Summary of Project Assets by Category
| Asset Category | File Count | Total Size (Bytes) | Total Size (MB) | Description |
| :--- | :---: | :---: | :---: | :--- |
| `data_artifact` | 42 | 1,436,371 | 1.37 MB | Categorized system component |
| `documentation` | 18 | 228,243 | 0.22 MB | Categorized system component |
| `model_artifact` | 13 | 352,681 | 0.34 MB | Categorized system component |
| `other` | 246 | 34,833,913 | 33.22 MB | Categorized system component |
| `qa_pipeline` | 217 | 90,867,062 | 86.66 MB | Categorized system component |
| `reports_logs` | 112 | 31,140,934 | 29.70 MB | Categorized system component |
| `script_executable` | 207 | 1,543,760 | 1.47 MB | Categorized system component |
| `test_suite` | 73 | 406,024 | 0.39 MB | Categorized system component |
| `v3_runtime` | 368 | 6,687,492 | 6.38 MB | Categorized system component |
| **TOTAL** | **1,296** | **167,496,480** | **159.74 MB** | **Complete repository inventory** |

## 2. Cryptographic Integrity Ledger (SHA-256) of Critical System Artifacts
| File Path | Category | Size (Bytes) | Last Modified (IST) | SHA-256 Digest |
| :--- | :---: | :---: | :---: | :--- |
| `run_live_trader.py` | `script_executable` | 2,735 | 2026-10-15T08:04:35.861841 | `8f509f0f33082b7aa8b933d8af3b58bb5669a931112fc6c23e2744707d4a1d4e` |
| `launch_background.py` | `script_executable` | 4,148 | 2026-10-15T00:41:36.357011 | `abc97dcb7d9b47c1c999b20df900ac3a2114c8041ec84cfb8ae23a387da3e69c` |
| `check_status.py` | `script_executable` | 9,345 | 2026-10-16T00:17:20.181837 | `738a010130265ee768e16da3c9c150e6cb9f00ee276925605ed8b57297471b9d` |
| `run_tests.py` | `script_executable` | 1,589 | 2026-09-19T12:51:00.395918 | `2f8e1261dcf54b3a69d8b68ae804d67e5a8f56c999e2991af776f12158f1229b` |
| `view_paper_trades.py` | `script_executable` | 9,171 | 2026-10-14T18:06:27.903131 | `305cb8d0caf2346f87c4e85648b12bdf9d7092d16073fc232fdafa99e41b1894` |
| `start_live_trader.bat` | `script_executable` | 672 | 2026-10-12T18:35:50.190584 | `58be107be20bf33a8f267eb865abcbf390243c2425eb5c50a1cf64d82329a087` |
| `start_background_trader.vbs` | `script_executable` | 393 | 2026-10-15T00:41:48.034210 | `da4b5d7ed124e5c32b7b2da9603fe84b182d702f43ca1eab459679e338679f73` |
| `v3/execution/live_trader.py` | `v3_runtime` | 77,711 | 2026-10-16T21:46:43.309088 | `8e8e13c6a483fef1766acb4f5ebc8b3d1470ee65888bb57cb94acadf8c66d642` |
| `v3/execution/kotak_adapter.py` | `v3_runtime` | 22,571 | 2026-10-15T01:12:49.756751 | `4202d7068750f311816d45eee62748e2964649b5c8a44401c66c6b9160f45003` |
| `v3/execution/edge_friction_gate.py` | `v3_runtime` | 4,977 | 2026-10-02T04:31:51.507016 | `662a68cea9a2ea6432bc6a7133a1e164b45d0729b021def0f4f77d10ec4aca5e` |
| `v3/intelligence/opportunity_engine.py` | `v3_runtime` | 38,379 | 2026-10-17T15:42:48.995337 | `309bc536ed19c8bf3dfc2a403eb717ea8bbc203b6ba6ff2df4416c260cbfb528` |
| `v3/intelligence/provenance_tracker.py` | `v3_runtime` | 11,528 | 2026-10-15T23:56:33.804339 | `55562f1f0b07df3bf6be72d2cb9400fd256dc66ce9953ca3b43105d2dc8d2225` |
| `v3/models/multimodel/active_model_weights.json` | `v3_runtime` | 11,101 | 2026-10-13T03:38:47.067590 | `82c17f1a716afc330fd892a5ee17381c68d6eacd0a695da3e67fdbf50c605153` |
| `QA/models/one_min_predictor.py` | `qa_pipeline` | 36,527 | 2026-10-17T15:30:37.426660 | `bdb1caa59256c3e8928ec3caae6c1a8f4dd28bf0cad111be0eb2a3b2a2d2bc2e` |
| `QA/scripts/build_and_train_live_1m.py` | `qa_pipeline` | 6,470 | 2026-10-17T15:30:21.202256 | `16d16c439270376706baa4cfb5e73ba367035618d05b84db0219e0d6eacc5c4b` |
| `QA/models/train_ensemble.py` | `qa_pipeline` | 4,449 | 2026-09-18T02:00:52.857634 | `5f959a7d22bd6689174aa39996525ed86ecf781bd278d2ed2caf93ce1c421b55` |
| `QA/models/saved_models_1m/breakout_classifier_1m.joblib` | `qa_pipeline` | 3,131,678 | 2026-10-12T10:47:47.980983 | `a083347292301a57408a8ccbdb3c5e35680d80be717f1ed2b450c66780d9af0d` |
| `QA/models/saved_models_1m/quantile_regressor_1m.joblib` | `qa_pipeline` | 1,383,473 | 2026-10-12T10:47:48.011181 | `25e31ecbdfd587d899824f5b8d1959a7879eb8aa8fed13654c5181c220015e5c` |
| `QA/models/saved_models_1m/return_regressors_1m.joblib` | `qa_pipeline` | 5,427,478 | 2026-10-12T10:47:47.955711 | `91370aaad0ccb62c535d9fb441c85ee931985d5d4307fb449f07027cc62cf2ec` |
| `QA/stocks_config.py` | `qa_pipeline` | 3,006 | 2026-10-13T03:39:41.129683 | `83c1420501736aae2924f489230ce4acd3e696e840864fbf6abed5a54fe0e51b` |
| `v2/risk/cost_engine.py` | `script_executable` | 4,704 | 2026-10-13T03:58:47.331048 | `16eee963ceeaa478c5d814e6972bc52dc89dfac85a27dce3c93b1dc4cf8066bb` |
| `QA/data/genuine_forward_oos_oct13_oct14.csv` | `qa_pipeline` | 826,417 | 2026-10-15T01:16:03.818915 | `fc2beee5136c5d4c2b6127b87a0ae1e941b22e0c0d545a1cb6539fffe7137bbb` |
| `QA/data/combined_weekend_1m.csv` | `qa_pipeline` | 5,697,067 | 2026-10-12T05:42:09.370811 | `4cf7b5ed8fbd0784c33f00dddef4974885d1d37b11134b901af3ebff341d2386` |
| `QA/data/RELIANCE_1m_weekend.csv` | `qa_pipeline` | 500,278 | 2026-10-12T05:42:07.034944 | `4466d796c0dd10f121d041ec9330c965d4d3a6e8435cc838cd5b43c2191ad8da` |
| `QA/data/TCS_1m_weekend.csv` | `qa_pipeline` | 439,377 | 2026-10-12T05:42:08.420823 | `33492b60a07d6d893b19de62098a6956aaa4edb457e95063b7ab4c68f19be80d` |
| `QA/data/INFY_1m_weekend.csv` | `qa_pipeline` | 473,341 | 2026-10-12T05:42:05.816924 | `482c13f400cbcfc0e77a91f641408f1020b4deea298232ae695d84528acbdce6` |
| `QA/data/HDFCBANK_1m_weekend.csv` | `qa_pipeline` | 487,555 | 2026-10-12T05:42:07.818341 | `342145c1b3e860b32fd149d8b601c479545ec5ef38806f19359b16211c2603a0` |
| `QA/data/ICICIBANK_1m_weekend.csv` | `qa_pipeline` | 503,863 | 2026-10-12T05:42:08.168633 | `c867a98fb947e39e48523be68d2a731b80968b7ab57334f1abb0ab4c013b222a` |
| `QA/data/SBIN_1m_weekend.csv` | `qa_pipeline` | 462,014 | 2026-10-12T05:42:07.452188 | `3335f80408c06a0f57e6b589bea6ece782be87aa106c3b083e2e696b446adc21` |
| `QA/data/friday_session_features.csv` | `qa_pipeline` | 179,100 | 2026-09-18T15:44:04.048310 | `9e878ea3202bd687a04489f5e949add70c53f09deca4e81b343953ab72d1b20e` |
| `reports/live/orders_stream.jsonl` | `reports_logs` | 1,768,924 | 2026-10-17T15:52:40.390823 | `3cc3d3b97f3484d5ecc0444d9998865063aa2d153d32220366c498dda9280d79` |
| `reports/live/prediction_outcomes_stream.jsonl` | `reports_logs` | 4,795,623 | 2026-10-15T23:58:18.957656 | `1a90f1f98b4133a4c04e82b75dcb560ef73534e973de22298d706ce22c744560` |
| `reports/live/prediction_provenance_stream.jsonl` | `reports_logs` | 6,753,442 | 2026-10-15T15:14:58.380459 | `bb49c716cd55850f3c2b369dae352be11e9e73e874563c13a07a57b7e7482e4d` |
| `reports/live/runtime_state.json` | `reports_logs` | 519 | 2026-10-16T01:13:35.511556 | `ba3f8676ec8cb5cb793c53e581801cfc5b7b44f9935685cc20066970c8b8f572` |
| `tests/test_timezone_regression.py` | `test_suite` | 7,788 | 2026-10-17T15:34:33.424296 | `502c69f3aae4976fe0e5b3225fae3f632f21297f8dfb41f15a7fbc5ed2fe38dd` |
| `tests/test_specialist_output_regression.py` | `test_suite` | 10,288 | 2026-10-17T15:37:34.280932 | `c7d04353a86663f457757975a990ab2cf0ac95262bdd318b1abe7162d9b1896e` |
| `CRITICAL_FIXES_REPORT.md` | `documentation` | 20,278 | 2026-10-17T16:02:12.421129 | `f0e28df8ba8c51ec4909174a9ba377b4a143103992e7e3311f2edb9cfa7af1d6` |
| `TEST_RESULTS.md` | `documentation` | 12,014 | 2026-10-17T16:02:44.524981 | `32066a6eb3cd43623ecca4f515fcc66c1dfd6b16903a6e72ed6909e19de1eb13` |
| `MONDAY_READINESS.md` | `documentation` | 16,290 | 2026-10-17T16:03:49.536503 | `0dfea9c0d0f9c1477ac2bb30a421078907b8bce218971cd72efd6569c2b61fda` |
| `ARCHITECTURE_MAP.md` | `documentation` | 40,900 | 2026-09-19T12:12:47.346749 | `b3890a30de439da929bc1b10b9583f97f257517d356331e2c2771e16e7e42f0a` |
| `FINAL_INDEPENDENT_VERIFICATION.md` | `documentation` | 23,344 | 2026-10-16T21:25:07.071485 | `9ec128571d8ca0b0888d3dd196372e9f142001715d8690697852891c19ad6f70` |

## 3. Working Tree Status and Uncommitted Changes Analysis
The working tree contains both tracked modifications and untracked files/directories:
1. **Tracked Modified Files:**
   - `QA/models/one_min_predictor.py`: Contains Task 1 timezone consistency logic (`Asia/Kolkata` localization/conversion).
   - `QA/scripts/build_and_train_live_1m.py`: Contains training-side timezone consistency fix (`Asia/Kolkata`).
   - `QA/engine/ai_agent_supervisor.py`, `QA/engine/compounding_trader.py`: V2 legacy compounding and supervisor modules.
   - `QA/models/saved_models_1m/*.joblib`: Pre-trained tree models.
2. **Untracked Production System Files (`v3/`):**
   - The entire `v3/` directory (`v3/execution/`, `v3/intelligence/`, `v3/models/`, `v3/research/`) is untracked in Git. However, it is physically present on disk, actively imported by `run_live_trader.py` (`from v3.execution.live_trader import AlphaNSELiveTrader`), and executed by all production runners.
   - Verification confirms `v3/intelligence/opportunity_engine.py` contains `validate_specialist_output()`, `extract_19_features()`, and strict boolean exclusion.
3. **Untracked Historical Datasets & Reports:**
   - `QA/data/genuine_forward_oos_oct13_oct14.csv`, `QA/data/*_1m_weekend.csv`.
   - `reports/live/orders_stream.jsonl`, `reports/live/prediction_outcomes_stream.jsonl`, `reports/live/runtime_state.json`.
4. **Prior Audit & Readiness Reports:**
   - `CRITICAL_FIXES_REPORT.md`, `TEST_RESULTS.md`, `MONDAY_READINESS.md`, `ARCHITECTURE_MAP.md`, `FINAL_INDEPENDENT_VERIFICATION.md`.
   - These prior documents are preserved intact and not overwritten.

## 4. Verification of Critical Fixes in Runtime Path
- **Task 1 (Timezone Consistency):**
  - Runtime Source File: `QA/models/one_min_predictor.py` (Line 267-278).
  - Active Code: Checks `hasattr(ts.dt, 'tz')`. If naive, localizes to `Asia/Kolkata`. If aware, converts to `Asia/Kolkata`. Minutes from 09:15 AM IST are clipped to `[0, 375]`.
  - Training Source File: `QA/scripts/build_and_train_live_1m.py` (Line 214-222).
  - Active Code: Identical `Asia/Kolkata` localization/conversion applied before feature extraction.
  - Direct Importer: `v3/execution/live_trader.py` imports `OneMinPredictor` directly at line 60.
- **Task 2 (Specialist Model Output Handling):**
  - Runtime Source File: `v3/intelligence/opportunity_engine.py` (Line 368-430).
  - Active Code: `validate_specialist_output(raw_output)` strictly rejects booleans (`isinstance(val, bool)` -> False), non-floats, arrays with length != 1, and non-finite values (`np.isnan`, `np.isinf`). Rejections fail closed with `score = 0.0`, `viable = False`, `net_expectancy_bps = -9999.0` without fabricating fallback scores.
  - Direct Importer: `v3/execution/live_trader.py` imports `OpportunityDiscoveryEngine` directly at line 61.

## 5. Machine-Readable Inventory Deliverable
- Complete machine-readable inventory is preserved at `audit/file_inventory.json` (full metadata) and `audit/file_inventory.csv` (1,296 indexed files with relative paths, categories, sizes, modification timestamps, and SHA-256 hashes).