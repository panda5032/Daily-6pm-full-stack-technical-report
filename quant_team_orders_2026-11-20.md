# Quant team order plan — 2026-11-20

**Status: PROVISIONAL PLAN. No orders have been placed.** This desk has no market access; the plan is for a human to execute.

The portfolio file is an intraday snapshot (~3:52pm ET, minutes before the close). Every price, share count, stop and dollar figure below is provisional. Re-run `python quant_team.py screen` and `optimize` on closing prices and recompute this plan before any order goes in.

## Summary

| Item | Value |
|---|---|
| Capital | $100,000 |
| Current holdings | none (all trades are new buys; no sells, no rebalance) |
| Target gross exposure | 25% ($25,000 by weight) |
| Achievable after whole-share rounding | $20,868 (20.9%) across 14 names; COST rounds to 0 shares |
| Tranche 1 (now, subject to refresh) | $6,376 (6.4% of capital, 31% of the achievable book), 12 names |
| Tranche 2 (on trigger) | $8,737 |
| Tranche 3 (on trigger) | $5,755 |
| Cash after tranche 1 | $93,624 (93.6%) |
| Cash after all three tranches | $79,132 (79.1%) |
| Open risk at stops, tranche 1 / full book | 0.27R / 0.98R (R = 1% of capital = $1,000) |

## Rules applied

- **Regime RISK-OFF -> three tranches** (role rule; playbook 11 principle of adding only to winners, never averaging down). Tranche 1 now, tranches 2 and 3 only on the PM's add-risk triggers.
- **QQQ-below-MA50 gate is ON.** QQQ 607.18 vs MA50 710.86 (-14.6%) in the cache; the house rule is no new buy on such a day unless the PM memo explicitly accepts it.
  - **TSM, ASML, ANET: PM override recorded.** The memo states that holding these "runs against the house QQQ-below-MA50 gate, so they are sized at 1.1-1.7% and should be entered in three tranches." Rule applied: explicit PM acceptance, staged entry.
  - **Other 11 tradable names:** the memo's decision is to be 25% invested today with QQQ below MA50 stated in the same sentence, which I read as acceptance of new buys for the book. It does not use explicit gate-override wording for these names. Rule applied: PM decision, three tranches. **PM to confirm** before tranche 1 is sent; if not confirmed, the gate holds all of tranche 1.
  - The macro desk's note asks for "staged, no adds before PCE Nov 25". Built into the tranche-2 condition.
- **Stops:** no same-day trade plan exists (`trade_plans_*.json` are from 2026-10-01 and were not used). Stop = the nearer of MA50 or 2x 20-day ATR below the entry reference.
  - **ATR is approximated.** The cache has adjusted closes only (no high/low), so ATR = 20-day mean of absolute close-to-close changes. This understates true range, so real 2x ATR stops would sit somewhat lower.
  - 9 names trade below their MA50, so MA50 is not a stop below entry; 2x ATR is used. For LLY, UPS, WMT, BRK-B the 2x ATR level is nearer than MA50. ABNB sits 0.1% above its MA50 (less than one ATR), which is noise rather than a stop, so 2x ATR is used there too. Net: all 14 stops are 2x ATR.
- **Order type:** day limit at or below the refreshed reference price, entered after the first 30 minutes of the session. No market orders, nothing at the open.
- Computed with a short Python snippet against `_data_cache/quant_team_state_2026-11-20.pkl` (`close`, `factors.dollar_vol`).

## Order table by tranche (all BUY, limit)

Limit reference = snapshot price. Stop distance % is from the reference. "R at target" is the loss at the stop on the full position, in units of $1,000.

