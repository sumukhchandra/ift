"""
Incremental Feature Engine for AlphaNSE V2.
Maintains bounded circular buffers and stateful accumulators for O(1) / O(W) updates per tick.
Also provides compute_full_features() for batch / golden fixture equivalence testing.
"""

import math
from collections import deque
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from ..data.schema import Bar
from .indicators import (
    calculate_true_range,
    calculate_parkinson_volatility,
    calculate_rsi,
    calculate_wick_ratios
)


class SymbolFeatureState:
    """Bounded rolling memory buffer for a single stock symbol."""

    def __init__(self, symbol: str, max_lookback: int = 65):
        self.symbol = symbol
        self.max_lookback = max_lookback

        # Price & volume deques
        self.closes: deque = deque(maxlen=max_lookback)
        self.highs: deque = deque(maxlen=max_lookback)
        self.lows: deque = deque(maxlen=max_lookback)
        self.opens: deque = deque(maxlen=max_lookback)
        self.volumes: deque = deque(maxlen=max_lookback)
        self.timestamps: deque = deque(maxlen=max_lookback)

        # Derived metric deques
        self.returns_1m: deque = deque(maxlen=max_lookback)
        self.true_ranges: deque = deque(maxlen=max_lookback)
        self.parkinson_vols: deque = deque(maxlen=max_lookback)
        self.micro_atr_14_series: deque = deque(maxlen=max_lookback)
        self.rsi_7_series: deque = deque(maxlen=max_lookback)
        self.ema_cross_series: deque = deque(maxlen=max_lookback)

        # Recursive accumulators
        self.cum_pv: float = 0.0
        self.cum_vol: float = 0.0
        self.ema_5: Optional[float] = None
        self.ema_20: Optional[float] = None


