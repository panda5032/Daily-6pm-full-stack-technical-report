---
name: quant-team
description: Run the full quant team to build or rebalance an optimised stock portfolio from AI_Portfolios.xlsx - screen, parallel research (fundamental, AI sector, macro), optimise, independent risk review, PM decision, order plan. Use when asked to "run the quant team", "build the portfolio", "rebalance", or for the team's view on what to own.
---

# Quant team run

You are the coordinator. Subagents cannot spawn each other, so you run the desks in order and pass files between them. The desks are defined in `.claude/agents/`; the numbers come from `quant_team.py`. Arguments (optional): capital in dollars (default 100000), a holdings CSV (`ticker,shares`) for a rebalance, `--include-crypto`.

Team: `stock-picker`, `stock-research-analyst`, `ai-stocks-research-analyst`, `macro-strategist`, `quant-researcher`, `risk-manager`, `quant-portfolio-manager`, `execution-trader`.

## Pipeline

**0. Setup** - `python -m pip install -q -r requirements.txt`.

**1. Screen** (stock-picker) - runs `python quant_team.py screen`, audits the ranking, writes `quant_team_picks_<date>.md`. If the engine reports DATA OUTAGE, stop the whole run and tell the user which hosts are blocked (Yahoo Finance hosts must be allowed in the environment's network settings). Never continue on stale or remembered prices.

**2. Research, in parallel** - launch these three in one message, each told the date and the candidates file:
- `stock-research-analyst` -> `quant_team_views_stock-research_<date>.json`
- `ai-stocks-research-analyst` -> `quant_team_views_ai-research_<date>.json`
- `macro-strategist` -> `quant_team_views_macro_<date>.json`

At the same time `quant-researcher` runs `python quant_team.py backtest` and reports which construction method the evidence supports.

**3. Optimise** - `python quant_team.py optimize --views quant_team_views_*_<date>.json --capital <capital> [--holdings <csv>]`. If the AI analyst listed `add_back` names, tell the PM; they are only added if the PM asks and the engine's eligibility allows.

**4. Risk review** (risk-manager) - independent review of `quant_team_portfolio_<date>.json`. On PASS WITH CHANGES or FAIL, apply the required changes (its vetoes/caps file is picked up by the same `--views` glob) and re-run step 3, then have the risk manager confirm. Maximum two loops; if it still fails, report that to the user rather than forcing a pass.

**5. Decision** (quant-portfolio-manager) - writes `quant_team_memo_<date>.md`.

**6. Orders** (execution-trader) - writes `quant_team_orders_<date>.md`. Plan only; nothing is ever executed.

**7. Report to the user** - exposure and cash, the portfolio table, the main judgement calls and desk disagreements, risk verdict, what would trigger adding or cutting risk, and the caveats (model estimates, biased backtest, intraday snapshot if flagged). Then persist: `git add -f quant_team_*_<date>.json quant_team_*_<date>.md`, commit as `quant team <date>`, push.

## Standing rules
- Every number traces to an engine file or a cited source. Missing data is reported as missing.
- Exposure is the minimum of the regime cap, the vol-target cap and any desk's cap. No desk can raise it.
- A risk-manager veto or limit failure is binding.
- Research output, not investment advice. No orders are placed by anyone on this team.
