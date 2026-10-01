# 🐋 Unusual Whale Options Activity — AI Portfolio
**Generated**: 2026-09-29 15:14  |  **Stocks scanned**: 167

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
| 🟢🟢 STRONG BUY | 12 |
| 🟢 BUY | 18 |
| 🟡 HOLD | 78 |
| 🔴 SELL | 7 |
| 🔴🔴 STRONG SELL | 3 |
| ⚪ NO OPTIONS | 47 |
| ⚪ NO DATA | 2 |

## 🟢 Top BUY Candidates (Bullish Whale Flow)

| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |
|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|
| 1 | **META** | Hyperscaler | $739.02 | $322.51 | $49.20 | 0.42 | +8.5 | 🟢🟢 STRONG BUY | Call premium $322.5M (87% of total) — large bullish flow |
| 2 | **HOOD** | Finance | $116.24 | $15.20 | $7.01 | 0.53 | +7.0 | 🟢🟢 STRONG BUY | Call premium $15.20M (68%) — bullish skew |
| 3 | **MU** | Semis | $1065.40 | $525.11 | $222.45 | 0.59 | +7.0 | 🟢🟢 STRONG BUY | Call premium $525.1M (70% of total) — large bullish flow |
| 4 | **WMT** | Rotation | $106.83 | $7.42 | $2.24 | 0.36 | +6.5 | 🟢🟢 STRONG BUY | Call premium $7.4M (77% of total) — large bullish flow |
| 5 | **NBIS** | AI Infrastructure | $237.27 | $26.92 | $16.10 | 0.52 | +5.5 | 🟢🟢 STRONG BUY | P/C ratio 0.52 ≤ 0.6 — bullish positioning |
| 6 | **IBIT** | Crypto | $47.33 | $5.67 | $2.04 | 0.42 | +5.0 | 🟢🟢 STRONG BUY | Call premium $5.7M (74% of total) — large bullish flow |
| 7 | **AMAT** | Semis | $512.15 | $7.98 | $1.53 | 0.78 | +5.0 | 🟢🟢 STRONG BUY | Call premium $8.0M (84% of total) — large bullish flow |
| 8 | **MSTR** | Crypto | $154.72 | $49.59 | $33.81 | 0.60 | +4.5 | 🟢🟢 STRONG BUY | Whale CALL $162 2026-10-23 vol 5,665 | $4.08M premium | vol/... |
| 9 | **MDB** | Software | $336.91 | $11.23 | $10.07 | 0.53 | +4.5 | 🟢🟢 STRONG BUY | P/C ratio 0.53 ≤ 0.6 — bullish positioning |
| 10 | **AMZN** | Hyperscaler | $246.70 | $45.64 | $31.08 | 0.37 | +4.0 | 🟢🟢 STRONG BUY | P/C ratio 0.37 ≤ 0.6 — bullish positioning |
| 11 | **GOOGL** | Hyperscaler | $340.94 | $9.40 | $2.87 | 0.48 | +4.0 | 🟢🟢 STRONG BUY | Call premium $9.4M (77% of total) — large bullish flow |
| 12 | **GME** | Trading | $23.75 | $6.79 | $1.05 | 0.20 | +4.0 | 🟢🟢 STRONG BUY | Call premium $6.8M (87% of total) — large bullish flow |
| 13 | **NET** | Software | $352.05 | $3.48 | $0.87 | 0.51 | +3.5 | 🟢 BUY | Call premium $3.48M (80%) — bullish skew |
| 14 | **BMNR** | Crypto | $26.74 | $2.18 | $0.61 | 0.34 | +3.5 | 🟢 BUY | Call premium $2.18M (78%) — bullish skew |
| 15 | **CRWV** | AI Infrastructure | $85.91 | $12.78 | $7.74 | 0.39 | +3.0 | 🟢 BUY | P/C ratio 0.39 ≤ 0.6 — bullish positioning |
| 16 | **AVGO** | Semis | $355.18 | $22.77 | $21.55 | 0.46 | +3.0 | 🟢 BUY | P/C ratio 0.46 ≤ 0.6 — bullish positioning |
| 17 | **DE** | Rotation | $680.46 | $5.03 | $1.37 | 1.69 | +3.0 | 🟢 BUY | Call premium $5.0M (79% of total) — large bullish flow |
| 18 | **COHR** | Semis | $292.22 | $5.63 | $6.84 | 0.47 | +3.0 | 🟢 BUY | P/C ratio 0.47 ≤ 0.6 — bullish positioning |
| 19 | **CRDO** | Software | $192.34 | $3.90 | $2.25 | 0.58 | +3.0 | 🟢 BUY | P/C ratio 0.58 ≤ 0.6 — bullish positioning |
| 20 | **UBER** | Self-Driving | $69.39 | $4.34 | $1.95 | 0.50 | +2.5 | 🟢 BUY | Call premium $4.34M (69%) — bullish skew |

## 🔴 Top SELL / Avoid (Bearish Whale Flow)

| Rank | Ticker | Sector | Spot | Call $M | Put $M | P/C | Score | Action | Top Whale Signal |
|------|--------|--------|------|---------|--------|-----|-------|--------|------------------|
| 1 | **BA** | Trading | $187.76 | $3.94 | $9.74 | 0.79 | -5.0 | 🔴🔴 STRONG SELL | Put premium $9.7M (71% of total) — large bearish flow |
| 2 | **VRT** | AI Infrastructure | $248.43 | $3.34 | $10.92 | 1.27 | -5.0 | 🔴🔴 STRONG SELL | Put premium $10.9M (77% of total) — large bearish flow |
| 3 | **CIEN** | AI Infrastructure | $354.90 | $2.83 | $27.99 | 1.75 | -5.0 | 🔴🔴 STRONG SELL | Put premium $28.0M (91% of total) — large bearish flow |
| 4 | **RDDT** | Software | $145.35 | $1.71 | $3.42 | 1.01 | -3.5 | 🔴 SELL | Put premium $3.42M (67%) — bearish skew |
| 5 | **SPOT** | Software | $493.30 | $0.63 | $2.29 | 2.71 | -3.5 | 🔴 SELL | Put premium $2.29M (78%) — bearish skew |
| 6 | **PDD** | China | $77.52 | $0.12 | $0.99 | 2.04 | -3.0 | 🔴 SELL | P/C ratio 2.04 ≥ 1.2 — bearish positioning |
| 7 | **GRAB** | Self-Driving | $3.13 | $0.12 | $0.30 | 1.33 | -3.0 | 🔴 SELL | P/C ratio 1.33 ≥ 1.2 — bearish positioning |
| 8 | **INTU** | Software | $268.06 | $1.00 | $3.50 | 0.65 | -2.5 | 🔴 SELL | Put premium $3.50M (78%) — bearish skew |
| 9 | **GS** | Rotation | $916.37 | $4.10 | $7.70 | 1.28 | -2.5 | 🔴 SELL | Put premium $7.70M (65%) — bearish skew |
| 10 | **BIDU** | China | $86.73 | $0.77 | $3.56 | 0.36 | -2.5 | 🔴 SELL | Put premium $3.56M (82%) — bearish skew |

## 🐋 Top 25 Whale Contracts (Highest Premium $)

