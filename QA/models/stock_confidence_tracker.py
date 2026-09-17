"""
Stock Confidence Tracker (Adaptive Intelligence Phase 2.1).
Maintains rolling per-symbol prediction verification metrics, dynamically scales
confidence multipliers, and manages adaptive blacklisting/whitelisting.
"""

import os
import json
import threading
from collections import deque
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIDENCE_STATE_FILE = os.path.join(PROJECT_ROOT, "logs", "stock_confidence_tracker.json")

# Initial empirical baseline priors from out-of-sample platform analysis
DEFAULT_PRIORS = {
    "BHARTIARTL.NS": {"accuracy": 0.64, "samples": 25},
    "RELIANCE.NS":   {"accuracy": 0.60, "samples": 25},
    "TATACAP.NS":    {"accuracy": 0.60, "samples": 25},
    "INFY.NS":       {"accuracy": 0.52, "samples": 25},
    "TCS.NS":        {"accuracy": 0.52, "samples": 25},
    "HDFCBANK.NS":   {"accuracy": 0.48, "samples": 25},
    "BAJFINANCE.NS": {"accuracy": 0.48, "samples": 25},
    "AXISBANK.NS":   {"accuracy": 0.44, "samples": 25},
    "ICICIBANK.NS":  {"accuracy": 0.44, "samples": 25},
    "SBIN.NS":       {"accuracy": 0.36, "samples": 25},
}


class StockConfidenceTracker:
    """
    Maintains rolling per-symbol prediction accuracy to dynamically calibrate
    model confidence and suppress trades on poor-edge symbols.
    """

    def __init__(self, window: int = 50):
        self.window = window
        self.lock = threading.RLock()
        self.history: Dict[str, deque] = {}
        self.blacklisted: set = set()
        self.reasons: Dict[str, str] = {}
        self._load_or_init()

    def _load_or_init(self):
        """Loads tracker state from disk or initializes with empirical priors."""
        from stocks_config import STOCK_BLACKLIST, STOCK_SYMBOLS
        self.blacklisted = set(STOCK_BLACKLIST)

        if os.path.exists(CONFIDENCE_STATE_FILE):
            try:
                with open(CONFIDENCE_STATE_FILE, "r") as f:
                    data = json.load(f)
                for sym, entries in data.get("history", {}).items():
                    self.history[sym] = deque(entries, maxlen=self.window)
                self.blacklisted = set(data.get("blacklisted", list(STOCK_BLACKLIST)))
                self.reasons = data.get("reasons", {})
                return
            except Exception as e:
                print(f"[StockConfidenceTracker] Error loading state file: {e}. Reinitializing.")

        # Seed with empirical baseline priors
        for sym in STOCK_SYMBOLS:
            self.history[sym] = deque(maxlen=self.window)
            prior = DEFAULT_PRIORS.get(sym, {"accuracy": 0.50, "samples": 20})
            total = prior["samples"]
            hits = int(total * prior["accuracy"])
            for _ in range(hits):
                self.history[sym].append(True)
            for _ in range(total - hits):
                self.history[sym].append(False)

            if sym in self.blacklisted:
                self.reasons[sym] = f"Baseline accuracy ({prior['accuracy']*100:.1f}%) below 50% hurdle"

        self._save()

    def _save(self):
        """Persist state to disk safely."""
        try:
            payload = {
                "window": self.window,
                "history": {s: list(h) for s, h in self.history.items()},
                "blacklisted": list(self.blacklisted),
                "reasons": self.reasons
            }
            with open(CONFIDENCE_STATE_FILE, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[StockConfidenceTracker] Error saving state: {e}")

    def update(self, symbol: str, was_direction_correct: bool):
        """Records a resolved prediction verification."""
        with self.lock:
            if symbol not in self.history:
                self.history[symbol] = deque(maxlen=self.window)
            self.history[symbol].append(bool(was_direction_correct))
            self._save()

    def get_accuracy(self, symbol: str) -> float:
        """Returns the rolling directional accuracy (0.0 - 1.0) for the symbol."""
        with self.lock:
            h = self.history.get(symbol)
            if not h:
                return 0.50
            return float(sum(h) / len(h))

    def get_sample_count(self, symbol: str) -> int:
        with self.lock:
            h = self.history.get(symbol)
            return len(h) if h else 0

    def is_blacklisted(self, symbol: str) -> bool:
        with self.lock:
            return symbol in self.blacklisted

    def blacklist(self, symbol: str, reason: str = "Poor predictive accuracy"):
        with self.lock:
            self.blacklisted.add(symbol)
            self.reasons[symbol] = reason
            self._save()

    def whitelist(self, symbol: str, reason: str = "Accuracy recovered above threshold"):
        with self.lock:
            self.blacklisted.discard(symbol)
            self.reasons.pop(symbol, None)
            self._save()

    def get_multiplier(self, symbol: str) -> float:
        """
        Computes dynamic confidence multiplier (0.0 to 1.35).
        - Blacklisted or <45% accuracy -> 0.0 (strictly zero trade entry)
        - 45% - 52% accuracy -> 0.50 (harsh dampener)
        - 52% - 62% accuracy -> 1.00 (neutral pass-through)
        - >= 62% accuracy -> 1.25 (conviction boost for proven performers)
        """
        with self.lock:
            if symbol in self.blacklisted:
                return 0.0

            h = self.history.get(symbol)
            if not h or len(h) < 10:
                return 1.0

            acc = sum(h) / len(h)
            if acc < 0.45:
                return 0.0
            elif acc < 0.52:
                return 0.50
            elif acc >= 0.62:
                return 1.25
            return 1.0

    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Returns structured status profile for the symbol."""
        with self.lock:
            h = self.history.get(symbol, deque())
            total = len(h)
            acc = (sum(h) / total) if total > 0 else 0.50
            is_bl = symbol in self.blacklisted
            mult = self.get_multiplier(symbol)

            if is_bl:
                tier = "BLACKLISTED"
            elif acc < 0.45:
                tier = "SUPPRESSED"
            elif acc < 0.52:
                tier = "PENALIZED"
            elif acc >= 0.62:
                tier = "BOOSTED"
            else:
                tier = "NEUTRAL"

            return {
                "symbol": symbol,
                "directional_accuracy_pct": round(acc * 100, 1),
                "verified_samples": total,
                "confidence_multiplier": mult,
                "tier": tier,
                "is_blacklisted": is_bl,
                "reason": self.reasons.get(symbol, "Nominal")
            }

    def get_all_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Returns status profiles for all tracked stocks."""
        from stocks_config import STOCK_SYMBOLS
        return {sym: self.get_profile(sym) for sym in STOCK_SYMBOLS}
