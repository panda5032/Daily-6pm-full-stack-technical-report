# 🐋 Unusual Whale Options Activity — AI Portfolio
**Generated**: 2026-09-30 15:14  |  **Stocks scanned**: 167

> **Disclaimer**: This is an algorithmic screen of public options data, not financial advice. Markets are closed weekends — Sunday runs reflect Friday's settled chains. Always do your own due diligence.

## Data Sources
- **Yahoo Finance option chains** (via `yfinance`) — full call/put chains, volume, OI, IV
- **Computed metrics** — Volume/OI ratio, total premium $, put/call ratio, IV vs 30D HV
- **30-day historical volatility** (via `yfinance` price history) — IV cheap/rich benchmark
- *Reference (not pulled live):* UnusualWhales.com, Barchart UOA, Finviz, CBOE volume reports

## Whale-Detection Thresholds
| Filter | Threshold | Meaning |
|--------|-----------|---------|
| Vol / OI ratio | ≥ 2.0 | New positioning vs existing book |
| Contract premium $ | ≥ $500,000 (whale ≥ $2,000,000) | Notional dollar size |
| Min volume | 100 contracts | Filter out illiquid noise |
| DTE window | 3 – 120 days | Skip 0DTE noise + LEAPS |
| P/C bullish | ≤ 0.6 | Calls dominating volume |
| P/C bearish | ≥ 1.2 | Puts dominating volume |

## Summary

| Action | Count |
|--------|-------|
| 🟢🟢 STRONG BUY | 10 |
| 🟢 BUY | 10 |
| 🟡 HOLD | 77 |
| 🔴 SELL | 4 |
| 🔴🔴 STRONG SELL | 1 |
| ⚪ NO OPTIONS | 63 |
| ⚪ NO DATA | 2 |

## 🟢 Top BUY Candidates (Bullish Whale Flow)

| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |
|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|
| 1 | **TSLA** | Self-Driving | $354.89 | $117.27 | $46.75 | 0.43 | +8.5 | 🟢🟢 STRONG BUY | Call premium $117.3M (71% of total) — large bullish flow |
| 2 | **JNJ** | Rotation | $264.79 | $39.88 | $0.37 | 0.30 | +7.5 | 🟢🟢 STRONG BUY | Call premium $39.9M (99% of total) — large bullish flow |
| 3 | **XLU** | Rotation | $39.43 | $5.12 | $0.39 | 0.04 | +7.0 | 🟢🟢 STRONG BUY | Call premium $5.1M (93% of total) — large bullish flow |
| 4 | **GOOGL** | Hyperscaler | $344.13 | $54.46 | $17.18 | 0.26 | +7.0 | 🟢🟢 STRONG BUY | Call premium $54.5M (76% of total) — large bullish flow |
| 5 | **PLTR** | Software | $187.04 | $10.28 | $4.60 | 0.56 | +5.5 | 🟢🟢 STRONG BUY | Call premium $10.28M (69%) — bullish skew |
| 6 | **INTC** | Semis | $120.16 | $4.59 | $0.63 | 0.20 | +4.5 | 🟢🟢 STRONG BUY | Call premium $4.59M (88%) — bullish skew |
| 7 | **MRVL** | Semis | $264.21 | $13.19 | $5.75 | 0.91 | +4.5 | 🟢🟢 STRONG BUY | Call premium $13.19M (70%) — bullish skew |
| 8 | **RIOT** | Crypto | $20.14 | $3.30 | $1.41 | 0.32 | +4.5 | 🟢🟢 STRONG BUY | Call premium $3.30M (70%) — bullish skew |
| 9 | **NOW** | Software | $134.01 | $3.53 | $1.54 | 0.38 | +4.5 | 🟢🟢 STRONG BUY | Call premium $3.53M (70%) — bullish skew |
| 10 | **LRCX** | Semis | $328.61 | $8.18 | $3.46 | 1.13 | +4.0 | 🟢🟢 STRONG BUY | Call premium $8.2M (70% of total) — large bullish flow |
| 11 | **BMNR** | Crypto | $26.43 | $2.39 | $0.75 | 0.54 | +3.5 | 🟢 BUY | Call premium $2.39M (76%) — bullish skew |
| 12 | **MSTR** | Crypto | $153.12 | $28.60 | $17.21 | 0.70 | +3.5 | 🟢 BUY | Notable CALL $170 2026-10-09 $1564K | vol/OI 5.9x |
| 13 | **DELL** | Semis | $538.32 | $16.25 | $7.18 | 0.59 | +3.5 | 🟢 BUY | Call premium $16.25M (69%) — bullish skew |
| 14 | **DDOG** | Software | $273.85 | $5.39 | $0.78 | 0.66 | +3.0 | 🟢 BUY | Call premium $5.4M (87% of total) — large bullish flow |
| 15 | **NFLX** | Software | $69.58 | $1.36 | $0.46 | 0.28 | +2.5 | 🟢 BUY | Call premium $1.36M (75%) — bullish skew |
| 16 | **CSCO** | AI Infrastructure | $107.61 | $2.86 | $0.47 | 0.58 | +2.5 | 🟢 BUY | Call premium $2.86M (86%) — bullish skew |
| 17 | **NKE** | Trading | $35.38 | $1.88 | $1.01 | 0.14 | +2.5 | 🟢 BUY | Call premium $1.88M (65%) — bullish skew |
| 18 | **AMD** | Semis | $611.74 | $64.55 | $23.94 | 0.99 | +2.5 | 🟢 BUY | Call premium $64.5M (73% of total) — large bullish flow |
| 19 | **CIFR** | AI Infrastructure | $15.82 | $0.34 | $0.08 | 0.13 | +2.0 | 🟢 BUY | P/C ratio 0.13 ≤ 0.6 — bullish positioning |
| 20 | **IREN** | AI Infrastructure | $40.86 | $0.87 | $0.90 | 0.59 | +2.0 | 🟢 BUY | P/C ratio 0.59 ≤ 0.6 — bullish positioning |

## 🔴 Top SELL / Avoid (Bearish Whale Flow)

| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |
|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|
| 1 | **CIEN** | AI Infrastructure | $351.93 | $1.15 | $27.13 | 4.51 | -6.0 | 🔴🔴 STRONG SELL | Put premium $27.1M (96% of total) — large bearish flow |
| 2 | **AAPL** | Hyperscaler | $333.01 | $16.58 | $14.89 | 0.60 | -3.5 | 🔴 SELL | Notable PUT $340 2026-10-05 $1138K | vol/OI 6.9x |
| 3 | **AMAT** | Semis | $511.67 | $4.98 | $2.70 | 2.30 | -3.0 | 🔴 SELL | P/C ratio 2.30 ≥ 1.2 — bearish positioning |
| 4 | **LLY** | Health | $1159.25 | $7.78 | $9.18 | 0.68 | -3.0 | 🔴 SELL | Whale PUT $1200 2026-11-06 vol 349 | $2.65M premium | vol/OI... |
| 5 | **APP** | Software | $290.52 | $3.69 | $7.41 | 0.88 | -2.5 | 🔴 SELL | Put premium $7.41M (67%) — bearish skew |