class IncrementalFeatureEngine:
    """
    Stateful incremental feature engine.
    Ingests one Bar at a time and computes all 30 AlphaNSE indicators in bounded time.
    """

    FEATURE_NAMES = [
        "ret_1m", "ret_3m", "ret_5m", "ret_10m",
        "accel_1m", "micro_rsi_7", "micro_rsi_14",
        "micro_vwap_dist", "micro_atr_14", "parkinson_vol",
        "bb_pct_b", "bb_bandwidth", "orderflow_imbalance",
        "vol_surge_ratio", "nifty_ret_1m", "nifty_lead_lag",
        "ema_cross_5_20", "atr_vol_ratio", "momentum_divergence",
        "vol_spike_zscore", "wick_pressure", "upper_wick_ratio", "lower_wick_ratio",
        "time_sin", "time_cos", "session_phase",
        "rolling_vwap_dist", "ema_cross_velocity",
        "stock_id_hash", "parkinson_vol_rolling"
    ]

    def __init__(self, max_lookback: int = 65):
        self.max_lookback = max_lookback
        self._states: Dict[str, SymbolFeatureState] = {}

    def get_state(self, symbol: str) -> SymbolFeatureState:
        if symbol not in self._states:
            self._states[symbol] = SymbolFeatureState(symbol, self.max_lookback)
        return self._states[symbol]

    def update(self, bar: Bar, nifty_ret_1m: float = 0.0) -> Dict[str, float]:
        """
        Incrementally process a newly closed bar and produce the 30-feature vector.
        Complexity: O(1) for recursive accumulators, O(W) for sliding window deques with W <= 60.
        """
        st = self.get_state(bar.symbol)
        c = bar.close
        h = bar.high
        l = bar.low
        o = bar.open
        v = max(bar.volume, 1.0)
        ts = bar.timestamp

        prev_close = st.closes[-1] if st.closes else None

        # 1. Multi-scale Returns
        ret_1m = (c - prev_close) / prev_close if prev_close else 0.0
        ret_3m = (c - st.closes[-3]) / st.closes[-3] if len(st.closes) >= 3 else 0.0
        ret_5m = (c - st.closes[-5]) / st.closes[-5] if len(st.closes) >= 5 else 0.0
        ret_10m = (c - st.closes[-10]) / st.closes[-10] if len(st.closes) >= 10 else 0.0

        prev_ret_1m = st.returns_1m[-1] if st.returns_1m else 0.0
        accel_1m = ret_1m - prev_ret_1m

        # Append to deques
        st.closes.append(c)
        st.highs.append(h)
        st.lows.append(l)
        st.opens.append(o)
        st.volumes.append(v)
        st.timestamps.append(ts)
        st.returns_1m.append(ret_1m)

        # 2. Micro-RSI (7 & 14 period)
        # Compute deltas over recent bars
        deltas = [st.closes[i] - st.closes[i - 1] for i in range(1, len(st.closes))]
        
        # RSI 7
        recent_7 = deltas[-7:] if len(deltas) >= 7 else deltas
        gains_7 = [max(0.0, d) for d in recent_7]
        losses_7 = [max(0.0, -d) for d in recent_7]
        micro_rsi_7 = calculate_rsi(gains_7, losses_7) if recent_7 else 50.0

        # RSI 14
        recent_14 = deltas[-14:] if len(deltas) >= 14 else deltas
        gains_14 = [max(0.0, d) for d in recent_14]
        losses_14 = [max(0.0, -d) for d in recent_14]
        micro_rsi_14 = calculate_rsi(gains_14, losses_14) if recent_14 else 50.0

        # 3. Micro-VWAP & Distance (Cumulative session VWAP)
        st.cum_pv += c * v
        st.cum_vol += v
        session_vwap = st.cum_pv / (st.cum_vol + 1e-9)
        micro_vwap_dist = (c - session_vwap) / (session_vwap + 1e-9)

        # Rolling 30 VWAP
        w30 = min(len(st.closes), 30)
        recent_closes = list(st.closes)[-w30:]
        recent_vols = list(st.volumes)[-w30:]
        rolling_pv = sum(px * vol for px, vol in zip(recent_closes, recent_vols))
        rolling_vol_sum = sum(recent_vols)
        rolling_vwap = rolling_pv / (rolling_vol_sum + 1e-9)
        rolling_vwap_dist = (c - rolling_vwap) / (rolling_vwap + 1e-9)

        # 4. Micro-ATR & Parkinson Volatility
        tr = calculate_true_range(h, l, prev_close)
        st.true_ranges.append(tr)

        w14 = min(len(st.true_ranges), 14)
        atr_14_raw = sum(list(st.true_ranges)[-w14:]) / w14 if w14 > 0 else tr
        micro_atr_14 = atr_14_raw / (c + 1e-9)
        st.micro_atr_14_series.append(micro_atr_14)

        park_vol = calculate_parkinson_volatility(h, l)
        st.parkinson_vols.append(park_vol)

        w10_park = min(len(st.parkinson_vols), 10)
        parkinson_vol_rolling = sum(list(st.parkinson_vols)[-w10_park:]) / w10_park if w10_park > 0 else park_vol

        # 5. Bollinger Bands (20 period, 2 std)
        w20 = min(len(st.closes), 20)
        recent_20_c = list(st.closes)[-w20:]
        mean_20 = sum(recent_20_c) / w20
        var_20 = sum((x - mean_20) ** 2 for x in recent_20_c) / w20
        std_20 = math.sqrt(var_20) if var_20 > 0 else 0.0
        upper_bb = mean_20 + (2.0 * std_20)
        lower_bb = mean_20 - (2.0 * std_20)
        bb_span = upper_bb - lower_bb
        if bb_span < 1e-5:
            bb_pct_b = 0.5
            bb_bandwidth = 0.0
        else:
            bb_pct_b = (c - lower_bb) / (bb_span + 1e-9)
            bb_bandwidth = bb_span / (mean_20 + 1e-9)

        # 6. Microstructure Order Flow Imbalance Proxy
        candle_range = max(h - l, 1e-5)
        orderflow_imbalance = v * ((c - o) / candle_range)

        vol_mean_20 = sum(recent_vols[-20:]) / min(len(recent_vols), 20) if recent_vols else 1.0
        vol_surge_ratio = v / (vol_mean_20 + 1e-9)

        w30_v = min(len(st.volumes), 30)
        recent_30_v = list(st.volumes)[-w30_v:]
        vol_mean_30 = sum(recent_30_v) / w30_v
        vol_var_30 = sum((x - vol_mean_30) ** 2 for x in recent_30_v) / w30_v
        vol_std_30 = math.sqrt(vol_var_30) if vol_var_30 > 0 else 1.0
        vol_spike_zscore = max(-3.0, min(5.0, (v - vol_mean_30) / (vol_std_30 + 1e-9)))

        # 7. Cross-Asset NIFTY 50
        nifty_lead_lag = ret_1m - nifty_ret_1m

        # 8. Fast EMA 5 vs EMA 20
        alpha_5 = 2.0 / (5.0 + 1.0)
        alpha_20 = 2.0 / (20.0 + 1.0)
        if st.ema_5 is None:
            st.ema_5 = c
        else:
            st.ema_5 = (alpha_5 * c) + ((1.0 - alpha_5) * st.ema_5)

        if st.ema_20 is None:
            st.ema_20 = c
        else:
            st.ema_20 = (alpha_20 * c) + ((1.0 - alpha_20) * st.ema_20)

        ema_cross_5_20 = (st.ema_5 - st.ema_20) / (st.ema_20 + 1e-9)
        st.ema_cross_series.append(ema_cross_5_20)

        ema_cross_velocity = (
            st.ema_cross_series[-1] - st.ema_cross_series[-4]
            if len(st.ema_cross_series) >= 4 else 0.0
        )

        # 9. Volatility Expansion Ratio (Micro-ATR vs rolling 60 baseline)
        w60_atr = min(len(st.micro_atr_14_series), 60)
        rolling_atr_60 = sum(list(st.micro_atr_14_series)[-w60_atr:]) / w60_atr if w60_atr > 0 else micro_atr_14
        atr_vol_ratio = micro_atr_14 / (rolling_atr_60 + 1e-9)

        # 10. Momentum Divergence (Price delta 3m vs RSI delta 3m)
        st.rsi_7_series.append(micro_rsi_7)
        rsi_diff_3 = (st.rsi_7_series[-1] - st.rsi_7_series[-4]) / 100.0 if len(st.rsi_7_series) >= 4 else 0.0
        momentum_divergence = ret_3m - rsi_diff_3

        # 11. Candlestick Wick Dynamics
        wick_pressure, upper_wick_ratio, lower_wick_ratio = calculate_wick_ratios(o, h, l, c)

        # 12. Time of Day & Cyclical Encodings
        minutes_from_open = max(0, min(375, (ts.hour * 60 + ts.minute) - (9 * 60 + 15)))
        time_sin = math.sin(2.0 * math.pi * minutes_from_open / 375.0)
        time_cos = math.cos(2.0 * math.pi * minutes_from_open / 375.0)
        if minutes_from_open <= 30:
            session_phase = 0.0
        elif minutes_from_open <= 120:
            session_phase = 1.0
        elif minutes_from_open <= 240:
            session_phase = 2.0
        else:
            session_phase = 3.0

        # Stock ID deterministic hash
        stock_id_hash = float((hash(bar.symbol) % 100) / 100.0)

        features = {
            "ret_1m": float(ret_1m),
            "ret_3m": float(ret_3m),
            "ret_5m": float(ret_5m),
            "ret_10m": float(ret_10m),
            "accel_1m": float(accel_1m),
            "micro_rsi_7": float(micro_rsi_7),
            "micro_rsi_14": float(micro_rsi_14),
            "micro_vwap_dist": float(micro_vwap_dist),
            "micro_atr_14": float(micro_atr_14),
            "parkinson_vol": float(park_vol),
            "bb_pct_b": float(bb_pct_b),
            "bb_bandwidth": float(bb_bandwidth),
            "orderflow_imbalance": float(orderflow_imbalance),
            "vol_surge_ratio": float(vol_surge_ratio),
            "nifty_ret_1m": float(nifty_ret_1m),
            "nifty_lead_lag": float(nifty_lead_lag),
            "ema_cross_5_20": float(ema_cross_5_20),
            "atr_vol_ratio": float(atr_vol_ratio),
            "momentum_divergence": float(momentum_divergence),
            "vol_spike_zscore": float(vol_spike_zscore),
            "wick_pressure": float(wick_pressure),
            "upper_wick_ratio": float(upper_wick_ratio),
            "lower_wick_ratio": float(lower_wick_ratio),
            "time_sin": float(time_sin),
            "time_cos": float(time_cos),
            "session_phase": float(session_phase),
            "rolling_vwap_dist": float(rolling_vwap_dist),
            "ema_cross_velocity": float(ema_cross_velocity),
            "stock_id_hash": float(stock_id_hash),
            "parkinson_vol_rolling": float(parkinson_vol_rolling)
        }
        return features


