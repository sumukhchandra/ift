import os, sys
sys.path.append('.')
from QA.engine.compounding_trader import CompoundingTrader, STOCK_SYMBOLS
import pandas as pd
import numpy as np

trader = CompoundingTrader()

for sym in STOCK_SYMBOLS:
    candles = trader.get_or_generate_candles(sym)
    feat_df = trader.predictor.extract_features_1m(candles)
    last_row = feat_df.iloc[-1]
    X = feat_df[trader.predictor.feature_cols].iloc[[-1]].fillna(0)
    
    current_price = float(last_row["close"])
    preds = [float(model.predict(X)[0]) for name, model in trader.predictor.regressors.items()]
    base_pred = float(np.mean(preds)) if preds else 0.0
    
    mom_1m = float(last_row.get("ret_1m", 0.0))
    mom_3m = float(last_row.get("ret_3m", 0.0))
    mom_5m = float(last_row.get("ret_5m", 0.0))
    rsi_7 = float(last_row.get("micro_rsi_7", 50.0))
    ema_cross = float(last_row.get("ema_cross_5_20", 0.0))
    upper_wick = float(last_row.get("upper_wick_ratio", 0.0))
    wick_pressure = float(last_row.get("wick_pressure", 0.5))
    vol_zscore = float(last_row.get("vol_spike_zscore", 0.0))
    sym_atr = float(last_row.get("micro_atr_14", 0.0025))
    
    trend_alpha = (mom_1m * 0.4) + (mom_3m * 0.3) + (mom_5m * 0.3)
    
    # Blended predicted return
    pred_return = base_pred
    if trend_alpha > 0 and ema_cross > 0:
        pred_return = (pred_return * 0.4) + (trend_alpha * 0.6)
    elif trend_alpha < 0 and ema_cross < 0:
        pred_return = (pred_return * 0.4) + (trend_alpha * 0.6)
        
    prob_raw = float(trader.predictor.classifier.predict_proba(X)[0][1])
    
    # Check rejection filters
    is_exhaustion = (upper_wick > 0.40 and wick_pressure < 0.45) or (rsi_7 > 72.0 and vol_zscore < -0.2)
    
    # Bullish trigger:
    # 1. Positive predicted return and positive short-term momentum / trend
    # 2. Not in exhaustion
    # 3. Model or breakout confidence above baseline (prob_raw >= 0.12 or ema_cross > 0)
    is_bullish = (pred_return > 0.0001) and (not is_exhaustion) and (prob_raw >= 0.11 or ema_cross > 0)
    
    print(f"{sym:15s} | Close: {current_price:8.2f} | PredRet: {pred_return*100:+.4f}% | ProbRaw: {prob_raw:.3f} | Mom1m: {mom_1m*100:+.3f}% | EMACross: {ema_cross*100:+.3f}% | Bullish: {is_bullish}")
