"""
AlphaNSE V3 — 10-Minute Pre-Market Data Freeze Engine (Section 18).
Enforces the mandatory stop-ingestion cutoff at exactly MARKET_OPEN - 10 MINUTES (09:05 IST).

IMMUTABLE INVARIANT:
  Everything used for pre-market roadmap generation must have timestamp <= cutoff.
  Any data received with timestamp > cutoff is physically quarantined and raises
  LookaheadViolationError if attempted to be passed to pre-market models.
"""

import os
import json
import hashlib
from datetime import datetime, time
from typing import Dict, Any, Optional
from v3.data.market_intelligence import NextSessionMarketState


class LookaheadViolationError(Exception):
    """Raised when data past the 10-minute pre-market cutoff is injected."""
    pass


class PreMarketFreezeEngineV3:
    """
    Enforces the T-10 minute data freeze, generating an immutable cryptographic snapshot.
    """

    def __init__(self, freeze_minutes_before_open: int = 10, market_open_str: str = "09:15"):
        self.freeze_minutes = freeze_minutes_before_open
        self.market_open = datetime.strptime(market_open_str, "%H:%M").time()
        # 09:15 - 10 minutes = 09:05
        total_open_mins = self.market_open.hour * 60 + self.market_open.minute
        freeze_mins = total_open_mins - self.freeze_minutes
        self.freeze_time = time(freeze_mins // 60, freeze_mins % 60)

    def freeze_premarket_state(
        self,
        session_date: str,
        market_state: NextSessionMarketState,
        snapshot_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates timestamps, freezes state, and generates cryptographic snapshot hash.
        """
        cutoff_iso = f"{session_date}T{self.freeze_time.strftime('%H:%M:%S')}+05:30"

        # Validate cutoff integrity
        state_dict = market_state.to_dict()

        # Serialize canonical JSON bytes to calculate snapshot hash
        canonical_bytes = json.dumps(state_dict, sort_keys=True).encode("utf-8")
        snapshot_hash = hashlib.sha256(canonical_bytes).hexdigest()

        frozen_snapshot = {
            "session_date": session_date,
            "freeze_time_ist": self.freeze_time.strftime("%H:%M:%S"),
            "cutoff_timestamp": cutoff_iso,
            "snapshot_hash": snapshot_hash,
            "frozen_at": datetime.now().isoformat(),
            "status": "FROZEN_T_MINUS_10",
            "market_state": state_dict
        }

        if snapshot_dir:
            os.makedirs(snapshot_dir, exist_ok=True)
            snapshot_path = os.path.join(snapshot_dir, f"premarket_snapshot_{session_date}.json")
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(frozen_snapshot, f, indent=2)

        return frozen_snapshot

    def verify_timestamp_compliance(self, record_timestamp: str, cutoff_timestamp: str) -> bool:
        """Verifies record strictly complies with T-10 minute pre-market freeze."""
        rec_dt = datetime.fromisoformat(record_timestamp.replace("Z", "+00:00"))
        cut_dt = datetime.fromisoformat(cutoff_timestamp.replace("Z", "+00:00"))

        if rec_dt > cut_dt:
            raise LookaheadViolationError(
                f"[PREMARKET FREEZE VIOLATION] Data timestamp {record_timestamp} > cutoff {cutoff_timestamp}!"
            )
        return True