| # | Ticker | Side | Strike | Expiry | DTE | Vol | OI | Vol/OI | $Premium | Moneyness |
|---|--------|------|--------|--------|-----|-----|----|---------|----------|-----------|
| 1 | **MU** | 🟢 CALL | $1150 | 2026-10-16 | 17d | 12,723 | 3,839 | 3.3x | $39.00M | +7.9% |
| 2 | **MU** | 🟢 CALL | $1070 | 2026-10-02 | 3d | 7,482 | 1,065 | 7.0x | $28.85M | +0.4% |
| 3 | **MU** | 🟢 CALL | $1065 | 2026-10-02 | 3d | 4,829 | 699 | 6.9x | $19.71M | -0.0% |
| 4 | **MU** | 🟢 CALL | $200 | 2026-10-02 | 3d | 222 | 11 | 20.2x | $19.55M | -81.2% |
| 5 | **MU** | 🔴 PUT | $1070 | 2026-10-02 | 3d | 4,401 | 1,108 | 4.0x | $18.80M | +0.4% |
| 6 | **MU** | 🟢 CALL | $1300 | 2026-10-16 | 17d | 19,703 | 9,013 | 2.2x | $16.98M | +22.0% |
| 7 | **MU** | 🟢 CALL | $1080 | 2026-10-02 | 3d | 4,595 | 2,105 | 2.2x | $15.90M | +1.4% |
| 8 | **CIEN** | 🔴 PUT | $600 | 2026-10-16 | 17d | 526 | 0 | 99.0x | $14.54M | +69.1% |
| 9 | **MU** | 🟢 CALL | $1075 | 2026-10-02 | 3d | 3,838 | 1,124 | 3.4x | $14.04M | +0.9% |
| 10 | **META** | 🟢 CALL | $750 | 2026-10-02 | 3d | 16,687 | 4,659 | 3.6x | $13.52M | +1.5% |
| 11 | **META** | 🟢 CALL | $730 | 2026-10-02 | 3d | 7,021 | 1,273 | 5.5x | $12.53M | -1.2% |
| 12 | **META** | 🟢 CALL | $725 | 2026-10-02 | 3d | 5,877 | 1,539 | 3.8x | $12.47M | -1.9% |
| 13 | **MU** | 🔴 PUT | $1080 | 2026-10-02 | 3d | 2,404 | 813 | 3.0x | $11.80M | +1.4% |
| 14 | **MU** | 🔴 PUT | $1065 | 2026-10-02 | 3d | 2,269 | 251 | 9.0x | $9.13M | -0.0% |
| 15 | **VRT** | 🔴 PUT | $330 | 2026-10-16 | 17d | 992 | 8 | 124.0x | $8.39M | +32.8% |
| 16 | **MU** | 🟢 CALL | $1072 | 2026-10-02 | 3d | 2,235 | 211 | 10.6x | $8.28M | +0.7% |
| 17 | **MU** | 🔴 PUT | $1072 | 2026-10-02 | 3d | 1,700 | 49 | 34.7x | $7.46M | +0.7% |
| 18 | **BE** | 🟢 CALL | $300 | 2026-10-02 | 3d | 11,753 | 3,991 | 2.9x | $7.29M | +3.0% |
| 19 | **MU** | 🔴 PUT | $1075 | 2026-10-02 | 3d | 1,456 | 402 | 3.6x | $6.70M | +0.9% |
| 20 | **MU** | 🟢 CALL | $1068 | 2026-10-02 | 3d | 1,685 | 214 | 7.9x | $6.70M | +0.2% |
| 21 | **META** | 🟢 CALL | $725 | 2026-10-05 | 6d | 2,899 | 144 | 20.1x | $6.65M | -1.9% |
| 22 | **META** | 🟢 CALL | $722 | 2026-10-02 | 3d | 2,914 | 337 | 8.6x | $6.50M | -2.2% |
| 23 | **BE** | 🔴 PUT | $290 | 2026-10-02 | 3d | 6,446 | 1,622 | 4.0x | $5.80M | -0.4% |
| 24 | **MU** | 🟢 CALL | $1095 | 2026-10-02 | 3d | 1,897 | 680 | 2.8x | $5.50M | +2.8% |
| 25 | **MU** | 🔴 PUT | $1068 | 2026-10-02 | 3d | 1,297 | 51 | 25.4x | $5.38M | +0.2% |

## Detailed Analysis by Sector

### Hyperscaler

