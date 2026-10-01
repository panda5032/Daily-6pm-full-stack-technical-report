# 🐋 Whale Deep Dive — 2026-09-30 15:14
Tickers: CIEN, JNJ, TSLA, NVDA, GOOGL · min print $250,000 · DTE 3–120 · fresh = Vol/OI ≥ 2.0 · whale ≥ $2,000,000
> ARB rows (paired deep-ITM call+put, same expiry) are financing trades — excluded from the directional $P/C. Volume shows both sides of a trade; aggressor side is inferred, not known. Not financial advice.

## CIEN — spot $351.93 — **BEARISH FLOW**
- Raw $P/C **15549370.00** (calls $0.0M / puts $15.5M) · Directional (arb-excluded) $P/C **15549370.00** (calls $0.0M / puts $15.5M)
- Fresh whale prints: 0 call-side / 2 put-side · 30D HV 65% · front ATM IV 57% (0.9x HV)
- Term structure (ATM IV / expected move): 10-09(9d) 57%/+7.9%  10-16(16d) 62%/+10.6%  10-23(23d) 62%/+12.7%  10-30(30d) 66%/+15.2%  11-06(37d) 62%/+15.3%  11-20(51d) 64%/+19.3%  12-18(79d) 71%/+26.5%

| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |
|---|---|---|---|---|---|---|---|---|---|
| PUT | 600 | 2026-10-16 | 16 | 526 | 0 | inf | $13,065,840 | 105% | SYNTH_SHORT,WHALE,fresh |
| PUT | 530 | 2026-10-16 | 16 | 124 | 0 | inf | $2,223,940 | 104% | SYNTH_SHORT,WHALE,fresh |
| PUT | 360 | 2026-10-16 | 16 | 102 | 390 | 0.3 | $259,590 | 69% | churn |


## JNJ — spot $264.79 — **BULLISH FLOW**
- Raw $P/C **0.00** (calls $34.9M / puts $0.0M) · Directional (arb-excluded) $P/C **0.00** (calls $34.9M / puts $0.0M)
- Fresh whale prints: 2 call-side / 0 put-side · 30D HV 17% · front ATM IV 26% (1.5x HV)
- Term structure (ATM IV / expected move): 10-09(9d) 26%/+3.0%  10-16(16d) 28%/+4.5%  10-23(23d) 29%/+5.4%  10-30(30d) 28%/+6.1%  11-06(37d) 28%/+5.7%  11-20(51d) 27%/+7.8%  12-18(79d) 26%/+9.5%

| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |
|---|---|---|---|---|---|---|---|---|---|
| CALL | 185 | 2026-10-16 | 16 | 3,637 | 0 | inf | $29,386,960 | 101% | STOCK_REPL,WHALE,fresh |
| CALL | 180 | 2026-10-16 | 16 | 275 | 0 | inf | $2,364,312 | 111% | STOCK_REPL,WHALE,fresh |
| CALL | 170 | 2026-10-16 | 16 | 205 | 20 | 10.2 | $1,968,512 | 126% | STOCK_REPL,fresh |
| CALL | 175 | 2026-10-16 | 16 | 130 | 0 | inf | $1,176,175 | 106% | STOCK_REPL,fresh |


## TSLA — spot $354.81 — **BULLISH FLOW**
- Raw $P/C **0.33** (calls $143.6M / puts $46.9M) · Directional (arb-excluded) $P/C **0.33** (calls $143.6M / puts $46.9M)
- Fresh whale prints: 10 call-side / 1 put-side · 30D HV 45% · front ATM IV 36% (0.8x HV)
- Term structure (ATM IV / expected move): 10-05(5d) 36%/+3.6%  10-07(7d) 38%/+4.4%  10-09(9d) 39%/+5.1%  10-16(16d) 40%/+6.8%  10-23(23d) 46%/+9.4%  10-30(30d) 45%/+10.4%  11-06(37d) 44%/+11.3%

| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |
|---|---|---|---|---|---|---|---|---|---|
| CALL | 350 | 2026-10-16 | 16 | 5,840 | 4,533 | 1.3 | $8,628,600 | 41% | churn |
| CALL | 355 | 2026-10-09 | 9 | 9,239 | 1,435 | 6.4 | $8,453,685 | 40% | WHALE,fresh |
| PUT | 350 | 2026-10-16 | 16 | 8,244 | 8,709 | 0.9 | $7,790,580 | 39% | churn |
| CALL | 350 | 2026-11-06 | 37 | 3,138 | 69 | 45.5 | $7,303,695 | 47% | WHALE,fresh |
| CALL | 175 | 2026-10-16 | 16 | 400 | 479 | 0.8 | $7,146,000 | 182% | churn |
| CALL | 350 | 2026-10-30 | 30 | 2,981 | 2,171 | 1.4 | $6,349,530 | 46% | churn |
| CALL | 350 | 2026-10-09 | 9 | 5,014 | 905 | 5.5 | $5,916,520 | 40% | WHALE,fresh |
| CALL | 338 | 2026-10-05 | 5 | 3,105 | 3 | 1035.0 | $5,845,163 | 44% | WHALE,fresh |
| CALL | 360 | 2026-10-16 | 16 | 5,630 | 6,483 | 0.9 | $5,714,450 | 41% | churn |
| CALL | 365 | 2026-10-09 | 9 | 7,527 | 1,843 | 4.1 | $3,895,222 | 40% | WHALE,fresh |
| CALL | 355 | 2026-10-16 | 16 | 2,995 | 2,434 | 1.2 | $3,721,288 | 41% | churn |
| PUT | 350 | 2026-10-09 | 9 | 5,409 | 1,800 | 3.0 | $3,515,850 | 38% | WHALE,fresh |
| CALL | 352 | 2026-10-09 | 9 | 3,134 | 584 | 5.4 | $3,267,195 | 40% | WHALE,fresh |
| CALL | 348 | 2026-10-09 | 9 | 2,366 | 156 | 15.2 | $3,158,610 | 41% | WHALE,fresh |
| PUT | 365 | 2026-10-30 | 30 | 1,310 | 822 | 1.6 | $3,121,075 | 44% | churn |


## NVDA — spot $228.38 — **BULLISH FLOW**
- Raw $P/C **0.52** (calls $86.9M / puts $45.4M) · Directional (arb-excluded) $P/C **0.52** (calls $86.9M / puts $45.4M)
- Fresh whale prints: 6 call-side / 5 put-side · 30D HV 38% · front ATM IV 28% (0.7x HV)
- Term structure (ATM IV / expected move): 10-05(5d) 28%/+2.8%  10-07(7d) 30%/+3.5%  10-09(9d) 31%/+4.1%  10-16(16d) 32%/+5.4%  10-23(23d) 31%/+6.3%  10-30(30d) 31%/+7.2%  11-06(37d) 32%/+8.2%

| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |
|---|---|---|---|---|---|---|---|---|---|
| CALL | 230 | 2026-10-16 | 16 | 16,286 | 60,517 | 0.3 | $9,364,450 | 33% | churn |
| CALL | 218 | 2026-10-05 | 5 | 5,546 | 801 | 6.9 | $6,987,960 | 58% | WHALE,fresh |
| CALL | 220 | 2026-10-05 | 5 | 5,986 | 1,777 | 3.4 | $5,971,035 | 45% | WHALE,fresh |
| PUT | 230 | 2026-10-09 | 9 | 10,031 | 9,765 | 1.0 | $4,990,422 | 27% | churn |
| PUT | 240 | 2026-10-05 | 5 | 4,182 | 801 | 5.2 | $4,474,740 | 0% | WHALE,fresh |
| CALL | 215 | 2026-10-05 | 5 | 3,075 | 519 | 5.9 | $4,443,375 | 53% | WHALE,fresh |
| CALL | 230 | 2026-10-09 | 9 | 9,883 | 12,186 | 0.8 | $4,175,567 | 33% | churn |
| CALL | 215 | 2026-10-16 | 16 | 2,444 | 25,661 | 0.1 | $3,983,720 | 43% | churn |
| CALL | 220 | 2026-10-07 | 7 | 3,740 | 330 | 11.3 | $3,880,250 | 41% | WHALE,fresh |
| PUT | 230 | 2026-10-07 | 7 | 7,490 | 474 | 15.8 | $3,052,175 | 24% | WHALE,fresh |
| CALL | 225 | 2026-10-16 | 16 | 3,290 | 30,730 | 0.1 | $2,845,850 | 36% | churn |
| PUT | 225 | 2026-10-23 | 23 | 5,748 | 5,606 | 1.0 | $2,830,890 | 28% | churn |
| CALL | 218 | 2026-10-07 | 7 | 2,160 | 293 | 7.4 | $2,662,200 | 43% | WHALE,fresh |
| PUT | 220 | 2026-10-09 | 9 | 19,001 | 6,433 | 3.0 | $2,555,635 | 29% | WHALE,fresh |
| PUT | 230 | 2026-10-16 | 16 | 3,757 | 15,135 | 0.2 | $2,272,985 | 27% | churn |