| Ticker | Sector | Total sh | T1 | T2 | T3 | Limit ref | MA50 | ATR(20) proxy | Stop | Stop dist % | R at target | T1 $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ABNB | Trading | 11 | 4 | 4 | 3 | 169.84 | 169.64 | 4.34 | 161.15 | 5.11 | 0.096 | 679 |
| AAPL | Hyperscaler | 5 | 2 | 2 | 1 | 341.33 | 341.56 | 4.63 | 332.07 | 2.71 | 0.046 | 683 |
| XOM | Rotation | 12 | 4 | 4 | 4 | 159.61 | 168.37 | 2.75 | 154.11 | 3.45 | 0.066 | 638 |
| UPS | Trading | 18 | 6 | 6 | 6 | 105.90 | 100.20 | 1.95 | 102.00 | 3.68 | 0.070 | 635 |
| CVX | Rotation | 9 | 3 | 3 | 3 | 208.17 | 213.71 | 3.01 | 202.15 | 2.89 | 0.054 | 625 |
| BRK-B | Rotation | 1 | 1 | 0 | 0 | 567.20 | 536.81 | 5.47 | 556.27 | 1.93 | 0.011 | 567 |
| META | Hyperscaler | 2 | 1 | 1 | 0 | 559.84 | 676.58 | 13.11 | 533.62 | 4.68 | 0.052 | 560 |
| WMT | Rotation | 11 | 4 | 4 | 3 | 127.96 | 116.65 | 1.45 | 125.06 | 2.27 | 0.032 | 512 |
| MSFT | Hyperscaler | 4 | 1 | 1 | 2 | 481.83 | 518.82 | 9.68 | 462.46 | 4.02 | 0.077 | 482 |
| PANW | Software | 4 | 1 | 1 | 2 | 343.22 | 367.42 | 11.74 | 319.74 | 6.84 | 0.094 | 343 |
| ANET (gate override) | AI Infrastructure | 6 | 2 | 2 | 2 | 166.12 | 191.98 | 8.82 | 148.47 | 10.62 | 0.106 | 332 |
| TSM (gate override) | Semis | 5 | 1 | 2 | 2 | 319.74 | 422.13 | 13.97 | 291.79 | 8.74 | 0.140 | 320 |
| LLY | Health | 1 | 0 | 1 | 0 | 1,347.02 | 1,265.58 | 21.61 | 1,303.80 | 3.21 | 0.043 | 0 |
| ASML (gate override) | Semis | 1 | 0 | 1 | 0 | 1,261.13 | 1,623.25 | 48.16 | 1,164.81 | 7.64 | 0.096 | 0 |
| COST | Rotation | 0 | - | - | - | 1,102.38 | 985.79 | 12.59 | n/a | n/a | 0 | 0 |
| **Total** | | | | | | | | | | | **0.98R** | **6,376** |

### How indivisible positions were handled

- **COST: no order.** The 0.97% target ($970) is less than one share ($1,102), so the position rounds to 0 shares and the money stays in cash. Buying one share would be 1.10% of capital, above the target, and the stock has an inferred (unconfirmed) report on 2026-12-10. Left for the PM to decide.
- **One-share positions cannot be split.** Rule used: a single share goes in tranche 1 only if it costs no more than 1% of capital; otherwise it waits for tranche 2, so that no name is bought in full on day one.
  - BRK-B ($567, 0.57%): tranche 1. Lowest-volatility name, above MA50.
  - LLY ($1,347, 1.35%): held for tranche 2. Buying it now would be the full position in one fill.
  - ASML ($1,261, 1.26%): held for tranche 2. It is a gate-override name and the top risk contributor, so it does not get a full-size entry against the gate.
- **2-5 share positions:** tranche 1 is the smaller part (1 of 2, 1 of 4, 1 or 2 of 5). Gate-override TSM is split 1/2/2, the lighter end first. META (2 shares) is split 1/1/0.
- Tranche 1 therefore ranges from 20% to 50% of each traded name instead of an exact third; in aggregate it is 31% of the achievable book.

## R budget (playbook 10)

R = 1% of capital = $1,000. Limits: total open risk <= 6R, same sector <= 2R.

| Sector | Tranche 1 | Full target |
|---|---|---|
| Semis | 0.03R | 0.24R |
| Hyperscaler | 0.06R | 0.18R |
| Trading | 0.06R | 0.17R |
| Rotation | 0.06R | 0.16R |
| AI Infrastructure | 0.04R | 0.11R |
| Software | 0.02R | 0.09R |
| Health | 0.00R | 0.04R |
| **Total** | **0.27R** | **0.98R** |

- **Result: passes with wide margin.** 0.98R of 6R in total; the largest sector is 0.24R of 2R. Nothing was scaled down for the R budget.
- Playbook 10's formula (position % = 1% / stop distance %) would allow positions of 9% to 52% of capital per name. The PM weights (1.0-2.0%) are far smaller and are the binding constraint.
- Caveat: this is the loss if every stop fills at its level. With VIX ~37 and a holiday-thinned week, gaps through stops are likely; the memo's own stress (sleeve beta ~1, about -2.5% of capital on a further -10% QQQ move at full size) is the better worst-case figure.
- After a position is 2R in profit, move the stop to breakeven and hand it to playbook 8 (exit only on a high-volume close below MA20). Only WMT and COST are above their MA20 today, so playbook 8 is not yet the active exit for any tranche-1 name; the 2x ATR stop is.

