# Quant team memo — 2026-11-20 (first run)

**Status: provisional.** Prices are an intraday snapshot taken ~3:52pm ET, eight minutes before the close. Re-run `python quant_team.py screen` and `optimize` on closing prices before acting.

Desks that ran as separate agents: stock research, AI-stocks research, macro. The stock-picker audit, risk review and PM decision in this memo were done by the coordinating session, not by separate agents.

## Decision
- **25% invested, 75% cash.** Regime is RISK-OFF (SPY and QQQ below MA50 and MA200, VIX ~37, 12% of the universe above MA50). The engine's cap is 35%; the macro desk lowered it to 25%.
- **15 names, ~1–2% each**, max-Sharpe under the standard limits. All five hard risk limits pass.
- **Biggest judgement call:** holding small positions in TSM, ASML and ANET, which are 13–24% below their 50-day averages, on the AI desk's view that this is a funding and de-rating shock on intact earnings. This runs against the house QQQ-below-MA50 gate, so they are sized at 1.1–1.7% and should be entered in three tranches.

## Portfolio ($100,000)
See `quant_team_portfolio_2026-11-20.md` for the full table: LLY, ABNB, MSFT, XOM, AAPL, CVX, UPS 2.0% each; TSM 1.7%, ASML 1.7%, META 1.6%, WMT 1.5%, PANW 1.4%, BRK-B 1.2%, ANET 1.1%, COST 1.0%.

At $100k the COST position rounds to zero shares (one share costs more than the 1% target).

## What research changed versus the pure quant portfolio
- **Out:** USO (view −1: oil momentum is an unwinding war premium), OSCR (growth flattered by a one-off gain; "FCF yield" is insurer float), JNJ, OKTA, AMD, XLU (neutral views, displaced).
- **In:** TSM, ASML, ANET, WMT, BRK-B (positive views).
- Not selected despite ranking: GME (−1, momentum from a bid saga), UNH (−1, Medicare Advantage clawback rule), TEAM (−1, guide cut).
- AI desk add-backs MU and GOOGL were **not** added: MU is excluded as a falling knife, and no limit is loosened on a first run.

## Desk disagreements
- **Semis:** quant theme score ranks the layer near the bottom on trailing price; the AI desk ranks it first on fundamentals. Resolved by small size, not by picking a side.
- **Oil:** quant ranks CVX and XOM at the top; stock research is neutral (peak-cycle earnings, crude falling). They stay at 2% each as the optimiser values their negative correlation to tech.
- **META:** quant positive, AI desk neutral (equity-funding its capex). Kept at 1.6%.

## Risk review
- Engine figures: ex-ante vol 3.3%, beta 0.19 to SPY, 1-day VaR95 0.3%, QQQ −10% shock −1.1%.
- **These understate the risk.** The low beta leans on CVX and XOM having a beta near −0.5 over the past year, which comes from an oil spike coinciding with a tech selloff. If oil falls with equities, the hedge disappears. Treating the invested sleeve as beta ~1 gives roughly −2.5% on a further −10% QQQ move and −6% on −25%.
- Top risk contributors are ASML, TSM, ABNB, ANET and PANW (58% of variance from 8% of capital).
- Event risk: PCE and GDP on Nov 25, payrolls Dec 4, FOMC Dec 9 (a hike is largely priced), CPI Dec 10. None of the 15 holdings has a confirmed earnings date in the next week; most dates could not be verified.

## Triggers
- **Add risk toward 35% and beyond:** QQQ back above MA50 with breadth above 40%; VIX in contango and below 28 for two closes.
- **Cut to 15%:** VIX closes above 40 while inverted; high-yield spread above 4%; 30-year yield above 5.5%; an AI-credit default.

## Caveats
- Model return (6.1%/yr) is an estimate from assumed information coefficients, not a forecast.
- The backtest (selection beat the equal-weight universe by about 13 points a year, 2023-12 to 2026-11) is flattered by a hindsight universe and excludes fundamentals and analyst views.
- The research desks could not open primary pages (web fetch was blocked), so their facts come from search summaries and several figures are flagged unverified in their files.

Research output only. Not investment advice. No orders were placed.