**META** — 🟢🟢 **STRONG BUY** (score: +8.5)  
Spot: $739.02 | Calls: 209,721 vol / $322.51M | Puts: 88,535 vol / $49.20M | P/C: 0.42 | HV30: 49%
- [S1_重仓看涨流] (+3.0) Call premium $322.5M (87% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.42 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $750 2026-10-02 vol 16,687 | $13.52M premium | vol/OI 3.6x
- [S4_看涨密度] (+1.5) 24 unusual call sweeps vs 4 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 86% vs 30D HV 49% (1.7x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $24.87M — speculative upside bets

**AMZN** — 🟢🟢 **STRONG BUY** (score: +4.0)  
Spot: $246.70 | Calls: 124,512 vol / $45.64M | Puts: 46,486 vol / $31.08M | P/C: 0.37 | HV30: 35%
- [S2_PC比偏低] (+2.0) P/C ratio 0.37 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $225 2026-10-02 vol 2,372 | $5.33M premium | vol/OI 6.9x
- [S5_IV昂贵] (-1.0) Avg call IV 69% vs 30D HV 35% (2.0x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $2.34M — speculative upside bets

**GOOGL** — 🟢🟢 **STRONG BUY** (score: +4.0)  
Spot: $340.94 | Calls: 50,750 vol / $9.40M | Puts: 24,442 vol / $2.87M | P/C: 0.48 | HV30: 23%
- [S1_重仓看涨流] (+3.0) Call premium $9.4M (77% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.48 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 97% vs 30D HV 23% (4.2x) — options expensive, sellers favored

**MSFT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $509.04 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 22%
- [NO_OPTIONS] (0.0) yfinance: no_options

**AAPL** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $329.59 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 23%
- [NO_OPTIONS] (0.0) yfinance: no_options

### Self-Driving

**UBER** — 🟢 **BUY** (score: +2.5)  
Spot: $69.39 | Calls: 40,568 vol / $4.34M | Puts: 20,090 vol / $1.95M | P/C: 0.50 | HV30: 29%
- [S1_看涨流] (+1.5) Call premium $4.34M (69%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.50 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 62% vs 30D HV 29% (2.1x) — options expensive, sellers favored

**TSLA** — 🟡 **HOLD** (score: -0.5)  
Spot: $352.90 | Calls: 34,990 vol / $19.10M | Puts: 35,925 vol / $11.50M | P/C: 1.03 | HV30: 45%
- [S3_巨鲸看跌] (-2.0) Whale PUT $355 2026-10-09 vol 3,970 | $3.99M premium | vol/OI 4.1x
- [S4_看涨密度] (+1.5) 7 unusual call sweeps vs 2 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 76% vs 30D HV 45% (1.7x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $8.02M — speculative upside bets

**PONY** — 🟡 **HOLD** (score: -1.0)  
Spot: $6.53 | Calls: 691 vol / $0.02M | Puts: 391 vol / $0.02M | P/C: 0.57 | HV30: 55%
- [S5_IV昂贵] (-1.0) Avg call IV 174% vs 30D HV 55% (3.2x) — options expensive, sellers favored

**GRAB** — 🔴 **SELL** (score: -3.0)  
Spot: $3.13 | Calls: 6,369 vol / $0.12M | Puts: 8,443 vol / $0.30M | P/C: 1.33 | HV30: 46%
- [S2_PC比偏高] (-2.0) P/C ratio 1.33 ≥ 1.2 — bearish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 253% vs 30D HV 46% (5.5x) — options expensive, sellers favored

### Robotics

**SERV** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $4.66 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 57%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PATH** — 🟡 **HOLD** (score: -1.0)  
Spot: $12.34 | Calls: 2,870 vol / $0.23M | Puts: 2,216 vol / $0.18M | P/C: 0.77 | HV30: 70%
- [S5_IV昂贵] (-1.0) Avg call IV 139% vs 30D HV 70% (2.0x) — options expensive, sellers favored

**ISRG** — 🟡 **HOLD** (score: -2.0)  
Spot: $412.25 | Calls: 1,518 vol / $2.47M | Puts: 2,868 vol / $2.42M | P/C: 1.89 | HV30: 31%
- [S3_看跌白鲸] (-1.0) Notable PUT $415 2026-10-23 $918K | vol/OI 12.9x
- [S5_IV昂贵] (-1.0) Avg call IV 62% vs 30D HV 31% (2.0x) — options expensive, sellers favored

### Semis

**MU** — 🟢🟢 **STRONG BUY** (score: +7.0)  
Spot: $1065.40 | Calls: 194,178 vol / $525.11M | Puts: 114,755 vol / $222.45M | P/C: 0.59 | HV30: 52%
- [S1_重仓看涨流] (+3.0) Call premium $525.1M (70% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.59 ≤ 0.6 — bullish positioning
- [S3_巨鲸看涨] (+2.0) Whale CALL $1150 2026-10-16 vol 12,723 | $39.00M premium | vol/OI 3.3x
- [S5_IV昂贵] (-1.0) Avg call IV 118% vs 30D HV 52% (2.2x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $152.62M — speculative upside bets

**AMAT** — 🟢🟢 **STRONG BUY** (score: +5.0)  
Spot: $512.15 | Calls: 2,556 vol / $7.98M | Puts: 1,992 vol / $1.53M | P/C: 0.78 | HV30: 48%
- [S1_重仓看涨流] (+3.0) Call premium $8.0M (84% of total) — large bullish flow
- [S3_巨鲸看涨] (+2.0) Whale CALL $400 2026-11-06 vol 350 | $2.87M premium | vol/OI 2.0x

**AVGO** — 🟢 **BUY** (score: +3.0)  
Spot: $355.18 | Calls: 69,560 vol / $22.77M | Puts: 32,305 vol / $21.55M | P/C: 0.46 | HV30: 34%
- [S2_PC比偏低] (+2.0) P/C ratio 0.46 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $365 2026-10-02 $1239K | vol/OI 2.5x
- [S5_IV昂贵] (-1.0) Avg call IV 68% vs 30D HV 34% (2.0x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $1.24M — speculative upside bets

**COHR** — 🟢 **BUY** (score: +3.0)  
Spot: $292.22 | Calls: 9,034 vol / $5.63M | Puts: 4,273 vol / $6.84M | P/C: 0.47 | HV30: 80%
- [S2_PC比偏低] (+2.0) P/C ratio 0.47 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $300 2026-10-02 $693K | vol/OI 2.3x

**MRVL** — 🟡 **HOLD** (score: +1.5)  
Spot: $263.28 | Calls: 7,421 vol / $6.67M | Puts: 5,023 vol / $3.13M | P/C: 0.68 | HV30: 74%
- [S1_看涨流] (+1.5) Call premium $6.67M (68%) — bullish skew

**ASML** — 🟡 **HOLD** (score: +1.5)  
Spot: $1834.86 | Calls: 1,673 vol / $6.72M | Puts: 2,522 vol / $3.53M | P/C: 1.51 | HV30: 39%
- [S1_看涨流] (+1.5) Call premium $6.72M (66%) — bullish skew

**DELL** — 🟡 **HOLD** (score: +1.0)  
Spot: $539.73 | Calls: 9,423 vol / $19.06M | Puts: 6,131 vol / $10.55M | P/C: 0.65 | HV30: 80%
- [S3_看涨白鲸] (+1.0) Notable CALL $575 2026-10-16 $765K | vol/OI 2.2x

**ANET** — 🟡 **HOLD** (score: +0.5)  
Spot: $202.80 | Calls: 1,958 vol / $2.91M | Puts: 2,801 vol / $1.17M | P/C: 1.43 | HV30: 42%
- [S1_看涨流] (+1.5) Call premium $2.91M (71%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 64% vs 30D HV 42% (1.5x) — options expensive, sellers favored

**QCOM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $184.19 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 49%
- [NO_OPTIONS] (0.0) yfinance: no_options

**INTC** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $115.98 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 70%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SKHY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $186.69 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 64%
- [NO_OPTIONS] (0.0) yfinance: no_options

**GFS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $47.86 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ADI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $398.27 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 31%
- [NO_OPTIONS] (0.0) yfinance: no_options

**LRCX** — 🟡 **HOLD** (score: +0.0)  
Spot: $324.04 | Calls: 2,195 vol / $2.46M | Puts: 3,771 vol / $2.97M | P/C: 1.72 | HV30: 56%

**AMD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $607.77 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 55%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TSM** — 🟡 **HOLD** (score: +0.0)  
Spot: $457.01 | Calls: 14,147 vol / $25.04M | Puts: 21,791 vol / $6.71M | P/C: 1.54 | HV30: 28%
- [S1_重仓看涨流] (+3.0) Call premium $25.0M (79% of total) — large bullish flow
- [S2_PC比偏高] (-2.0) P/C ratio 1.54 ≥ 1.2 — bearish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 61% vs 30D HV 28% (2.2x) — options expensive, sellers favored

**ARM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $293.67 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 86%
- [NO_OPTIONS] (0.0) yfinance: no_options

**NVDA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $227.30 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 40%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TER** — 🟡 **HOLD** (score: +0.0)  
Spot: $403.28 | Calls: 2,904 vol / $3.09M | Puts: 1,775 vol / $3.47M | P/C: 0.61 | HV30: 67%

**SMCI** — 🟡 **HOLD** (score: -1.0)  
Spot: $41.03 | Calls: 11,474 vol / $1.62M | Puts: 8,381 vol / $1.97M | P/C: 0.73 | HV30: 72%
- [S3_看跌白鲸] (-1.0) Notable PUT $45 2026-10-23 $615K | vol/OI 9.9x

**KLAC** — 🟡 **HOLD** (score: -1.0)  
Spot: $196.50 | Calls: 1,396 vol / $0.82M | Puts: 723 vol / $0.20M | P/C: 0.52 | HV30: 47%
- [S5_IV昂贵] (-1.0) Avg call IV 90% vs 30D HV 47% (1.9x) — options expensive, sellers favored

**TXN** — 🟡 **HOLD** (score: -1.0)  
Spot: $281.82 | Calls: 82 vol / $0.09M | Puts: 131 vol / $0.07M | P/C: 1.60 | HV30: 29%
- [S5_IV昂贵] (-1.0) Avg call IV 51% vs 30D HV 29% (1.8x) — options expensive, sellers favored

**NXPI** — 🟡 **HOLD** (score: -1.0)  
Spot: $236.66 | Calls: 530 vol / $0.53M | Puts: 405 vol / $0.83M | P/C: 0.76 | HV30: 34%
- [S5_IV昂贵] (-1.0) Avg call IV 57% vs 30D HV 34% (1.7x) — options expensive, sellers favored

**MCHP** — 🟡 **HOLD** (score: -1.0)  
Spot: $78.78 | Calls: 2,342 vol / $1.17M | Puts: 1,948 vol / $0.69M | P/C: 0.83 | HV30: 35%
- [S5_IV昂贵] (-1.0) Avg call IV 69% vs 30D HV 35% (2.0x) — options expensive, sellers favored

### AI Infrastructure

**NBIS** — 🟢🟢 **STRONG BUY** (score: +5.5)  
Spot: $237.27 | Calls: 48,653 vol / $26.92M | Puts: 25,191 vol / $16.10M | P/C: 0.52 | HV30: 71%
- [S2_PC比偏低] (+2.0) P/C ratio 0.52 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $232 2026-10-16 $826K | vol/OI 2.6x
- [S4_看涨密度] (+1.5) 6 unusual call sweeps vs 2 put — concentrated bullish
- [S6_OTM看涨] (+1.0) OTM call premium $2.13M — speculative upside bets

**CRWV** — 🟢 **BUY** (score: +3.0)  
Spot: $85.91 | Calls: 75,656 vol / $12.78M | Puts: 29,807 vol / $7.74M | P/C: 0.39 | HV30: 71%
- [S2_PC比偏低] (+2.0) P/C ratio 0.39 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $50 2026-10-02 $833K | vol/OI 3.3x

**CSCO** — 🟢 **BUY** (score: +2.5)  
Spot: $106.96 | Calls: 18,394 vol / $2.57M | Puts: 6,634 vol / $0.72M | P/C: 0.36 | HV30: 25%
- [S1_看涨流] (+1.5) Call premium $2.57M (78%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.36 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 60% vs 30D HV 25% (2.4x) — options expensive, sellers favored

**GEV** — 🟡 **HOLD** (score: +1.0)  
Spot: $962.72 | Calls: 1,101 vol / $3.55M | Puts: 1,575 vol / $2.01M | P/C: 1.43 | HV30: 45%
- [S3_看涨白鲸] (+1.0) Notable CALL $895 2026-10-09 $797K | vol/OI 8.3x

**ORCL** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $137.90 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 48%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PSTG** — ⚪ **NO DATA** (score: +0.0)  
Spot: $0.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 0%
- [NO_PRICE] (0.0) Could not retrieve spot price

**CIFR** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $16.54 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 103%
- [NO_OPTIONS] (0.0) yfinance: no_options

**DLR** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $176.59 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 27%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CEG** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $264.64 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 38%
- [NO_OPTIONS] (0.0) yfinance: no_options

**APLD** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $25.42 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 77%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ETN** — 🟡 **HOLD** (score: +0.0)  
Spot: $433.21 | Calls: 341 vol / $0.41M | Puts: 851 vol / $0.40M | P/C: 2.50 | HV30: 42%

**VST** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $140.82 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 32%
- [NO_OPTIONS] (0.0) yfinance: no_options

**IREN** — 🟡 **HOLD** (score: -0.5)  
Spot: $41.39 | Calls: 49,402 vol / $2.93M | Puts: 28,418 vol / $6.65M | P/C: 0.58 | HV30: 77%
- [S1_看跌流] (-1.5) Put premium $6.65M (69%) — bearish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.58 ≤ 0.6 — bullish positioning
- [S3_看跌白鲸] (-1.0) Notable PUT $45 2026-10-02 $1870K | vol/OI 2.3x

**VRT** — 🔴🔴 **STRONG SELL** (score: -5.0)  
Spot: $248.43 | Calls: 3,075 vol / $3.34M | Puts: 3,890 vol / $10.92M | P/C: 1.27 | HV30: 59%
- [S1_重仓看跌流] (-3.0) Put premium $10.9M (77% of total) — large bearish flow
- [S3_巨鲸看跌] (-2.0) Whale PUT $330 2026-10-16 vol 992 | $8.39M premium | vol/OI 124.0x

**CIEN** — 🔴🔴 **STRONG SELL** (score: -5.0)  
Spot: $354.90 | Calls: 2,281 vol / $2.83M | Puts: 3,991 vol / $27.99M | P/C: 1.75 | HV30: 69%
- [S1_重仓看跌流] (-3.0) Put premium $28.0M (91% of total) — large bearish flow
- [S3_巨鲸看跌] (-2.0) Whale PUT $600 2026-10-16 vol 526 | $14.54M premium | vol/OI 99.0x

### Energy

**BE** — 🟢 **BUY** (score: +2.0)  
Spot: $291.28 | Calls: 100,999 vol / $92.37M | Puts: 85,586 vol / $54.40M | P/C: 0.85 | HV30: 85%
- [S3_巨鲸看涨] (+2.0) Whale CALL $300 2026-10-02 vol 11,753 | $7.29M premium | vol/OI 2.9x

**SMR** — 🟡 **HOLD** (score: +1.0)  
Spot: $7.76 | Calls: 6,553 vol / $0.07M | Puts: 1,551 vol / $0.22M | P/C: 0.24 | HV30: 96%
- [S2_PC比偏低] (+2.0) P/C ratio 0.24 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 231% vs 30D HV 96% (2.4x) — options expensive, sellers favored

**ONDS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $7.49 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 61%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $4.59 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 47%
- [NO_OPTIONS] (0.0) yfinance: no_options

**OKLO** — 🟡 **HOLD** (score: -0.5)  
Spot: $37.12 | Calls: 12,016 vol / $1.05M | Puts: 4,781 vol / $3.10M | P/C: 0.40 | HV30: 78%
- [S1_看跌流] (-1.5) Put premium $3.10M (75%) — bearish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.40 ≤ 0.6 — bullish positioning
- [S3_看跌白鲸] (-1.0) Notable PUT $120 2026-10-16 $1655K | vol/OI 99.0x

**MP** — 🟡 **HOLD** (score: -1.0)  
Spot: $45.44 | Calls: 1,601 vol / $0.08M | Puts: 1,721 vol / $0.34M | P/C: 1.07 | HV30: 53%
- [S5_IV昂贵] (-1.0) Avg call IV 84% vs 30D HV 53% (1.6x) — options expensive, sellers favored

**EOSE** — 🟡 **HOLD** (score: -1.0)  
Spot: $3.12 | Calls: 3,285 vol / $0.11M | Puts: 908 vol / $0.04M | P/C: 0.28 | HV30: 107%
- [S5_IV昂贵] (-1.0) Avg call IV 244% vs 30D HV 107% (2.3x) — options expensive, sellers favored

**LAC** — 🟡 **HOLD** (score: -1.0)  
Spot: $2.64 | Calls: 632 vol / $0.01M | Puts: 289 vol / $0.05M | P/C: 0.46 | HV30: 49%
- [S5_IV昂贵] (-1.0) Avg call IV 231% vs 30D HV 49% (4.7x) — options expensive, sellers favored

### Software

**MDB** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $336.91 | Calls: 8,138 vol / $11.23M | Puts: 4,335 vol / $10.07M | P/C: 0.53 | HV30: 87%
- [S2_PC比偏低] (+2.0) P/C ratio 0.53 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $260 2026-10-23 $831K | vol/OI 54.5x
- [S4_看涨密度] (+1.5) 3 unusual call sweeps vs 1 put — concentrated bullish

**NET** — 🟢 **BUY** (score: +3.5)  
Spot: $352.05 | Calls: 5,085 vol / $3.48M | Puts: 2,578 vol / $0.87M | P/C: 0.51 | HV30: 67%
- [S1_看涨流] (+1.5) Call premium $3.48M (80%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.51 ≤ 0.6 — bullish positioning

**CRDO** — 🟢 **BUY** (score: +3.0)  
Spot: $192.34 | Calls: 5,704 vol / $3.90M | Puts: 3,286 vol / $2.25M | P/C: 0.58 | HV30: 97%
- [S2_PC比偏低] (+2.0) P/C ratio 0.58 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $190 2026-10-30 $996K | vol/OI 2.7x

**SHOP** — 🟢 **BUY** (score: +2.5)  
Spot: $148.30 | Calls: 11,557 vol / $4.99M | Puts: 4,392 vol / $1.58M | P/C: 0.38 | HV30: 53%
- [S1_看涨流] (+1.5) Call premium $4.99M (76%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.38 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 83% vs 30D HV 53% (1.6x) — options expensive, sellers favored

**PLTR** — 🟢 **BUY** (score: +2.0)  
Spot: $186.97 | Calls: 55,661 vol / $15.26M | Puts: 44,003 vol / $8.39M | P/C: 0.79 | HV30: 45%
- [S3_巨鲸看涨] (+2.0) Whale CALL $188 2026-10-02 vol 7,284 | $2.24M premium | vol/OI 2.2x
- [S5_IV昂贵] (-1.0) Avg call IV 84% vs 30D HV 45% (1.9x) — options expensive, sellers favored
- [S6_OTM看涨] (+1.0) OTM call premium $2.24M — speculative upside bets

**RBRK** — 🟡 **HOLD** (score: +1.5)  
Spot: $114.72 | Calls: 958 vol / $1.05M | Puts: 779 vol / $0.24M | P/C: 0.81 | HV30: 82%
- [S1_看涨流] (+1.5) Call premium $1.05M (81%) — bullish skew

**RBLX** — 🟡 **HOLD** (score: +1.0)  
Spot: $41.19 | Calls: 6,180 vol / $0.22M | Puts: 2,396 vol / $0.46M | P/C: 0.39 | HV30: 66%
- [S2_PC比偏低] (+2.0) P/C ratio 0.39 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 106% vs 30D HV 66% (1.6x) — options expensive, sellers favored

**ESTC** — 🟡 **HOLD** (score: +1.0)  
Spot: $88.86 | Calls: 406 vol / $0.90M | Puts: 295 vol / $0.17M | P/C: 0.73 | HV30: 75%
- [S3_看涨白鲸] (+1.0) Notable CALL $50 2026-11-20 $596K | vol/OI 99.0x

**NOW** — 🟡 **HOLD** (score: +1.0)  
Spot: $129.99 | Calls: 29,865 vol / $6.89M | Puts: 20,933 vol / $7.61M | P/C: 0.70 | HV30: 57%
- [S3_看涨白鲸] (+1.0) Notable CALL $132 2026-10-02 $590K | vol/OI 4.9x

**TTD** — 🟡 **HOLD** (score: +1.0)  
Spot: $12.05 | Calls: 18,440 vol / $0.37M | Puts: 8,998 vol / $0.73M | P/C: 0.49 | HV30: 40%
- [S2_PC比偏低] (+2.0) P/C ratio 0.49 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 166% vs 30D HV 40% (4.1x) — options expensive, sellers favored

**SNOW** — 🟡 **HOLD** (score: +1.0)  
Spot: $330.30 | Calls: 6,465 vol / $4.63M | Puts: 4,538 vol / $2.95M | P/C: 0.70 | HV30: 60%
- [S3_看涨白鲸] (+1.0) Notable CALL $300 2026-10-09 $594K | vol/OI 23.1x

**OKTA** — 🟡 **HOLD** (score: +0.5)  
Spot: $204.85 | Calls: 1,830 vol / $3.69M | Puts: 5,535 vol / $1.53M | P/C: 3.02 | HV30: 101%
- [S1_看涨流] (+1.5) Call premium $3.69M (71%) — bullish skew
- [S2_PC比偏高] (-2.0) P/C ratio 3.02 ≥ 1.2 — bearish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $129 2026-10-02 $782K | vol/OI 4.6x

**WDAY** — 🟡 **HOLD** (score: +0.5)  
Spot: $189.18 | Calls: 2,837 vol / $1.44M | Puts: 606 vol / $0.26M | P/C: 0.21 | HV30: 44%
- [S1_看涨流] (+1.5) Call premium $1.44M (85%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 72% vs 30D HV 44% (1.6x) — options expensive, sellers favored

**DDOG** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $268.69 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 54%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TWLO** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $290.80 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 58%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ADBE** — 🟡 **HOLD** (score: +0.0)  
Spot: $233.18 | Calls: 1,252 vol / $0.44M | Puts: 1,378 vol / $0.93M | P/C: 1.10 | HV30: 43%

**ALAB** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $357.77 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 86%
- [NO_OPTIONS] (0.0) yfinance: no_options

**S** — 🟡 **HOLD** (score: +0.0)  
Spot: $23.33 | Calls: 1,169 vol / $0.08M | Puts: 80 vol / $0.01M | P/C: 0.07 | HV30: 0%

**U** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $39.72 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 38%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ZETA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $28.98 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 45%
- [NO_OPTIONS] (0.0) yfinance: no_options

**TEAM** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $175.96 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 58%
- [NO_OPTIONS] (0.0) yfinance: no_options

**APP** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $305.66 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 40%
- [NO_OPTIONS] (0.0) yfinance: no_options

**NFLX** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $70.32 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 36%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CRM** — 🟡 **HOLD** (score: +0.0)  
Spot: $225.41 | Calls: 8,190 vol / $2.50M | Puts: 7,068 vol / $1.72M | P/C: 0.86 | HV30: 74%

**WOLF** — 🟡 **HOLD** (score: +0.0)  
Spot: $28.14 | Calls: 635 vol / $0.11M | Puts: 434 vol / $0.06M | P/C: 0.68 | HV30: 80%

**SOUN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $5.83 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 40%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CFLT** — ⚪ **NO DATA** (score: +0.0)  
Spot: $0.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 0%
- [NO_PRICE] (0.0) Could not retrieve spot price

**INFY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $10.64 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 31%
- [NO_OPTIONS] (0.0) yfinance: no_options

**DUOL** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $142.69 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 59%
- [NO_OPTIONS] (0.0) yfinance: no_options

**BBAI** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $2.66 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 45%
- [NO_OPTIONS] (0.0) yfinance: no_options

**IBM** — 🟡 **HOLD** (score: +0.0)  
Spot: $220.00 | Calls: 6,515 vol / $1.89M | Puts: 3,412 vol / $3.26M | P/C: 0.52 | HV30: 33%
- [S2_PC比偏低] (+2.0) P/C ratio 0.52 ≤ 0.6 — bullish positioning
- [S3_看跌白鲸] (-1.0) Notable PUT $290 2026-10-16 $646K | vol/OI 3.6x
- [S5_IV昂贵] (-1.0) Avg call IV 60% vs 30D HV 33% (1.8x) — options expensive, sellers favored

**SNPS** — 🟡 **HOLD** (score: -1.0)  
Spot: $415.05 | Calls: 2,126 vol / $2.79M | Puts: 2,850 vol / $2.68M | P/C: 1.34 | HV30: 56%
- [S3_看跌白鲸] (-1.0) Notable PUT $422 2026-10-02 $1284K | vol/OI 7.5x

**AI** — 🟡 **HOLD** (score: -1.0)  
Spot: $10.35 | Calls: 1,508 vol / $0.07M | Puts: 2,898 vol / $0.04M | P/C: 1.92 | HV30: 45%
- [S5_IV昂贵] (-1.0) Avg call IV 108% vs 30D HV 45% (2.4x) — options expensive, sellers favored

**UPST** — 🟡 **HOLD** (score: -1.0)  
Spot: $23.13 | Calls: 3,627 vol / $0.09M | Puts: 2,871 vol / $0.62M | P/C: 0.79 | HV30: 47%
- [S5_IV昂贵] (-1.0) Avg call IV 119% vs 30D HV 47% (2.5x) — options expensive, sellers favored

**GTLB** — 🟡 **HOLD** (score: -1.0)  
Spot: $46.72 | Calls: 1,202 vol / $0.22M | Puts: 645 vol / $0.10M | P/C: 0.54 | HV30: 51%
- [S5_IV昂贵] (-1.0) Avg call IV 107% vs 30D HV 51% (2.1x) — options expensive, sellers favored

**HUBS** — 🟡 **HOLD** (score: -1.5)  
Spot: $197.64 | Calls: 235 vol / $0.52M | Puts: 985 vol / $2.09M | P/C: 4.19 | HV30: 65%
- [S1_看跌流] (-1.5) Put premium $2.09M (80%) — bearish skew

**INTU** — 🔴 **SELL** (score: -2.5)  
Spot: $268.06 | Calls: 2,305 vol / $1.00M | Puts: 1,492 vol / $3.50M | P/C: 0.65 | HV30: 42%
- [S1_看跌流] (-1.5) Put premium $3.50M (78%) — bearish skew
- [S5_IV昂贵] (-1.0) Avg call IV 79% vs 30D HV 42% (1.9x) — options expensive, sellers favored

**RDDT** — 🔴 **SELL** (score: -3.5)  
Spot: $145.35 | Calls: 11,346 vol / $1.71M | Puts: 11,404 vol / $3.42M | P/C: 1.01 | HV30: 54%
- [S1_看跌流] (-1.5) Put premium $3.42M (67%) — bearish skew
- [S3_看跌白鲸] (-1.0) Notable PUT $190 2026-10-02 $707K | vol/OI 99.0x
- [S5_IV昂贵] (-1.0) Avg call IV 103% vs 30D HV 54% (1.9x) — options expensive, sellers favored

**SPOT** — 🔴 **SELL** (score: -3.5)  
Spot: $493.30 | Calls: 996 vol / $0.63M | Puts: 2,695 vol / $2.29M | P/C: 2.71 | HV30: 40%
- [S1_看跌流] (-1.5) Put premium $2.29M (78%) — bearish skew
- [S3_看跌白鲸] (-1.0) Notable PUT $410 2026-10-30 $656K | vol/OI 841.5x
- [S5_IV昂贵] (-1.0) Avg call IV 69% vs 30D HV 40% (1.7x) — options expensive, sellers favored

### Health

**TEM** — 🟡 **HOLD** (score: +1.5)  
Spot: $82.62 | Calls: 2,390 vol / $1.16M | Puts: 2,200 vol / $0.40M | P/C: 0.92 | HV30: 109%
- [S1_看涨流] (+1.5) Call premium $1.16M (74%) — bullish skew

**HIMS** — 🟡 **HOLD** (score: +1.0)  
Spot: $28.70 | Calls: 25,174 vol / $1.37M | Puts: 6,963 vol / $1.09M | P/C: 0.28 | HV30: 74%
- [S2_PC比偏低] (+2.0) P/C ratio 0.28 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 114% vs 30D HV 74% (1.5x) — options expensive, sellers favored

**OSCR** — 🟡 **HOLD** (score: +0.5)  
Spot: $29.76 | Calls: 1,418 vol / $1.91M | Puts: 903 vol / $0.15M | P/C: 0.64 | HV30: 41%
- [S1_看涨流] (+1.5) Call premium $1.91M (93%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 118% vs 30D HV 41% (2.9x) — options expensive, sellers favored

**LLY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $1185.77 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 27%
- [NO_OPTIONS] (0.0) yfinance: no_options

**RXRX** — 🟡 **HOLD** (score: +0.0)  
Spot: $4.03 | Calls: 55 vol / $0.00M | Puts: 4 vol / $0.00M | P/C: 0.07 | HV30: 90%

**UNH** — 🟡 **HOLD** (score: +0.0)  
Spot: $374.95 | Calls: 8,385 vol / $6.95M | Puts: 5,787 vol / $4.56M | P/C: 0.69 | HV30: 19%
- [S3_看涨白鲸] (+1.0) Notable CALL $375 2026-10-16 $603K | vol/OI 2.2x
- [S5_IV昂贵] (-1.0) Avg call IV 51% vs 30D HV 19% (2.7x) — options expensive, sellers favored

**TMDX** — 🟡 **HOLD** (score: -1.0)  
Spot: $84.14 | Calls: 1,185 vol / $0.35M | Puts: 163 vol / $0.17M | P/C: 0.14 | HV30: 42%
- [S5_IV昂贵] (-1.0) Avg call IV 104% vs 30D HV 42% (2.5x) — options expensive, sellers favored

**CRSP** — 🟡 **HOLD** (score: -1.0)  
Spot: $56.01 | Calls: 515 vol / $0.08M | Puts: 216 vol / $0.03M | P/C: 0.42 | HV30: 63%
- [S5_IV昂贵] (-1.0) Avg call IV 95% vs 30D HV 63% (1.5x) — options expensive, sellers favored

### Space

**RKLB** — 🟡 **HOLD** (score: +1.0)  
Spot: $69.72 | Calls: 36,018 vol / $2.96M | Puts: 9,776 vol / $1.83M | P/C: 0.27 | HV30: 54%
- [S2_PC比偏低] (+2.0) P/C ratio 0.27 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 106% vs 30D HV 54% (2.0x) — options expensive, sellers favored

**ASTS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $59.42 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 74%
- [NO_OPTIONS] (0.0) yfinance: no_options

**LUNR** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $14.55 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 70%
- [NO_OPTIONS] (0.0) yfinance: no_options

**JOBY** — 🟡 **HOLD** (score: -1.0)  
Spot: $5.99 | Calls: 1,424 vol / $0.03M | Puts: 1,196 vol / $0.06M | P/C: 0.84 | HV30: 35%
- [S5_IV昂贵] (-1.0) Avg call IV 101% vs 30D HV 35% (2.9x) — options expensive, sellers favored

**ACHR** — 🟡 **HOLD** (score: -1.0)  
Spot: $5.07 | Calls: 6,061 vol / $0.14M | Puts: 4,347 vol / $0.17M | P/C: 0.72 | HV30: 48%
- [S5_IV昂贵] (-1.0) Avg call IV 247% vs 30D HV 48% (5.2x) — options expensive, sellers favored

**FLY** — 🟡 **HOLD** (score: -1.0)  
Spot: $22.87 | Calls: 1,269 vol / $0.36M | Puts: 794 vol / $0.09M | P/C: 0.63 | HV30: 67%
- [S5_IV昂贵] (-1.0) Avg call IV 113% vs 30D HV 67% (1.7x) — options expensive, sellers favored

### China

**NIO** — 🟢 **BUY** (score: +2.0)  
Spot: $3.40 | Calls: 13,520 vol / $0.13M | Puts: 3,309 vol / $0.11M | P/C: 0.24 | HV30: 0%
- [S2_PC比偏低] (+2.0) P/C ratio 0.24 ≤ 0.6 — bullish positioning

**XPEV** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $9.46 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 41%
- [NO_OPTIONS] (0.0) yfinance: no_options

**FUTU** — 🟡 **HOLD** (score: +0.0)  
Spot: $112.98 | Calls: 277 vol / $0.05M | Puts: 408 vol / $0.10M | P/C: 1.47 | HV30: 51%

**TCEHY** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $54.60 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 28%
- [NO_OPTIONS] (0.0) yfinance: no_options

**BABA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $107.75 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 39%
- [NO_OPTIONS] (0.0) yfinance: no_options

**JD** — 🟡 **HOLD** (score: -1.0)  
Spot: $26.30 | Calls: 2,704 vol / $0.12M | Puts: 4,656 vol / $0.30M | P/C: 1.72 | HV30: 18%
- [S5_IV昂贵] (-1.0) Avg call IV 97% vs 30D HV 18% (5.3x) — options expensive, sellers favored

**BIDU** — 🔴 **SELL** (score: -2.5)  
Spot: $86.73 | Calls: 9,023 vol / $0.77M | Puts: 3,234 vol / $3.56M | P/C: 0.36 | HV30: 50%
- [S1_看跌流] (-1.5) Put premium $3.56M (82%) — bearish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.36 ≤ 0.6 — bullish positioning
- [S3_巨鲸看跌] (-2.0) Whale PUT $115 2026-10-16 vol 926 | $2.62M premium | vol/OI 71.2x
- [S5_IV昂贵] (-1.0) Avg call IV 78% vs 30D HV 50% (1.6x) — options expensive, sellers favored

**PDD** — 🔴 **SELL** (score: -3.0)  
Spot: $77.52 | Calls: 2,883 vol / $0.12M | Puts: 5,875 vol / $0.99M | P/C: 2.04 | HV30: 23%
- [S2_PC比偏高] (-2.0) P/C ratio 2.04 ≥ 1.2 — bearish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 55% vs 30D HV 23% (2.4x) — options expensive, sellers favored

### Crypto

**IBIT** — 🟢🟢 **STRONG BUY** (score: +5.0)  
Spot: $47.33 | Calls: 112,602 vol / $5.67M | Puts: 47,679 vol / $2.04M | P/C: 0.42 | HV30: 48%
- [S1_重仓看涨流] (+3.0) Call premium $5.7M (74% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.42 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $48 2026-10-09 $919K | vol/OI 4.8x
- [S5_IV昂贵] (-1.0) Avg call IV 74% vs 30D HV 48% (1.6x) — options expensive, sellers favored

**MSTR** — 🟢🟢 **STRONG BUY** (score: +4.5)  
Spot: $154.72 | Calls: 133,770 vol / $49.59M | Puts: 80,916 vol / $33.81M | P/C: 0.60 | HV30: 105%
- [S3_巨鲸看涨] (+2.0) Whale CALL $162 2026-10-23 vol 5,665 | $4.08M premium | vol/OI 13.5x
- [S4_看涨密度] (+1.5) 8 unusual call sweeps vs 0 put — concentrated bullish
- [S6_OTM看涨] (+1.0) OTM call premium $14.53M — speculative upside bets

**BMNR** — 🟢 **BUY** (score: +3.5)  
Spot: $26.74 | Calls: 13,582 vol / $2.18M | Puts: 4,593 vol / $0.61M | P/C: 0.34 | HV30: 89%
- [S1_看涨流] (+1.5) Call premium $2.18M (78%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.34 ≤ 0.6 — bullish positioning

**ETHA** — 🟡 **HOLD** (score: +0.5)  
Spot: $20.27 | Calls: 39,200 vol / $1.67M | Puts: 26,584 vol / $0.48M | P/C: 0.68 | HV30: 57%
- [S1_看涨流] (+1.5) Call premium $1.67M (78%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 93% vs 30D HV 57% (1.6x) — options expensive, sellers favored

**COIN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $190.07 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 89%
- [NO_OPTIONS] (0.0) yfinance: no_options

**HUT** — 🟡 **HOLD** (score: +0.0)  
Spot: $92.89 | Calls: 2,311 vol / $1.20M | Puts: 1,808 vol / $0.95M | P/C: 0.78 | HV30: 89%

**RIOT** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $21.41 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 84%
- [NO_OPTIONS] (0.0) yfinance: no_options

**XRPC** — 🟡 **HOLD** (score: +0.0)  
Spot: $15.85 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 97%

**BSOL** — 🟡 **HOLD** (score: +0.0)  
Spot: $16.37 | Calls: 436 vol / $0.13M | Puts: 165 vol / $0.02M | P/C: 0.38 | HV30: 74%

**MARA** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $12.00 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 95%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CLSK** — 🟡 **HOLD** (score: -1.0)  
Spot: $13.30 | Calls: 7,118 vol / $0.47M | Puts: 6,663 vol / $0.65M | P/C: 0.94 | HV30: 81%
- [S5_IV昂贵] (-1.0) Avg call IV 163% vs 30D HV 81% (2.0x) — options expensive, sellers favored

**BULL** — 🟡 **HOLD** (score: -1.0)  
Spot: $7.18 | Calls: 1,742 vol / $0.07M | Puts: 829 vol / $0.07M | P/C: 0.48 | HV30: 74%
- [S5_IV昂贵] (-1.0) Avg call IV 161% vs 30D HV 74% (2.2x) — options expensive, sellers favored

**SBET** — 🟡 **HOLD** (score: -1.0)  
Spot: $9.47 | Calls: 3,593 vol / $0.18M | Puts: 195 vol / $0.01M | P/C: 0.05 | HV30: 89%
- [S5_IV昂贵] (-1.0) Avg call IV 178% vs 30D HV 89% (2.0x) — options expensive, sellers favored

**HIVE** — 🟡 **HOLD** (score: -1.0)  
Spot: $3.00 | Calls: 576 vol / $0.07M | Puts: 181 vol / $0.01M | P/C: 0.31 | HV30: 87%
- [S5_IV昂贵] (-1.0) Avg call IV 247% vs 30D HV 87% (2.8x) — options expensive, sellers favored

### Finance

**HOOD** — 🟢🟢 **STRONG BUY** (score: +7.0)  
Spot: $116.24 | Calls: 47,905 vol / $15.20M | Puts: 25,596 vol / $7.01M | P/C: 0.53 | HV30: 85%
- [S1_看涨流] (+1.5) Call premium $15.20M (68%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.53 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $118 2026-10-02 $715K | vol/OI 2.9x
- [S4_看涨密度] (+1.5) 3 unusual call sweeps vs 1 put — concentrated bullish
- [S6_OTM看涨] (+1.0) OTM call premium $1.33M — speculative upside bets

**SOFI** — 🟢 **BUY** (score: +2.0)  
Spot: $15.91 | Calls: 105,398 vol / $2.41M | Puts: 56,447 vol / $3.52M | P/C: 0.54 | HV30: 48%
- [S2_PC比偏低] (+2.0) P/C ratio 0.54 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $16 2026-10-02 $566K | vol/OI 3.0x
- [S5_IV昂贵] (-1.0) Avg call IV 90% vs 30D HV 48% (1.9x) — options expensive, sellers favored

**OPEN** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $2.38 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 54%
- [NO_OPTIONS] (0.0) yfinance: no_options

**PYPL** — 🟡 **HOLD** (score: -1.0)  
Spot: $53.90 | Calls: 3,011 vol / $0.36M | Puts: 2,398 vol / $0.23M | P/C: 0.80 | HV30: 48%
- [S5_IV昂贵] (-1.0) Avg call IV 73% vs 30D HV 48% (1.5x) — options expensive, sellers favored

**LMND** — 🟡 **HOLD** (score: -1.0)  
Spot: $44.62 | Calls: 167 vol / $0.01M | Puts: 138 vol / $0.05M | P/C: 0.83 | HV30: 41%
- [S5_IV昂贵] (-1.0) Avg call IV 78% vs 30D HV 41% (1.9x) — options expensive, sellers favored

**AFRM** — 🟡 **HOLD** (score: -1.0)  
Spot: $69.35 | Calls: 3,486 vol / $0.62M | Puts: 1,817 vol / $0.45M | P/C: 0.52 | HV30: 53%
- [S5_IV昂贵] (-1.0) Avg call IV 79% vs 30D HV 53% (1.5x) — options expensive, sellers favored

### Quantum

**IONQ** — 🟢 **BUY** (score: +2.0)  
Spot: $43.90 | Calls: 17,276 vol / $1.81M | Puts: 7,702 vol / $1.27M | P/C: 0.45 | HV30: 71%
- [S2_PC比偏低] (+2.0) P/C ratio 0.45 ≤ 0.6 — bullish positioning

**RGTI** — 🟡 **HOLD** (score: +1.0)  
Spot: $15.78 | Calls: 13,515 vol / $0.56M | Puts: 6,305 vol / $0.61M | P/C: 0.47 | HV30: 69%
- [S2_PC比偏低] (+2.0) P/C ratio 0.47 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 141% vs 30D HV 69% (2.1x) — options expensive, sellers favored

**QBTS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $16.45 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 69%
- [NO_OPTIONS] (0.0) yfinance: no_options

**QUBT** — 🟡 **HOLD** (score: -1.0)  
Spot: $8.48 | Calls: 3,266 vol / $0.06M | Puts: 1,158 vol / $0.08M | P/C: 0.35 | HV30: 57%
- [S5_IV昂贵] (-1.0) Avg call IV 172% vs 30D HV 57% (3.0x) — options expensive, sellers favored

### Trading

**GME** — 🟢🟢 **STRONG BUY** (score: +4.0)  
Spot: $23.75 | Calls: 94,192 vol / $6.79M | Puts: 19,162 vol / $1.05M | P/C: 0.20 | HV30: 39%
- [S1_重仓看涨流] (+3.0) Call premium $6.8M (87% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.20 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 120% vs 30D HV 39% (3.1x) — options expensive, sellers favored

**LULU** — 🟢 **BUY** (score: +2.0)  
Spot: $96.85 | Calls: 12,219 vol / $1.08M | Puts: 6,352 vol / $1.29M | P/C: 0.52 | HV30: 64%
- [S2_PC比偏低] (+2.0) P/C ratio 0.52 ≤ 0.6 — bullish positioning

**PTON** — 🟡 **HOLD** (score: +1.0)  
Spot: $5.05 | Calls: 5,207 vol / $0.20M | Puts: 279 vol / $0.02M | P/C: 0.05 | HV30: 42%
- [S2_PC比偏低] (+2.0) P/C ratio 0.05 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 278% vs 30D HV 42% (6.6x) — options expensive, sellers favored

**NKE** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $35.83 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 26%
- [NO_OPTIONS] (0.0) yfinance: no_options

**UPS** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $93.93 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 26%
- [NO_OPTIONS] (0.0) yfinance: no_options

**ABNB** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $156.97 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 36%
- [NO_OPTIONS] (0.0) yfinance: no_options

**CMG** — 🟡 **HOLD** (score: -1.0)  
Spot: $31.89 | Calls: 13,714 vol / $0.71M | Puts: 9,321 vol / $0.55M | P/C: 0.68 | HV30: 36%
- [S5_IV昂贵] (-1.0) Avg call IV 88% vs 30D HV 36% (2.5x) — options expensive, sellers favored

**BA** — 🔴🔴 **STRONG SELL** (score: -5.0)  
Spot: $187.76 | Calls: 14,492 vol / $3.94M | Puts: 11,483 vol / $9.74M | P/C: 0.79 | HV30: 30%
- [S1_重仓看跌流] (-3.0) Put premium $9.7M (71% of total) — large bearish flow
- [S3_看跌白鲸] (-1.0) Notable PUT $218 2026-10-16 $705K | vol/OI 99.0x
- [S5_IV昂贵] (-1.0) Avg call IV 62% vs 30D HV 30% (2.0x) — options expensive, sellers favored

### Rotation

**WMT** — 🟢🟢 **STRONG BUY** (score: +6.5)  
Spot: $106.83 | Calls: 64,788 vol / $7.42M | Puts: 23,590 vol / $2.24M | P/C: 0.36 | HV30: 34%
- [S1_重仓看涨流] (+3.0) Call premium $7.4M (77% of total) — large bullish flow
- [S2_PC比偏低] (+2.0) P/C ratio 0.36 ≤ 0.6 — bullish positioning
- [S3_看涨白鲸] (+1.0) Notable CALL $106 2026-10-16 $1057K | vol/OI 74.2x
- [S4_看涨密度] (+1.5) 3 unusual call sweeps vs 0 put — concentrated bullish
- [S5_IV昂贵] (-1.0) Avg call IV 53% vs 30D HV 34% (1.6x) — options expensive, sellers favored

**DE** — 🟢 **BUY** (score: +3.0)  
Spot: $680.46 | Calls: 1,123 vol / $5.03M | Puts: 1,894 vol / $1.37M | P/C: 1.69 | HV30: 36%
- [S1_重仓看涨流] (+3.0) Call premium $5.0M (79% of total) — large bullish flow

**XOM** — 🟢 **BUY** (score: +2.5)  
Spot: $161.40 | Calls: 10,215 vol / $2.36M | Puts: 4,996 vol / $0.68M | P/C: 0.49 | HV30: 25%
- [S1_看涨流] (+1.5) Call premium $2.36M (78%) — bullish skew
- [S2_PC比偏低] (+2.0) P/C ratio 0.49 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 50% vs 30D HV 25% (2.0x) — options expensive, sellers favored

**CAT** — 🟡 **HOLD** (score: +1.5)  
Spot: $826.84 | Calls: 3,644 vol / $7.32M | Puts: 3,372 vol / $3.80M | P/C: 0.93 | HV30: 28%
- [S1_看涨流] (+1.5) Call premium $7.32M (66%) — bullish skew
- [S3_看涨白鲸] (+1.0) Notable CALL $775 2026-10-09 $600K | vol/OI 13.5x
- [S5_IV昂贵] (-1.0) Avg call IV 61% vs 30D HV 28% (2.2x) — options expensive, sellers favored

**JPM** — 🟡 **HOLD** (score: +1.0)  
Spot: $335.04 | Calls: 8,767 vol / $2.31M | Puts: 5,101 vol / $1.47M | P/C: 0.58 | HV30: 18%
- [S2_PC比偏低] (+2.0) P/C ratio 0.58 ≤ 0.6 — bullish positioning
- [S5_IV昂贵] (-1.0) Avg call IV 42% vs 30D HV 18% (2.3x) — options expensive, sellers favored

**JNJ** — 🟡 **HOLD** (score: +0.5)  
Spot: $267.65 | Calls: 2,779 vol / $1.43M | Puts: 4,621 vol / $0.63M | P/C: 1.66 | HV30: 19%
- [S1_看涨流] (+1.5) Call premium $1.43M (70%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 51% vs 30D HV 19% (2.6x) — options expensive, sellers favored

**BRK-B** — 🟡 **HOLD** (score: +0.5)  
Spot: $502.42 | Calls: 6,600 vol / $3.80M | Puts: 4,694 vol / $0.91M | P/C: 0.71 | HV30: 11%
- [S1_看涨流] (+1.5) Call premium $3.80M (81%) — bullish skew
- [S5_IV昂贵] (-1.0) Avg call IV 36% vs 30D HV 11% (3.2x) — options expensive, sellers favored

**XLU** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $39.72 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 15%
- [NO_OPTIONS] (0.0) yfinance: no_options

**GE** — 🟡 **HOLD** (score: -1.0)  
Spot: $318.11 | Calls: 1,425 vol / $0.81M | Puts: 1,086 vol / $0.75M | P/C: 0.76 | HV30: 30%
- [S5_IV昂贵] (-1.0) Avg call IV 56% vs 30D HV 30% (1.9x) — options expensive, sellers favored

**COST** — 🟡 **HOLD** (score: -1.0)  
Spot: $924.66 | Calls: 5,920 vol / $5.67M | Puts: 4,162 vol / $4.16M | P/C: 0.70 | HV30: 20%
- [S5_IV昂贵] (-1.0) Avg call IV 32% vs 30D HV 20% (1.7x) — options expensive, sellers favored

**CVX** — 🟡 **HOLD** (score: -1.0)  
Spot: $204.40 | Calls: 2,156 vol / $0.68M | Puts: 1,129 vol / $0.26M | P/C: 0.52 | HV30: 22%
- [S5_IV昂贵] (-1.0) Avg call IV 42% vs 30D HV 22% (1.9x) — options expensive, sellers favored

**GS** — 🔴 **SELL** (score: -2.5)  
Spot: $916.37 | Calls: 3,283 vol / $4.10M | Puts: 4,202 vol / $7.70M | P/C: 1.28 | HV30: 28%
- [S1_看跌流] (-1.5) Put premium $7.70M (65%) — bearish skew
- [S5_IV昂贵] (-1.0) Avg call IV 50% vs 30D HV 28% (1.8x) — options expensive, sellers favored

### Commodity

**GLD** — 🟢 **BUY** (score: +2.0)  
Spot: $383.00 | Calls: 8,362 vol / $1.02M | Puts: 3,137 vol / $1.62M | P/C: 0.38 | HV30: 27%
- [S2_PC比偏低] (+2.0) P/C ratio 0.38 ≤ 0.6 — bullish positioning

**USO** — ⚪ **NO OPTIONS** (score: +0.0)  
Spot: $143.38 | Calls: 0 vol / $0.00M | Puts: 0 vol / $0.00M | P/C: N/A | HV30: 44%
- [NO_OPTIONS] (0.0) yfinance: no_options

**SLV** — 🟡 **HOLD** (score: -1.0)  
Spot: $55.49 | Calls: 23,528 vol / $2.12M | Puts: 15,862 vol / $2.47M | P/C: 0.67 | HV30: 42%
- [S5_IV昂贵] (-1.0) Avg call IV 65% vs 30D HV 42% (1.5x) — options expensive, sellers favored

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