## Earnings blackout (5 trading days, through 2026-11-30)

- **No holding has a confirmed report inside the window.** Nothing is held back for earnings.
- Recently reported, risk behind them: WMT (Nov 19), PANW (Nov 18), ANET (Nov 3), AAPL (Nov 2).
- **Most dates are unverified.** The views files list "unknown" for LLY, ABNB, MSFT, AAPL, CVX, XOM, UPS, META, ASML, PANW, BRK-B, ANET (expected late January to February where stated). Confirm on company IR pages before sending tranche 1.
- Outside the window: COST 2026-12-10 (inferred), TSM November monthly revenue ~2026-12-10.
- Macro events in the holding window: flash PMIs Nov 23; Dell earnings Nov 24 (AI server read-through for ANET/TSM/ASML); PCE and Q3 GDP Nov 25; Thanksgiving closure Nov 26; half day Nov 27; payrolls Dec 4; FOMC Dec 9; CPI Dec 10.

## Liquidity

No flags. The largest full-size order is $1,927 (MSFT); the largest share of 60-day median daily dollar volume is UPS at 0.0004%. Every order is far below the 1% threshold.

## Rebalance

Not applicable: no holdings were supplied, `exits` is empty. Every order is at least 0.5% of capital except the single TSM, ANET and PANW tranche-1 lots (0.32-0.34%), which are kept because they are parts of staged positions, not rebalance trims. Turnover if all three tranches fill: 20.9% of capital, one way.

## Conditions that release tranches 2 and 3

Every condition listed for a tranche must be met on closing prices; share counts are recomputed at the time.

**Tranche 2 ($8,737)** — all of:
1. Not before the Oct PCE release on 2026-11-25, and core PCE prints below +0.4% m/m (macro desk: no adds before PCE).
2. The first PM add-risk trigger: VIX front month in contango (VIX < VIX3M) and VIX below 28 for two consecutive closes.
3. No cut trigger active (below).
4. Per name: added only if the tranche-1 lot is at or above its fill price (playbook 11, never average down). LLY and ASML have no tranche-1 lot; they need conditions 1-3 and a close at or above today's reference price (1,347.02 and 1,261.13), with the stop recomputed from the fill.

**Tranche 3 ($5,755)** — all of:
1. The second PM add-risk trigger: QQQ closes back above its MA50 with universe breadth above 40%. QQQ is 14.6% below MA50 and breadth is 11%, so this is not close.
2. Tranche 2 filled and the position in profit; stop on the earlier lots moved to at least cost.
3. No cut trigger active.

If only the QQQ/breadth trigger fires first, it releases tranche 2 and the VIX trigger then releases tranche 3: one tranche per trigger, in whichever order they arrive.

**Cut triggers (cancel all unfilled tranches; PM cuts the cap to 15%):** VIX closes above 40 while the curve is inverted; high-yield index spread above 4%; 30-year yield above 5.5%; an AI-credit default or missed payment; core PCE at or above +0.4% m/m on Nov 25. Tranche 1 alone (6.4%) and tranches 1+2 (15.1%) are at or near the 15% cap, so a cut trigger means tranche 3 is cancelled and tranche 2 is trimmed or skipped.

## Items for the PM

1. Confirm that the 25% decision is an acceptance of the QQQ gate for the 11 names other than TSM, ASML and ANET. Until then tranche 1 is not sent.
2. Rounding leaves the book at 20.9% rather than 25%, and tranche 3 depends on a QQQ recovery of about 17%. At $100k the plan realistically sits at 6-15% invested for some time.
3. COST: 0 shares. Accept, or approve one share at 1.10%.
4. LLY and ASML single shares deferred to tranche 2. Say if LLY (defensive, above MA50) should go in tranche 1 instead; that would lift tranche 1 to $7,723.
5. Stops use a close-only ATR proxy. A feed with highs and lows would widen them.

Research output only. Not investment advice. No orders were placed.