## 🐋 Top 25 Whale Contracts (Highest Premium $)

| # | Ticker | Side | Strike | Expiry | DTE | Vol | OI | Vol/OI | $Premium | Moneyness |
|---|--------|------|--------|--------|-----|-----|----|---------|----------|-----------|
| 1 | **JNJ** | 🟢 CALL | $185 | 2026-10-16 | 16d | 3,637 | 0 | 99.0x | $31.86M | -30.1% |
| 2 | **CIEN** | 🔴 PUT | $600 | 2026-10-16 | 16d | 526 | 0 | 99.0x | $14.54M | +70.5% |
| 3 | **TSLA** | 🟢 CALL | $355 | 2026-10-09 | 9d | 9,061 | 1,435 | 6.3x | $8.25M | +0.0% |
| 4 | **NVDA** | 🟢 CALL | $218 | 2026-10-05 | 5d | 5,546 | 801 | 6.9x | $7.54M | -4.7% |
| 5 | **NVDA** | 🟢 CALL | $220 | 2026-10-05 | 5d | 5,984 | 1,777 | 3.4x | $6.33M | -3.6% |
| 6 | **TSLA** | 🟢 CALL | $350 | 2026-10-09 | 9d | 5,006 | 905 | 5.5x | $6.01M | -1.4% |
| 7 | **TSLA** | 🟢 CALL | $338 | 2026-10-05 | 5d | 3,105 | 3 | 1035.0x | $5.59M | -4.9% |
| 8 | **NVDA** | 🟢 CALL | $215 | 2026-10-05 | 5d | 3,075 | 519 | 5.9x | $4.74M | -5.8% |
| 9 | **NVDA** | 🔴 PUT | $240 | 2026-10-05 | 5d | 4,182 | 801 | 5.2x | $4.07M | +5.1% |
| 10 | **NVDA** | 🟢 CALL | $220 | 2026-10-07 | 7d | 3,739 | 330 | 11.3x | $4.04M | -3.6% |
| 11 | **TSLA** | 🟢 CALL | $365 | 2026-10-09 | 9d | 7,501 | 1,843 | 4.1x | $3.86M | +2.8% |
| 12 | **TSLA** | 🔴 PUT | $350 | 2026-10-09 | 9d | 5,359 | 1,800 | 3.0x | $3.62M | -1.4% |
| 13 | **TSLA** | 🟢 CALL | $352 | 2026-10-09 | 9d | 3,093 | 584 | 5.3x | $3.25M | -0.7% |
| 14 | **TSLA** | 🟢 CALL | $348 | 2026-10-09 | 9d | 2,365 | 156 | 15.2x | $3.19M | -2.1% |
| 15 | **TSLA** | 🟢 CALL | $350 | 2026-10-05 | 5d | 3,422 | 163 | 21.0x | $3.16M | -1.4% |
| 16 | **NVDA** | 🔴 PUT | $230 | 2026-10-07 | 7d | 7,400 | 474 | 15.6x | $2.85M | +0.7% |
| 17 | **TSLA** | 🟢 CALL | $352 | 2026-10-16 | 16d | 2,105 | 479 | 4.4x | $2.82M | -0.7% |
| 18 | **MRVL** | 🟢 CALL | $270 | 2026-10-09 | 9d | 2,771 | 1,129 | 2.5x | $2.77M | +2.2% |
| 19 | **NVDA** | 🔴 PUT | $220 | 2026-10-09 | 9d | 18,938 | 6,433 | 2.9x | $2.75M | -3.6% |
| 20 | **TSLA** | 🟢 CALL | $355 | 2026-10-05 | 5d | 4,154 | 806 | 5.2x | $2.69M | +0.0% |
| 21 | **LLY** | 🔴 PUT | $1200 | 2026-11-06 | 37d | 349 | 3 | 116.3x | $2.65M | +3.5% |
| 22 | **GOOGL** | 🟢 CALL | $300 | 2026-10-09 | 9d | 538 | 86 | 6.3x | $2.64M | -12.8% |
| 23 | **GOOGL** | 🟢 CALL | $305 | 2026-10-16 | 16d | 589 | 248 | 2.4x | $2.63M | -11.4% |
| 24 | **NVDA** | 🟢 CALL | $218 | 2026-10-07 | 7d | 2,160 | 293 | 7.4x | $2.58M | -4.7% |
| 25 | **JNJ** | 🟢 CALL | $180 | 2026-10-16 | 16d | 275 | 0 | 99.0x | $2.55M | -32.0% |

## Detailed Analysis by Sector

### Hyperscaler

