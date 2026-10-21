"""
Phase 2 Data Ingestion & Validation Execution Script.
Orchestrates universe tracking, corporate actions fetching, raw data acquisition,
parquet pipeline normalization, manifest generation, and grid validation.
"""

import os
import sys
import logging
import json
import pandas as pd

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("phase2_ingestion")

def main():
    logger.info("=== STARTING ALPHANSE V2 PHASE 2 DATA INGESTION ===")

    # 1. Universe Membership
    logger.info("Step 1: Initializing Universe Membership...")
    from v2.data.storage.universe_tracker import UniverseTracker
    tracker = UniverseTracker()
    universe_df = tracker.initialize_default_universe()
    logger.info(f"Universe membership initialized: {len(universe_df)} symbols recorded.")

    # 2. Corporate Actions
    logger.info("Step 2: Fetching Corporate Actions (splits and dividends)...")
    from v2.data.ingestion.corporate_actions_fetcher import CorporateActionsFetcher
    corp_fetcher = CorporateActionsFetcher()
    corp_df = corp_fetcher.fetch_actions()
    logger.info(f"Corporate actions recorded: {len(corp_df)} actions found.")

    # 3. Historical Data Fetcher (5m and 1m)
    logger.info("Step 3: Fetching Historical Data from Yahoo Finance...")
    from v2.data.ingestion.historical_fetcher import HistoricalFetcher
    hist_fetcher = HistoricalFetcher()
    fetch_results = hist_fetcher.fetch_all(force_refresh=False)
    logger.info("Historical downloads completed.")

    # 4. Parquet Normalization Pipeline
    logger.info("Step 4: Running Parquet Pipeline for 5m and 1m data...")
    from v2.data.storage.parquet_pipeline import ParquetPipeline
    pipeline = ParquetPipeline()
    
    raw_5m, adj_5m = pipeline.run_pipeline_for_interval(interval="5m")
    raw_1m, adj_1m = pipeline.run_pipeline_for_interval(interval="1m")

    # Generate Manifest
    generated_files = [
        raw_5m, adj_5m, raw_1m, adj_1m,
        tracker.parquet_path,
        os.path.join("v2/data/storage/metadata", "corporate_actions.parquet")
    ]
    manifest = pipeline.generate_manifest(generated_files)
    logger.info(f"Generated manifest with {len(manifest['files'])} files tracked.")

    # 5. Grid Validation & Data Gate
    logger.info("Step 5: Validating 5m Session Grid and Evaluating Data Gate...")
    from v2.data.validation.grid_validator import GridValidator
    validator = GridValidator(interval="5m")
    df_5m = pd.read_parquet(raw_5m)
    decision = validator.validate_dataset(df_5m)

    logger.info("=== PHASE 2 DATA GATE EVALUATION RESULTS ===")
    logger.info(f"Status: {decision.status}")
    logger.info(f"Passed Gate: {decision.passed_gate}")
    logger.info(f"Sessions Detected: {decision.session_count}")
    logger.info(f"Total Bars: {decision.total_bars}")
    logger.info(f"Symbols: {decision.symbol_count}")
    
    for crit_name, crit in decision.criteria_results.items():
        pass_str = "PASS" if crit["passed"] else "FAIL"
        logger.info(f"  [{pass_str}] {crit_name}: actual={crit['actual']} (target: {crit['target']})")

    # Save decision to json for reporting
    decision_path = "v2/data/storage/metadata/data_coverage_decision.json"
    decision_dict = {
        "status": decision.status,
        "passed_gate": decision.passed_gate,
        "session_count": decision.session_count,
        "total_bars": decision.total_bars,
        "symbol_count": decision.symbol_count,
        "evaluation_time": decision.evaluation_time,
        "criteria_results": decision.criteria_results,
        "symbol_metrics": decision.symbol_metrics,
        "regime_breakdown": decision.regime_breakdown
    }
    import numpy as np

    def _json_serial(o):
        if isinstance(o, (bool, np.bool_)):
            return bool(o)
        if isinstance(o, (int, np.integer)):
            return int(o)
        if isinstance(o, (float, np.floating)):
            return float(o)
        return str(o)

    with open(decision_path, "w", encoding="utf-8") as f:
        json.dump(decision_dict, f, indent=2, default=_json_serial)
    logger.info(f"Saved data coverage decision to {decision_path}")

    logger.info("=== PHASE 2 INGESTION COMPLETE ===")
    return decision.status

if __name__ == "__main__":
    status = main()
    if status == "DATA_BLOCKED":
        sys.exit(1)
    sys.exit(0)
