# AlphaNSE V3 — Session 5 Pre-Market Readiness Report

> [!IMPORTANT]
> **CLASSIFICATION: FRESH FORWARD VALIDATION (SESSION 5 ONWARD)**  
> **EXPERIMENT TYPE**: Daily-Adaptive 60-Minute Horizon with Rupee Net-Edge Gating  
> **PROFITABILITY CLAIM**: False (Unproven experimental hypothesis)  
> **SAFETY**: Capital router locked; Broker execution physically disabled.

## 1. Cryptographic Model Provenance

- **Target Session Date**: 2026-09-25
- **Data Cutoff (D-1)**: `2026-09-24T15:25:00+05:30`
- **Training Dataset Hash**: `c64676e8a3056581fffc82b31d818b431151cb5e41ada8ab82bb352f5972ee0d`
- **Feature Pipeline Version**: `cdc70e950012b43a`
- **Model Version**: `AlphaNSE_V3_60m_20260925_v1`
- **Model SHA-256 Hash**: `ad765f8ebe55827dbb5280613dfb900d6b704f93dac43b44279cb7909c020f02`
- **Training Window**: 2026-06-29 to 2026-09-24
- **Training Observations**: 38,922 rows
- **Pre-Market Regime**: `NORMAL_VOL`

## 2. In-Sample Pre-Market Validation Metrics

- **In-Sample Rows**: 38,922
- **In-Sample MAE**: 27.76 bps
- **In-Sample IC**: 0.0788
- **Annualized Regime Volatility**: 16.61%
- **Sanity Gates Status**: `PASSED`

## 3. Session 5 Execution Parameters

| Parameter | Value | Rationale |
| :--- | :--- | :--- |
| **Holding Horizon** | 12 bars (60 minutes) | Lower turnover, higher gross return opportunity |
| **Universe** | Dynamic Tradable Equities (no index) | Dynamic ranking across all available liquid symbols |
| **Whitelist/Blacklist** | None (Dynamic) | Avoid premature blacklisting from only 4 sessions |
| **Morning Entry Window** | 09:15 to 12:00 IST | Active morning liquidity |
| **Lunch Blackout** | 12:00 to 14:00 IST | Strictly NO NEW ENTRIES (avoids lunch chop) |
| **Afternoon Entry Window** | 14:00 to 14:25 IST | Post-lunch momentum |
| **Entry Cutoff** | 14:25 IST | Ensures 60m position completes before 15:25 close |
| **Intraday Square-Off** | 15:25 IST | Zero overnight holding invariant |
| **Net-Edge Hurdle** | ≥ ₹0.80 net expected profit | Must clear all statutory taxes, spread, slippage |
| **Available Capital** | ₹5,000.00 | Micro-capital account constraint |
| **Cash Policy** | Cash is valid & intentional | If net edge < ₹0.80, HOLD CASH (0 trades) |

## 4. Verification Check

```bash
# Verify manifest on disk:
type v3/adaptive/ledger\manifests\manifest_20260925.json
```