def compute_full_features(bars: List[Bar]) -> pd.DataFrame:
    """
    Computes all 30 features across a complete list of bars in batch mode.
    Used for regression testing and numerical equivalence validation against IncrementalFeatureEngine.
    """
    if not bars:
        return pd.DataFrame()

    records = [
        {
            "timestamp": b.timestamp,
            "symbol": b.symbol,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume
        }
        for b in sorted(bars, key=lambda x: x.timestamp)
    ]
    df = pd.DataFrame(records)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_p = df["open"]
    vol = df["volume"].replace(0, 1.0)

    # Returns
    df["ret_1m"] = close.pct_change(1).fillna(0.0)
    df["ret_3m"] = close.pct_change(3).fillna(0.0)
    df["ret_5m"] = close.pct_change(5).fillna(0.0)
    df["ret_10m"] = close.pct_change(10).fillna(0.0)
    df["accel_1m"] = df["ret_1m"].diff().fillna(0.0)

    # RSI
    delta = close.diff().fillna(0.0)
    gain_7 = delta.clip(lower=0).rolling(7, min_periods=1).mean()
    loss_7 = (-delta.clip(upper=0)).rolling(7, min_periods=1).mean()
    sum_7 = gain_7 + loss_7
    df["micro_rsi_7"] = np.where(sum_7 == 0, 50.0, 100.0 - (100.0 / (1.0 + (gain_7 / (loss_7 + 1e-9)))))

    gain_14 = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss_14 = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    sum_14 = gain_14 + loss_14
    df["micro_rsi_14"] = np.where(sum_14 == 0, 50.0, 100.0 - (100.0 / (1.0 + (gain_14 / (loss_14 + 1e-9)))))

    # Cumulative VWAP
    cum_pv = (close * vol).cumsum()
    cum_vol = vol.cumsum()
    vwap = cum_pv / (cum_vol + 1e-9)
    df["micro_vwap_dist"] = (close - vwap) / (vwap + 1e-9)

    # Rolling 30 VWAP
    rolling_pv = (close * vol).rolling(30, min_periods=1).sum()
    rolling_vol = vol.rolling(30, min_periods=1).sum()
    rolling_vwap = rolling_pv / (rolling_vol + 1e-9)
    df["rolling_vwap_dist"] = (close - rolling_vwap) / (rolling_vwap + 1e-9)

    # True Range & ATR
    tr = np.maximum(
        high - low,
        np.maximum(
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        )
    ).fillna(high - low)
    df["micro_atr_14"] = (tr.rolling(14, min_periods=1).mean() / (close + 1e-9)).fillna(0.0)

    # Parkinson Volatility
    hl_ratio = np.log(high / low.replace(0, np.nan)).fillna(0.0)
    df["parkinson_vol"] = np.sqrt((hl_ratio ** 2) / (4.0 * np.log(2.0))).fillna(0.0)
    df["parkinson_vol_rolling"] = df["parkinson_vol"].rolling(10, min_periods=1).mean().fillna(df["parkinson_vol"])

    # Bollinger Bands
    rolling_mean_20 = close.rolling(20, min_periods=1).mean()
    rolling_std_20 = close.rolling(20, min_periods=1).std(ddof=0).fillna(1e-5)
    upper_bb = rolling_mean_20 + (2.0 * rolling_std_20)
    lower_bb = rolling_mean_20 - (2.0 * rolling_std_20)
    bb_span = upper_bb - lower_bb
    df["bb_pct_b"] = np.where(bb_span < 1e-5, 0.5, (close - lower_bb) / (bb_span + 1e-9))
    df["bb_bandwidth"] = np.where(bb_span < 1e-5, 0.0, bb_span / (rolling_mean_20 + 1e-9))

    # Order flow & Volume
    candle_range = (high - low).replace(0, 1e-5)
    df["orderflow_imbalance"] = (vol * ((close - open_p) / candle_range)).fillna(0.0)
    vol_mean_20 = vol.rolling(20, min_periods=1).mean()
    df["vol_surge_ratio"] = (vol / (vol_mean_20 + 1e-9)).fillna(1.0)

    vol_mean_30 = vol.rolling(30, min_periods=1).mean()
    vol_std_30 = vol.rolling(30, min_periods=1).std(ddof=0).fillna(1.0).replace(0, 1.0)
    df["vol_spike_zscore"] = ((vol - vol_mean_30) / (vol_std_30 + 1e-9)).clip(-3.0, 5.0).fillna(0.0)

    # Cross Asset
    df["nifty_ret_1m"] = 0.0
    df["nifty_lead_lag"] = df["ret_1m"]

    # EMA Cross
    ema_5 = close.ewm(span=5, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    df["ema_cross_5_20"] = ((ema_5 - ema_20) / (ema_20 + 1e-9)).fillna(0.0)
    df["ema_cross_velocity"] = df["ema_cross_5_20"].diff(3).fillna(0.0)

    # ATR expansion
    rolling_atr_60 = df["micro_atr_14"].rolling(60, min_periods=1).mean()
    df["atr_vol_ratio"] = (df["micro_atr_14"] / (rolling_atr_60 + 1e-9)).fillna(1.0)

    # Momentum divergence
    rsi_diff_3 = df["micro_rsi_7"].diff(3).fillna(0.0) / 100.0
    df["momentum_divergence"] = (df["ret_3m"] - rsi_diff_3).fillna(0.0)

    # Wick ratios
    bar_span = (high - low).replace(0, 1e-5)
    df["wick_pressure"] = ((close - low) / bar_span).clip(0.0, 1.0).fillna(0.5)
    df["upper_wick_ratio"] = ((high - np.maximum(open_p, close)) / bar_span).clip(0.0, 1.0).fillna(0.0)
    df["lower_wick_ratio"] = ((np.minimum(open_p, close) - low) / bar_span).clip(0.0, 1.0).fillna(0.0)

    # Cyclical & Identity
    ts_dt = pd.to_datetime(df["timestamp"])
    mins = (ts_dt.dt.hour * 60 + ts_dt.dt.minute) - (9 * 60 + 15)
    mins = mins.clip(0, 375)
    df["time_sin"] = np.sin(2.0 * np.pi * mins / 375.0)
    df["time_cos"] = np.cos(2.0 * np.pi * mins / 375.0)
    df["session_phase"] = np.where(mins <= 30, 0.0, np.where(mins <= 120, 1.0, np.where(mins <= 240, 2.0, 3.0)))
    df["stock_id_hash"] = df["symbol"].apply(lambda s: float((hash(s) % 100) / 100.0))

    return df