## GOOGL — spot $344.08 — **BULLISH FLOW**
- Raw $P/C **0.23** (calls $56.2M / puts $12.8M) · Directional (arb-excluded) $P/C **0.23** (calls $56.2M / puts $12.8M)
- Fresh whale prints: 3 call-side / 0 put-side · 30D HV 24% · front ATM IV 30% (1.3x HV)
- Term structure (ATM IV / expected move): 10-05(5d) 30%/+3.0%  10-07(7d) 36%/+3.9%  10-09(9d) 35%/+4.2%  10-16(16d) 32%/+5.3%  10-23(23d) 34%/+6.5%  10-30(30d) 37%/+8.4%  11-06(37d) 39%/+9.4%

| Type | Strike | Exp | DTE | Vol | OI | V/OI | Premium | IV | Tags |
|---|---|---|---|---|---|---|---|---|---|
| CALL | 170 | 2026-10-16 | 16 | 852 | 662 | 1.3 | $14,882,310 | 159% | churn |
| CALL | 350 | 2026-10-16 | 16 | 4,929 | 9,345 | 0.5 | $3,413,333 | 33% | churn |
| CALL | 360 | 2026-10-16 | 16 | 7,349 | 18,312 | 0.4 | $2,774,248 | 32% | churn |
| CALL | 350 | 2026-10-09 | 9 | 5,137 | 1,813 | 2.8 | $2,427,232 | 32% | WHALE,fresh |
| CALL | 300 | 2026-10-09 | 9 | 538 | 86 | 6.3 | $2,411,585 | 53% | STOCK_REPL,WHALE,fresh |
| CALL | 305 | 2026-10-16 | 16 | 589 | 248 | 2.4 | $2,353,055 | 50% | WHALE,fresh |
| CALL | 340 | 2026-10-16 | 16 | 1,520 | 7,360 | 0.2 | $1,763,200 | 34% | churn |
| CALL | 355 | 2026-10-09 | 9 | 5,209 | 7,621 | 0.7 | $1,653,858 | 32% | churn |
| CALL | 350 | 2026-10-30 | 30 | 1,220 | 3,345 | 0.4 | $1,579,900 | 40% | churn |
| CALL | 348 | 2026-10-16 | 16 | 1,804 | 406 | 4.4 | $1,456,730 | 33% | fresh |
| CALL | 370 | 2026-10-16 | 16 | 6,519 | 34,116 | 0.2 | $1,336,395 | 33% | churn |
| PUT | 348 | 2026-10-09 | 9 | 1,336 | 46 | 29.0 | $1,225,780 | 37% | fresh |
| CALL | 345 | 2026-10-16 | 16 | 1,340 | 6,009 | 0.2 | $1,209,350 | 33% | churn |
| PUT | 350 | 2026-10-16 | 16 | 986 | 6,398 | 0.2 | $1,180,735 | 31% | churn |
| CALL | 300 | 2026-10-16 | 16 | 261 | 949 | 0.3 | $1,157,535 | 52% | churn |


---
