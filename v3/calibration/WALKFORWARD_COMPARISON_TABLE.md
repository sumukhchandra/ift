# OOS Walk-Forward Calibration Comparison

> **Chronology invariant:** Factor for session D computed strictly from sessions < D.
> Realized metrics are ground-truth (same row for both columns).

## Per-Session Detail

### Session 2026-09-24
- OOS factor: **0.4828** (WEIGHTED_MEDIAN, n=9)

| Metric | Uncalibrated (factor=1.0) | OOS Calibrated | Realized (ground truth) |
| :--- | :---: | :---: | :---: |
| Calibration factor applied | 1.000 | 0.4828 | — |
| Trades triggered | 10 | 0 | 0 |
| Avg gross expected (bps) | +32.36 | +0.00 | — |
| Avg net expected (bps) | +14.51 | +0.00 | — |
| Total net expected (₹) | ₹+58.37 | ₹+0.00 | — |
| Directional accuracy | 100.0% | 100.0% | 100.0% |
| Mean abs magnitude error (bps) | 2.9 | 2.9 | 2.9 |
| Realized net P&L (₹) | — | — | ₹+0.00 |

### Session 2026-09-25
- OOS factor: **0.4858** (WEIGHTED_MEDIAN, n=10)

| Metric | Uncalibrated (factor=1.0) | OOS Calibrated | Realized (ground truth) |
| :--- | :---: | :---: | :---: |
| Calibration factor applied | 1.000 | 0.4858 | — |
| Trades triggered | 5 | 3 | 2 |
| Avg gross expected (bps) | +54.76 | +36.54 | — |
| Avg net expected (bps) | +36.89 | +18.66 | — |
| Total net expected (₹) | ₹+74.50 | ₹+22.33 | — |
| Directional accuracy | 100.0% | 100.0% | 100.0% |
| Mean abs magnitude error (bps) | 47.2 | 47.2 | 47.2 |
| Realized net P&L (₹) | — | — | ₹+0.00 |

## Aggregate Comparison (All Sessions in Walk-Forward)

| Metric | Uncalibrated | OOS Calibrated | Δ |
| :--- | :---: | :---: | :---: |
| Total trades | 15 | 3 | -12 |
| Zero-trade sessions | 0 | 1 | +1 |
| Total net expected (₹) | ₹+132.87 | ₹+22.33 | ₹-110.54 |
| Directional accuracy | 100.0% | 100.0% | — |
| Mean abs magnitude error | 25.1 bps | (calibrated) | — |
| Realized net P&L | — | — | ₹+0.00 |

> **Note:** Directional accuracy and magnitude error are model properties, unchanged by
> calibration (calibration scales magnitude only, not direction). The key question is
> whether calibration causes the net-edge gate to trigger on economically valid candidates
> (calibrated gross > cost) while correctly suppressing marginal ones.

## Session 6 Protocol

The factor computed from Sessions 1–5 OOS history will be:

```
factor  = 0.4858
method  = WEIGHTED_MEDIAN
n_obs   = 12
window  = 2026-09-18 → 2026-09-25
```

> Freeze this before 09:15 on 2026-09-26.
> Broker execution remains **locked** (paper/shadow mode).