**GOOGL** — 🟢🟢 **STRONG BUY** (score: +7.0)  
Spot: $344.13 | Calls: 112,657 vol / $54.46M | Puts: 28,815 vol / $17.18M | P/C: 0.26 | HV30: 24%
- [S1_重仓看涨流] (+3.0) Call premium $54.5M (76% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.26 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $300 2026-10-09 vol 538 | $2.64M premium | vol/OI 6.3x
- [S5_IV昂贵] (-1.0) Avg call IV 69% vs 30D HV 24% (2.9x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $6.00M — speculative upside bets

**MSFT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $512.96 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 22%
- [NO_OPTIONS] (0.0) yfinance: no_options

**META** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $725.29 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**AMZN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $249.03 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 26%
- [NO_OPTIONS] (0.0) yfinance: no_options

**AAPL** — 🔴 **SELL** (score: -3.5)  
Spot: $333.01 | Calls: 56,867 vol / $16.58M | Puts: 34,239 vol / $14.89M | P/C: 0.60 | HV30: 22%
- [S3_看跌白鲸] (-1.0) Notable PUT $340 2026-10-05 $1138K | vol/OI 6.9x
- [S4_看跌密度] (-1.5) 4 unusual put sweeps vs 0 call — concentrated bearish
- [S5_IV昂贵] (-1.0) Avg call IV 60% vs 30D HV 22% (2.7x) — options expensive, sellers favored

### Self-Driving

**TSLA** — 🟢🟢 **STRONG BUY** (score: +8.5)  
Spot: $354.89 | Calls: 200,938 vol / $117.27M | Puts: 85,954 vol / $46.75M | P/C: 0.43 | HV30: 45%
- [S1_重仓看涨流] (+3.0) Call premium $117.3M (71% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.43 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $355 2026-10-09 vol 9,061 | $8.25M premium | vol/OI 6.3x
- [S4_看涨密度] (+1.5) 19 unusual call sweeps vs 9 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 82% vs 30D HV 45% (1.8x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $20.75M — speculative upside bets

**UBER** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $68.51 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 29%
- [NO_OPTIONS] (0.0) yfinance: no_options

**GRAB** — 🟡 **HOLD** (score: +0.0)  
Spot: $3.12 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 45%

**PONY** — 🟡 **HOLD** (score: -1.0)  
Spot: $6.53 | Calls: 1,779 vol / $0.02M | Puts: 176 vol / $0.02M | P/C: 0.10 | HV30: 54%
- [S5_IV昂贵] (-1.0) Avg call IV 128% vs 30D HV 54% (2.4x) — options expensive, sellers favored

### Robotics

**PATH** — 🟡 **HOLD** (score: +1.0)  
Spot: $12.83 | Calls: 6,654 vol / $0.26M | Puts: 1,465 vol / $0.09M | P/C: 0.22 | HV30: 72%
- [S2_PC比偏低] (+2.0) P/C ratio 0.22 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 116% vs 30D HV 72% (1.6x) — options expensive, sellers favored

**SERV** — 🟡 **HOLD** (score: -1.0)  
Spot: $4.66 | Calls: 2,286 vol / $0.03M | Puts: 368 vol / $0.11M | P/C: 0.16 | HV30: 53%
- [S5_IV昂贵] (-1.0) Avg call IV 192% vs 30D HV 53% (3.6x) — options expensive, sellers favored

**ISRG** — 🟡 **HOLD** (score: -1.0)  
Spot: $406.66 | Calls: 901 vol / $1.64M | Puts: 996 vol / $1.19M | P/C: 1.11 | HV30: 31%
- [S5_IV昂贵] (-1.0) Avg call IV 69% vs 30D HV 31% (2.2x) — options expensive, sellers favored

### Semis

**INTC** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $120.16 | Calls: 12,907 vol / $4.59M | Puts: 2,548 vol / $0.63M | P/C: 0.20 | HV30: 67%
- [S1_看涨流] (+1.5) Call premium $4.59M (88%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.20 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $118 2026-10-07 $1820K | vol/OI 20.1x

**MRVL** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $264.21 | Calls: 10,372 vol / $13.19M | Puts: 9,435 vol / $5.75M | P/C: 0.91 | HV30: 70%
- [S1_看涨流] (+1.5) Call premium $13.19M (70%) — bullish skew
- [S3_巨鲸看涨] (+2.0) Whale CALL $270 2026-10-09 vol 2,771 | $2.77M premium | vol/OI 2.5x
- [S6_OTM看涨] (+1.0) OTM call premium $2.77M — speculative upside bets

**LRCX** — 🟢🟢 **STRONG BUY** (score: +4.0)  
Spot: $328.61 | Calls: 5,410 vol / $8.18M | Puts: 6,098 vol / $3.46M | P/C: 1.13 | HV30: 54%
- [S1_重仓看涨流] (+3.0) Call premium $8.2M (70% of total) — large bullish flow
- [S3_看涨白鲸] (+1.0) Notable CALL $325 2026-10-16 $1685K | vol/OI 6.1x

**DELL** — 🟢 **BUY** (score: +3.5)  
Spot: $538.32 | Calls: 6,932 vol / $16.25M | Puts: 4,118 vol / $7.18M | P/C: 0.59 | HV30: 80%
- [S1_看涨流] (+1.5) Call premium $16.25M (69%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.59 ≤ 0.6 — bullish positioning

**AMD** — 🟢 **BUY** (score: +2.5)  
Spot: $611.74 | Calls: 31,720 vol / $64.55M | Puts: 31,257 vol / $23.94M | P/C: 0.99 | HV30: 53%
- [S1_重仓看涨流] (+3.0) Call premium $64.5M (73% of total) — large bullish flow
- [S3_看跌白鲸] (-1.0) Notable PUT $575 2026-10-09 $1109K | vol/OI 5.6x
- [S4_看涨密度] (+1.5) 6 unusual call sweeps vs 2 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 100% vs 30D HV 53% (1.9x) — options expensive, sellers favored

**NVDA** — 🟡 **HOLD** (score: +1.0)  
Spot: $228.29 | Calls: 130,870 vol / $53.97M | Puts: 133,722 vol / $31.06M | P/C: 1.02 | HV30: 39%
- [S3_巨鲸看涨] (+2.0) Whale CALL $218 2026-10-05 vol 5,546 | $7.54M premium | vol/OI 6.9x
- [S5_IV昂贵] (-1.0) Avg call IV 80% vs 30D HV 39% (2.0x) — options expensive, sellers favored

**COHR** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $287.79 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 72%
- [NO_OPTIONS] (0.0) yfinance: no_options

**MU** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $1067.49 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TER** — 🟡 **HOLD** (score: +0.0)  
Spot: $400.91 | Calls: 282 vol / $0.93M | Puts: 316 vol / $0.24M | P/C: 1.12 | HV30: 62%

**TSM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $456.28 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 25%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SKHY** — 🟡 **HOLD** (score: +0.0)  
Spot: $184.02 | Calls: 415 vol / $0.47M | Puts: 791 vol / $0.49M | P/C: 1.91 | HV30: 58%

**TXN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $280.03 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 26%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SMCI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $41.06 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 67%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ARM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $289.76 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 83%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QCOM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $184.06 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**AVGO** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $351.29 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 33%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ANET** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $203.61 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 40%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ASML** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $1811.25 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 37%
- [NO_OPTIONS] (0.0) yfinance: no_options

**MCHP** — 🟡 **HOLD** (score: -1.0)  
Spot: $77.75 | Calls: 583 vol / $0.61M | Puts: 1,400 vol / $0.67M | P/C: 2.40 | HV30: 34%
- [S5_IV昂贵] (-1.0) Avg call IV 72% vs 30D HV 34% (2.1x) — options expensive, sellers favored

**GFS** — 🟡 **HOLD** (score: -1.0)  
Spot: $47.91 | Calls: 473 vol / $0.07M | Puts: 298 vol / $0.50M | P/C: 0.63 | HV30: 44%
- [S5_IV昂贵] (-1.0) Avg call IV 115% vs 30D HV 44% (2.6x) — options expensive, sellers favored

**ADI** — 🟡 **HOLD** (score: -1.0)  
Spot: $396.79 | Calls: 808 vol / $0.72M | Puts: 390 vol / $0.54M | P/C: 0.48 | HV30: 29%
- [S5_IV昂贵] (-1.0) Avg call IV 49% vs 30D HV 29% (1.7x) — options expensive, sellers favored

**KLAC** — 🟡 **HOLD** (score: -1.0)  
Spot: $195.03 | Calls: 1,286 vol / $0.58M | Puts: 593 vol / $0.22M | P/C: 0.46 | HV30: 45%
- [S5_IV昂贵] (-1.0) Avg call IV 68% vs 30D HV 45% (1.5x) — options expensive, sellers favored

**NXPI** — 🟡 **HOLD** (score: -1.0)  
Spot: $237.47 | Calls: 569 vol / $0.94M | Puts: 619 vol / $1.61M | P/C: 1.09 | HV30: 33%
- [S5_IV昂贵] (-1.0) Avg call IV 50% vs 30D HV 33% (1.5x) — options expensive, sellers favored

**AMAT** — 🔴 **SELL** (score: -3.0)  
Spot: $511.67 | Calls: 2,532 vol / $4.98M | Puts: 5,830 vol / $2.70M | P/C: 2.30 | HV30: 46%
- [S2_PC比偏高] (-2.0) P/C ratio 2.30 ≥ 1.2 — bearish positioning
- [S3_看跌白鲸] (-1.0) Notable PUT $395 2026-11-06 $555K | vol/OI 143.8x

### AI Infrastructure

**CSCO** — 🟢 **BUY** (score: +2.5)  
Spot: $107.61 | Calls: 7,864 vol / $2.86M | Puts: 4,523 vol / $0.47M | P/C: 0.58 | HV30: 25%
- [S1_看涨流] (+1.5) Call premium $2.86M (86%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.58 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 53% vs 30D HV 25% (2.1x) — options expensive, sellers favored

**CIFR** — 🟢 **BUY** (score: +2.0)  
Spot: $15.82 | Calls: 6,534 vol / $0.34M | Puts: 838 vol / $0.08M | P/C: 0.13 | HV30: 96%
- [S2_PC比偏低] (+2.0) P/C ratio 0.13 ≤ 0.6 — bullish positioning

**IREN** — 🟢 **BUY** (score: +2.0)  
Spot: $40.86 | Calls: 5,697 vol / $0.87M | Puts: 3,381 vol / $0.90M | P/C: 0.59 | HV30: 74%
- [S2_PC比偏低] (+2.0) P/C ratio 0.59 ≤ 0.6 — bullish positioning

**CRWV** — 🟡 **HOLD** (score: +1.5)  
Spot: $87.10 | Calls: 13,415 vol / $3.96M | Puts: 10,323 vol / $1.86M | P/C: 0.77 | HV30: 62%
- [S1_看涨流] (+1.5) Call premium $3.96M (68%) — bullish skew
- [S3_看涨白鲸] (+1.0) Notable CALL $87 2026-10-16 $729K | vol/OI 2.1x
- [S5_IV昂贵] (-1.0) Avg call IV 95% vs 30D HV 62% (1.5x) — options expensive, sellers favored

**ORCL** — 🟡 **HOLD** (score: +1.0)  
Spot: $137.33 | Calls: 12,562 vol / $3.26M | Puts: 5,937 vol / $4.50M | P/C: 0.47 | HV30: 48%
- [S2_PC比偏低] (+2.0) P/C ratio 0.47 ≤ 0.6 — bullish positioning
- [S3_看跌白鲸] (-1.0) Notable PUT $200 2026-10-09 $1573K | vol/OI 16.7x

**NBIS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $236.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 67%
- [NO_OPTIONS] (0.0) yfinance: no_options

**APLD** — 🟡 **HOLD** (score: +0.0)  
Spot: $24.38 | Calls: 1,389 vol / $0.20M | Puts: 692 vol / $0.09M | P/C: 0.50 | HV30: 74%

**CEG** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $253.97 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 38%
- [NO_OPTIONS] (0.0) yfinance: no_options

**VRT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $241.44 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 57%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PSTG** — ⚪ **NO DATA** (score: +0.0)  
Spot: $0.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 0%
- [NO_PRICE] (0.0) Could not retrieve spot price

**DLR** — 🟡 **HOLD** (score: -1.0)  
Spot: $175.61 | Calls: 207 vol / $0.08M | Puts: 181 vol / $0.09M | P/C: 0.87 | HV30: 26%
- [S5_IV昂贵] (-1.0) Avg call IV 54% vs 30D HV 26% (2.0x) — options expensive, sellers favored

**VST** — 🟡 **HOLD** (score: -1.0)  
Spot: $138.36 | Calls: 2,444 vol / $0.51M | Puts: 1,513 vol / $0.34M | P/C: 0.62 | HV30: 31%
- [S5_IV昂贵] (-1.0) Avg call IV 57% vs 30D HV 31% (1.9x) — options expensive, sellers favored

**ETN** — 🟡 **HOLD** (score: -1.0)  
Spot: $429.61 | Calls: 478 vol / $0.69M | Puts: 900 vol / $0.69M | P/C: 1.88 | HV30: 39%
- [S5_IV昂贵] (-1.0) Avg call IV 67% vs 30D HV 39% (1.7x) — options expensive, sellers favored

**GEV** — 🟡 **HOLD** (score: -2.0)  
Spot: $949.90 | Calls: 1,438 vol / $3.39M | Puts: 2,646 vol / $3.94M | P/C: 1.84 | HV30: 41%
- [S3_看跌白鲸] (-1.0) Notable PUT $850 2026-11-06 $1549K | vol/OI 22.6x
- [S6_OTM看跌] (-1.0) OTM put premium $1.55M — speculative downside bets

**CIEN** — 🔴🔴 **STRONG SELL** (score: -6.0)  
Spot: $351.93 | Calls: 740 vol / $1.15M | Puts: 3,341 vol / $27.13M | P/C: 4.51 | HV30: 64%
- [S1_重仓看跌流] (-3.0) Put premium $27.1M (96% of total) — large bearish flow
- [S3_巨鲸看跌] (-2.0) Whale PUT $600 2026-10-16 vol 526 | $14.54M premium | vol/OI 99.0x
- [S5_IV昂贵] (-1.0) Avg call IV 122% vs 30D HV 64% (1.9x) — options expensive, sellers favored

### Energy

**EOSE** — 🟡 **HOLD** (score: +1.0)  
Spot: $3.07 | Calls: 5,784 vol / $0.10M | Puts: 2,069 vol / $0.07M | P/C: 0.36 | HV30: 106%
- [S2_PC比偏低] (+2.0) P/C ratio 0.36 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 206% vs 30D HV 106% (1.9x) — options expensive, sellers favored

**ONDS** — 🟡 **HOLD** (score: +1.0)  
Spot: $7.32 | Calls: 9,392 vol / $0.16M | Puts: 3,527 vol / $0.24M | P/C: 0.38 | HV30: 61%
- [S2_PC比偏低] (+2.0) P/C ratio 0.38 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 109% vs 30D HV 61% (1.8x) — options expensive, sellers favored

**BE** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $276.96 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 81%
- [NO_OPTIONS] (0.0) yfinance: no_options

**OKLO** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $37.03 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 76%
- [NO_OPTIONS] (0.0) yfinance: no_options

**MP** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $47.29 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 54%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SMR** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $7.90 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 95%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QS** — 🟡 **HOLD** (score: -1.0)  
Spot: $4.64 | Calls: 689 vol / $0.01M | Puts: 221 vol / $0.01M | P/C: 0.32 | HV30: 45%
- [S5_IV昂贵] (-1.0) Avg call IV 136% vs 30D HV 45% (3.0x) — options expensive, sellers favored

**LAC** — 🟡 **HOLD** (score: -1.0)  
Spot: $2.62 | Calls: 463 vol / $0.04M | Puts: 129 vol / $0.00M | P/C: 0.28 | HV30: 46%
- [S5_IV昂贵] (-1.0) Avg call IV 206% vs 30D HV 46% (4.5x) — options expensive, sellers favored

### Software

**PLTR** — 🟢🟢 **STRONG BUY** (score: +5.5)  
Spot: $187.04 | Calls: 22,127 vol / $10.28M | Puts: 12,291 vol / $4.60M | P/C: 0.56 | HV30: 45%
- [S1_看涨流] (+1.5) Call premium $10.28M (69%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.56 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $190 2026-10-09 vol 5,061 | $2.05M premium | vol/OI 2.5x
- [S5_IV昂贵] (-1.0) Avg call IV 83% vs 30D HV 45% (1.8x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $2.05M — speculative upside bets

**NOW** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $134.01 | Calls: 10,492 vol / $3.53M | Puts: 3,977 vol / $1.54M | P/C: 0.38 | HV30: 58%
- [S1_看涨流] (+1.5) Call premium $3.53M (70%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.38 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $134 2026-10-23 $685K | vol/OI 11.0x

**DDOG** — 🟢 **BUY** (score: +3.0)  
Spot: $273.85 | Calls: 2,585 vol / $5.39M | Puts: 1,703 vol / $0.78M | P/C: 0.66 | HV30: 54%
- [S1_重仓看涨流] (+3.0) Call premium $5.4M (87% of total) — large bullish flow

**NFLX** — 🟢 **BUY** (score: +2.5)  
Spot: $69.58 | Calls: 5,720 vol / $1.36M | Puts: 1,594 vol / $0.46M | P/C: 0.28 | HV30: 35%
- [S1_看涨流] (+1.5) Call premium $1.36M (75%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.28 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 57% vs 30D HV 35% (1.6x) — options expensive, sellers favored

**SNPS** — 🟡 **HOLD** (score: +1.5)  
Spot: $435.07 | Calls: 1,926 vol / $3.21M | Puts: 842 vol / $0.67M | P/C: 0.44 | HV30: 57%
- [S1_看涨流] (+1.5) Call premium $3.21M (83%) — bullish skew

**CRDO** — 🟡 **HOLD** (score: +1.5)  
Spot: $194.85 | Calls: 914 vol / $1.60M | Puts: 1,061 vol / $0.85M | P/C: 1.16 | HV30: 90%
- [S1_看涨流] (+1.5) Call premium $1.60M (65%) — bullish skew

**U** — 🟡 **HOLD** (score: +1.0)  
Spot: $40.93 | Calls: 9,998 vol / $0.74M | Puts: 3,063 vol / $0.40M | P/C: 0.31 | HV30: 38%
- [S2_PC比偏低] (+2.0) P/C ratio 0.31 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 70% vs 30D HV 38% (1.8x) — options expensive, sellers favored

**AI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $11.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**MDB** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $348.36 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 88%
- [NO_OPTIONS] (0.0) yfinance: no_options

**RBRK** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $114.51 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 82%
- [NO_OPTIONS] (0.0) yfinance: no_options

**OKTA** — 🟡 **HOLD** (score: +0.0)  
Spot: $209.11 | Calls: 580 vol / $0.71M | Puts: 2,332 vol / $0.30M | P/C: 4.02 | HV30: 101%

**ESTC** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $91.69 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 75%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ALAB** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $355.97 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 84%
- [NO_OPTIONS] (0.0) yfinance: no_options

**INTU** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $275.70 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%
- [NO_OPTIONS] (0.0) yfinance: no_options

**RDDT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $142.43 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 54%
- [NO_OPTIONS] (0.0) yfinance: no_options

**WOLF** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $28.11 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 75%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TEAM** — 🟡 **HOLD** (score: +0.0)  
Spot: $179.17 | Calls: 3 vol / $0.01M | Puts: 6 vol / $0.00M | P/C: 2.00 | HV30: 58%

**GTLB** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $47.27 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 51%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TTD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $12.15 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 40%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SNOW** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $339.73 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 61%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ZETA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $31.58 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 51%
- [NO_OPTIONS] (0.0) yfinance: no_options

**RBLX** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $42.38 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 66%
- [NO_OPTIONS] (0.0) yfinance: no_options

**S** — 🟡 **HOLD** (score: +0.0)  
Spot: $23.77 | Calls: 3,982 vol / $0.19M | Puts: 164 vol / $0.02M | P/C: 0.04 | HV30: 72%

**CFLT** — ⚪ **NO DATA** (score: +0.0)  
Spot: $0.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 0%
- [NO_PRICE] (0.0) Could not retrieve spot price

**IBM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $219.99 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 32%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SOUN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $6.03 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 42%
- [NO_OPTIONS] (0.0) yfinance: no_options

**HUBS** — 🟡 **HOLD** (score: +0.0)  
Spot: $204.86 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 64%

**WDAY** — 🟡 **HOLD** (score: +0.0)  
Spot: $190.45 | Calls: 297 vol / $0.26M | Puts: 137 vol / $0.09M | P/C: 0.46 | HV30: 44%

**SHOP** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $148.43 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 53%
- [NO_OPTIONS] (0.0) yfinance: no_options

**NET** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $347.24 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 67%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TWLO** — 🟡 **HOLD** (score: +0.0)  
Spot: $292.42 | Calls: 844 vol / $1.10M | Puts: 527 vol / $0.80M | P/C: 0.62 | HV30: 57%

**ADBE** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $240.04 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 43%
- [NO_OPTIONS] (0.0) yfinance: no_options

**DUOL** — 🟡 **HOLD** (score: +0.0)  
Spot: $142.40 | Calls: 532 vol / $0.29M | Puts: 484 vol / $0.21M | P/C: 0.91 | HV30: 55%

**CRM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $229.58 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 74%
- [NO_OPTIONS] (0.0) yfinance: no_options

**BBAI** — 🟡 **HOLD** (score: -1.0)  
Spot: $2.65 | Calls: 1,260 vol / $0.01M | Puts: 157 vol / $0.01M | P/C: 0.12 | HV30: 44%
- [S5_IV昂贵] (-1.0) Avg call IV 279% vs 30D HV 44% (6.3x) — options expensive, sellers favored

**INFY** — 🟡 **HOLD** (score: -1.0)  
Spot: $10.73 | Calls: 924 vol / $0.11M | Puts: 378 vol / $0.08M | P/C: 0.41 | HV30: 31%
- [S5_IV昂贵] (-1.0) Avg call IV 100% vs 30D HV 31% (3.3x) — options expensive, sellers favored

**SPOT** — 🟡 **HOLD** (score: -1.0)  
Spot: $487.39 | Calls: 281 vol / $0.76M | Puts: 350 vol / $0.38M | P/C: 1.25 | HV30: 38%
- [S5_IV昂贵] (-1.0) Avg call IV 68% vs 30D HV 38% (1.8x) — options expensive, sellers favored

**UPST** — 🟡 **HOLD** (score: -1.0)  
Spot: $23.00 | Calls: 883 vol / $0.04M | Puts: 1,199 vol / $0.38M | P/C: 1.36 | HV30: 47%
- [S5_IV昂贵] (-1.0) Avg call IV 96% vs 30D HV 47% (2.0x) — options expensive, sellers favored

**APP** — 🔴 **SELL** (score: -2.5)  
Spot: $290.52 | Calls: 6,899 vol / $3.69M | Puts: 6,059 vol / $7.41M | P/C: 0.88 | HV30: 42%
- [S1_看跌流] (-1.5) Put premium $7.41M (67%) — bearish skew
- [S5_IV昂贵] (-1.0) Avg call IV 76% vs 30D HV 42% (1.8x) — options expensive, sellers favored

### Health

**TMDX** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $83.58 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%
- [NO_OPTIONS] (0.0) yfinance: no_options

**HIMS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $29.80 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 74%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CRSP** — 🟡 **HOLD** (score: +0.0)  
Spot: $55.29 | Calls: 157 vol / $0.08M | Puts: 198 vol / $0.09M | P/C: 1.26 | HV30: 62%

**TEM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $81.86 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 108%
- [NO_OPTIONS] (0.0) yfinance: no_options

**RXRX** — 🟡 **HOLD** (score: -1.0)  
Spot: $4.12 | Calls: 3,279 vol / $0.08M | Puts: 176 vol / $0.00M | P/C: 0.05 | HV30: 90%
- [S5_IV昂贵] (-1.0) Avg call IV 160% vs 30D HV 90% (1.8x) — options expensive, sellers favored

**OSCR** — 🟡 **HOLD** (score: -1.0)  
Spot: $30.83 | Calls: 659 vol / $0.09M | Puts: 535 vol / $0.09M | P/C: 0.81 | HV30: 42%
- [S5_IV昂贵] (-1.0) Avg call IV 70% vs 30D HV 42% (1.7x) — options expensive, sellers favored

**UNH** — 🟡 **HOLD** (score: -1.0)  
Spot: $367.31 | Calls: 1,879 vol / $1.86M | Puts: 2,802 vol / $2.61M | P/C: 1.49 | HV30: 20%
- [S5_IV昂贵] (-1.0) Avg call IV 63% vs 30D HV 20% (3.2x) — options expensive, sellers favored

**LLY** — 🔴 **SELL** (score: -3.0)  
Spot: $1159.25 | Calls: 3,842 vol / $7.78M | Puts: 2,602 vol / $9.18M | P/C: 0.68 | HV30: 25%
- [S3_巨鲸看跌] (-2.0) Whale PUT $1200 2026-11-06 vol 349 | $2.65M premium | vol/OI 116.3x
- [S5_IV昂贵] (-1.0) Avg call IV 64% vs 30D HV 25% (2.5x) — options expensive, sellers favored

### Space

**RKLB** — 🟡 **HOLD** (score: +1.0)  
Spot: $69.69 | Calls: 14,863 vol / $2.31M | Puts: 5,226 vol / $1.57M | P/C: 0.35 | HV30: 53%
- [S2_PC比偏低] (+2.0) P/C ratio 0.35 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 83% vs 30D HV 53% (1.6x) — options expensive, sellers favored

**JOBY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $6.05 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 35%
- [NO_OPTIONS] (0.0) yfinance: no_options

**FLY** — 🟡 **HOLD** (score: +0.0)  
Spot: $23.14 | Calls: 759 vol / $0.12M | Puts: 486 vol / $0.07M | P/C: 0.64 | HV30: 0%

**ACHR** — 🟡 **HOLD** (score: -1.0)  
Spot: $4.97 | Calls: 3,407 vol / $0.05M | Puts: 2,119 vol / $0.07M | P/C: 0.62 | HV30: 48%
- [S5_IV昂贵] (-1.0) Avg call IV 151% vs 30D HV 48% (3.1x) — options expensive, sellers favored

**ASTS** — 🟡 **HOLD** (score: -1.0)  
Spot: $58.86 | Calls: 4,286 vol / $1.13M | Puts: 4,240 vol / $1.93M | P/C: 0.99 | HV30: 72%
- [S3_看跌白鲸] (-1.0) Notable PUT $59 2026-10-30 $511K | vol/OI 13.8x

**LUNR** — 🟡 **HOLD** (score: -1.0)  
Spot: $14.24 | Calls: 4,652 vol / $0.06M | Puts: 525 vol / $0.09M | P/C: 0.11 | HV30: 69%
- [S5_IV昂贵] (-1.0) Avg call IV 111% vs 30D HV 69% (1.6x) — options expensive, sellers favored

### China

**NIO** — 🟡 **HOLD** (score: +1.0)  
Spot: $3.43 | Calls: 5,742 vol / $0.08M | Puts: 1,245 vol / $0.03M | P/C: 0.22 | HV30: 36%
- [S2_PC比偏低] (+2.0) P/C ratio 0.22 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 203% vs 30D HV 36% (5.7x) — options expensive, sellers favored

**TCEHY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $54.25 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 28%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PDD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $77.94 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 23%
- [NO_OPTIONS] (0.0) yfinance: no_options

**FUTU** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $110.55 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 51%
- [NO_OPTIONS] (0.0) yfinance: no_options

**XPEV** — 🟡 **HOLD** (score: +0.0)  
Spot: $9.56 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%

**BABA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $107.56 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 38%
- [NO_OPTIONS] (0.0) yfinance: no_options

**BIDU** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $86.90 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 34%
- [NO_OPTIONS] (0.0) yfinance: no_options

**JD** — 🟡 **HOLD** (score: -1.0)  
Spot: $26.60 | Calls: 1,299 vol / $0.09M | Puts: 713 vol / $0.09M | P/C: 0.55 | HV30: 18%
- [S5_IV昂贵] (-1.0) Avg call IV 48% vs 30D HV 18% (2.6x) — options expensive, sellers favored

### Crypto

**RIOT** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $20.14 | Calls: 37,753 vol / $3.30M | Puts: 12,263 vol / $1.41M | P/C: 0.32 | HV30: 85%
- [S1_看涨流] (+1.5) Call premium $3.30M (70%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.32 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $22 2026-10-30 $1747K | vol/OI 361.8x
- [S5_IV昂贵] (-1.0) Avg call IV 135% vs 30D HV 85% (1.6x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $1.75M — speculative upside bets

**BMNR** — 🟢 **BUY** (score: +3.5)  
Spot: $26.43 | Calls: 21,616 vol / $2.39M | Puts: 11,687 vol / $0.75M | P/C: 0.54 | HV30: 89%
- [S1_看涨流] (+1.5) Call premium $2.39M (76%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.54 ≤ 0.6 — bullish positioning

**MSTR** — 🟢 **BUY** (score: +3.5)  
Spot: $153.12 | Calls: 59,809 vol / $28.60M | Puts: 42,113 vol / $17.21M | P/C: 0.70 | HV30: 103%
- [S3_看涨白鲸] (+1.0) Notable CALL $170 2026-10-09 $1564K | vol/OI 5.9x
- [S4_看涨密度] (+1.5) 4 unusual call sweeps vs 0 put — concentrated bullish
- [S6_OTM看涨] (+1.0) OTM call premium $2.16M — speculative upside bets

**BULL** — 🟡 **HOLD** (score: +1.0)  
Spot: $6.97 | Calls: 5,263 vol / $0.15M | Puts: 3,121 vol / $0.14M | P/C: 0.59 | HV30: 74%
- [S2_PC比偏低] (+2.0) P/C ratio 0.59 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 137% vs 30D HV 74% (1.9x) — options expensive, sellers favored

**IBIT** — 🟡 **HOLD** (score: +0.0)  
Spot: $47.33 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%

**XRPC** — 🟡 **HOLD** (score: +0.0)  
Spot: $15.78 | Calls: 11 vol / $0.00M | Puts: 33 vol / $0.00M | P/C: 3.00 | HV30: 97%

**BSOL** — 🟡 **HOLD** (score: +0.0)  
Spot: $16.13 | Calls: 152 vol / $0.02M | Puts: 140 vol / $0.01M | P/C: 0.92 | HV30: 75%

**COIN** — 🟡 **HOLD** (score: +0.0)  
Spot: $186.34 | Calls: 1,033 vol / $0.75M | Puts: 1,257 vol / $0.98M | P/C: 1.22 | HV30: 88%

**CLSK** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $12.88 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 80%
- [NO_OPTIONS] (0.0) yfinance: no_options

**HUT** — 🟡 **HOLD** (score: +0.0)  
Spot: $86.08 | Calls: 5,568 vol / $2.05M | Puts: 4,105 vol / $2.23M | P/C: 0.74 | HV30: 88%

**ETHA** — 🟡 **HOLD** (score: +0.0)  
Spot: $20.11 | Calls: 2,901 vol / $0.36M | Puts: 1,230 vol / $0.06M | P/C: 0.42 | HV30: 57%

**MARA** — 🟡 **HOLD** (score: +0.0)  
Spot: $11.31 | Calls: 26,634 vol / $0.76M | Puts: 17,329 vol / $1.17M | P/C: 0.65 | HV30: 93%

**HIVE** — 🟡 **HOLD** (score: -1.0)  
Spot: $2.95 | Calls: 201 vol / $0.04M | Puts: 12 vol / $0.00M | P/C: 0.06 | HV30: 82%
- [S5_IV昂贵] (-1.0) Avg call IV 262% vs 30D HV 82% (3.2x) — options expensive, sellers favored

**SBET** — 🟡 **HOLD** (score: -1.0)  
Spot: $9.27 | Calls: 1,111 vol / $0.09M | Puts: 1,021 vol / $0.04M | P/C: 0.92 | HV30: 88%
- [S5_IV昂贵] (-1.0) Avg call IV 138% vs 30D HV 88% (1.6x) — options expensive, sellers favored

### Finance

**HOOD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $112.52 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 84%
- [NO_OPTIONS] (0.0) yfinance: no_options

**LMND** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $45.15 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PYPL** — 🟡 **HOLD** (score: +0.0)  
Spot: $52.52 | Calls: 2,458 vol / $0.19M | Puts: 2,052 vol / $0.30M | P/C: 0.83 | HV30: 48%

**AFRM** — 🟡 **HOLD** (score: +0.0)  
Spot: $69.23 | Calls: 1,573 vol / $0.38M | Puts: 528 vol / $0.12M | P/C: 0.34 | HV30: 52%

**SOFI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $15.72 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 0%
- [NO_OPTIONS] (0.0) yfinance: no_options

**OPEN** — 🟡 **HOLD** (score: -1.0)  
Spot: $2.37 | Calls: 678 vol / $0.01M | Puts: 662 vol / $0.02M | P/C: 0.98 | HV30: 53%
- [S5_IV昂贵] (-1.0) Avg call IV 120% vs 30D HV 53% (2.2x) — options expensive, sellers favored

### Quantum

**RGTI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $15.73 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 67%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QUBT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $8.45 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 55%
- [NO_OPTIONS] (0.0) yfinance: no_options

**IONQ** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $43.87 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 69%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QBTS** — 🟡 **HOLD** (score: -1.0)  
Spot: $16.56 | Calls: 2,515 vol / $0.21M | Puts: 1,008 vol / $0.24M | P/C: 0.40 | HV30: 67%
- [S5_IV昂贵] (-1.0) Avg call IV 124% vs 30D HV 67% (1.8x) — options expensive, sellers favored

### Trading

**NKE** — 🟢 **BUY** (score: +2.5)  
Spot: $35.38 | Calls: 35,842 vol / $1.88M | Puts: 5,056 vol / $1.01M | P/C: 0.14 | HV30: 25%
- [S1_看涨流] (+1.5) Call premium $1.88M (65%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.14 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 74% vs 30D HV 25% (2.9x) — options expensive, sellers favored

**CMG** — 🟡 **HOLD** (score: +1.0)  
Spot: $31.94 | Calls: 12,464 vol / $0.74M | Puts: 1,577 vol / $0.21M | P/C: 0.13 | HV30: 36%
- [S2_PC比偏低] (+2.0) P/C ratio 0.13 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 57% vs 30D HV 36% (1.6x) — options expensive, sellers favored

**PTON** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $4.98 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 42%
- [NO_OPTIONS] (0.0) yfinance: no_options

**GME** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $24.65 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 39%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ABNB** — 🟡 **HOLD** (score: +0.0)  
Spot: $160.66 | Calls: 381 vol / $0.08M | Puts: 408 vol / $0.14M | P/C: 1.07 | HV30: 36%

**LULU** — 🟡 **HOLD** (score: +0.0)  
Spot: $96.18 | Calls: 1,352 vol / $0.21M | Puts: 890 vol / $0.38M | P/C: 0.66 | HV30: 64%

**BA** — 🟡 **HOLD** (score: -1.0)  
Spot: $186.09 | Calls: 2,957 vol / $0.84M | Puts: 979 vol / $1.34M | P/C: 0.33 | HV30: 30%
- [S5_IV昂贵] (-1.0) Avg call IV 51% vs 30D HV 30% (1.7x) — options expensive, sellers favored

**UPS** — 🟡 **HOLD** (score: -1.0)  
Spot: $93.43 | Calls: 2,557 vol / $0.31M | Puts: 887 vol / $0.51M | P/C: 0.35 | HV30: 26%
- [S5_IV昂贵] (-1.0) Avg call IV 43% vs 30D HV 26% (1.7x) — options expensive, sellers favored

### Rotation

**JNJ** — 🟢🟢 **STRONG BUY** (score: +7.5)  
Spot: $264.79 | Calls: 7,123 vol / $39.88M | Puts: 2,153 vol / $0.37M | P/C: 0.30 | HV30: 17%
- [S1_重仓看涨流] (+3.0) Call premium $39.9M (99% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.30 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $185 2026-10-16 vol 3,637 | $31.86M premium | vol/OI 99.0x
- [S4_看涨密度] (+1.5) 4 unusual call sweeps vs 0 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 46% vs 30D HV 17% (2.7x) — options expensive, sellers favored

**XLU** — 🟢🟢 **STRONG BUY** (score: +7.0)  
Spot: $39.43 | Calls: 121,123 vol / $5.12M | Puts: 5,186 vol / $0.39M | P/C: 0.04 | HV30: 15%
- [S1_重仓看涨流] (+3.0) Call premium $5.1M (93% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.04 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $41 2026-10-30 vol 55,981 | $2.52M premium | vol/OI 19.0x
- [S5_IV昂贵] (-1.0) Avg call IV 34% vs 30D HV 15% (2.3x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $3.21M — speculative upside bets

**DE** — 🟡 **HOLD** (score: +1.5)  
Spot: $671.36 | Calls: 623 vol / $1.04M | Puts: 346 vol / $0.39M | P/C: 0.56 | HV30: 35%
- [S1_看涨流] (+1.5) Call premium $1.04M (73%) — bullish skew

**JPM** — 🟡 **HOLD** (score: +1.0)  
Spot: $330.88 | Calls: 14,729 vol / $4.50M | Puts: 8,066 vol / $3.67M | P/C: 0.55 | HV30: 18%
- [S2_PC比偏低] (+2.0) P/C ratio 0.55 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 48% vs 30D HV 18% (2.7x) — options expensive, sellers favored

**WMT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $103.93 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 34%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CVX** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $204.39 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 21%
- [NO_OPTIONS] (0.0) yfinance: no_options

**XOM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $162.87 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 24%
- [NO_OPTIONS] (0.0) yfinance: no_options

**GS** — 🟡 **HOLD** (score: -1.0)  
Spot: $901.45 | Calls: 3,363 vol / $4.08M | Puts: 3,743 vol / $7.53M | P/C: 1.11 | HV30: 28%
- [S5_IV昂贵] (-1.0) Avg call IV 54% vs 30D HV 28% (1.9x) — options expensive, sellers favored

**CAT** — 🟡 **HOLD** (score: -1.0)  
Spot: $810.95 | Calls: 1,539 vol / $5.56M | Puts: 1,628 vol / $3.46M | P/C: 1.06 | HV30: 25%
- [S5_IV昂贵] (-1.0) Avg call IV 55% vs 30D HV 25% (2.2x) — options expensive, sellers favored

**COST** — 🟡 **HOLD** (score: -1.0)  
Spot: $910.52 | Calls: 3,421 vol / $2.42M | Puts: 3,667 vol / $1.86M | P/C: 1.07 | HV30: 20%
- [S5_IV昂贵] (-1.0) Avg call IV 38% vs 30D HV 20% (1.9x) — options expensive, sellers favored

**BRK-B** — 🟡 **HOLD** (score: -1.0)  
Spot: $498.12 | Calls: 208 vol / $0.06M | Puts: 373 vol / $0.13M | P/C: 1.79 | HV30: 11%
- [S5_IV昂贵] (-1.0) Avg call IV 19% vs 30D HV 11% (1.7x) — options expensive, sellers favored

**GE** — 🟡 **HOLD** (score: -1.0)  
Spot: $312.36 | Calls: 1,882 vol / $0.43M | Puts: 599 vol / $0.78M | P/C: 0.32 | HV30: 30%
- [S5_IV昂贵] (-1.0) Avg call IV 61% vs 30D HV 30% (2.1x) — options expensive, sellers favored

### Commodity

**GLD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $380.92 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 27%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SLV** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $54.51 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%
- [NO_OPTIONS] (0.0) yfinance: no_options

**USO** — 🟡 **HOLD** (score: -1.0)  
Spot: $145.67 | Calls: 10,478 vol / $2.08M | Puts: 9,332 vol / $2.37M | P/C: 0.89 | HV30: 44%
- [S5_IV昂贵] (-1.0) Avg call IV 72% vs 30D HV 44% (1.6x) — options expensive, sellers favored

---
## Scoring Methodology

| Score Range | Action | Meaning |
|-------------|--------|---------|
| ≥ +4 | STRONG BUY | Multiple bullish whale signals aligned |
| +2 to +4 | BUY | Net bullish options flow |
| -2 to +2 | HOLD | Mixed or neutral options flow |
| -4 to -2 | SELL | Net bearish options flow |
| < -4 | STRONG SELL | Multiple bearish whale signals aligned |

### The 6 Whale Signals
1. **S1 Premium $ flow** — Total call vs put dollar volume (>$5M one-sided = strong)
2. **S2 P/C ratio** — Volume-weighted put/call ratio (≤0.6 bullish, ≥1.2 bearish)
3. **S3 Largest whale** — Single biggest unusual contract (≥$2M = big whale)
4. **S4 Whale density** — Count of unusual call vs put sweeps
5. **S5 IV vs HV** — Implied vol vs 30D realized vol (rich = sellers favored)
6. **S6 OTM skew** — Out-of-money speculative call vs put premium

### Why these signals work
- **Vol/OI > 2** flags new positioning, not closing of existing OI.
- **Premium $** weighs by dollar size — $500K of OTM puts ≠ $500K of ATM calls.
- **P/C ratio** smoothes out individual contract noise across the whole chain.
- **IV vs HV** distinguishes real conviction (cheap IV bought aggressively) from
  pre-event hedging (rich IV pumped by event uncertainty).
