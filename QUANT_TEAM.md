# Quant team

Eight Claude Code agents plus one deterministic engine that together build a risk-controlled, optimised stock portfolio from `AI_Portfolios.xlsx`. Run it with `/quant-team` (optionally: capital, a holdings CSV).

| Desk | Agent (`.claude/agents/`) | Produces |
|---|---|---|
| Portfolio manager | `quant-portfolio-manager` | final decision, `quant_team_memo_<date>.md` |
| Stock picker | `stock-picker` | audited ranking, `quant_team_picks_<date>.md` |
| Stock research | `stock-research-analyst` | views on non-AI names |
| AI stocks research | `ai-stocks-research-analyst` | AI-cycle call + views on the AI value chain |
| Macro strategist | `macro-strategist` | gross-exposure cap, calendar |
| Quant researcher | `quant-researcher` | optimiser, backtest, model changes |
| Risk manager | `risk-manager` | independent review, binding vetoes |
| Execution trader | `execution-trader` | staged order plan (never places orders) |

## Flow

```
stock-picker ──screen──► candidates.json
        ├─► stock-research-analyst ─┐
        ├─► ai-stocks-research ─────┼─► views_*.json ─► quant_team.py optimize ─► portfolio.json
        ├─► macro-strategist ───────┘                         ▲          │
        └─► quant-researcher (backtest)                       │          ▼
                                             vetoes / caps ◄── risk-manager
                                                                         │
                                  quant-portfolio-manager (memo) ◄───────┘──► execution-trader (orders)
```

Agents supply judgement as structured views (`view` −2..+2, `conviction` 0..1), vetoes and an exposure cap. `quant_team.py` supplies every number.

## Engine (`quant_team.py`)

```bash
python quant_team.py screen                                   # data QA, regime, factors, fundamentals, ranking
python quant_team.py optimize --views quant_team_views_*.json --capital 100000 [--holdings h.csv]
python quant_team.py backtest                                 # walk-forward, all construction methods
```

- **Alpha**: risk-adjusted momentum (12-1, 6-1, 3m), trend, low risk, relative strength vs QQQ, AI-theme strength, blended 65/35 with growth / quality / value from reported quarterly statements.
- **Expected return**: `beta × ERP + IC × vol × score`, plus `IC_view × vol × view` from the research desks.
- **Risk model**: 1-year covariance, Ledoit-Wolf shrinkage.
- **Construction**: long-only max-Sharpe; name ≤ 8%, sector ≤ 30%, no name > 15% of risk, ≥ 12 names.
- **Exposure**: min(regime cap, 25% vol target, any desk's cap). Risk-off regimes hold cash.
- **Filters**: 260+ bars, price ≥ $3, $20M+ daily dollar volume; falling knives (below MA200 and −25% in a month) are never new buys.

Policy constants are at the top of the file.

## Read the results honestly

- Model "expected return" rests on assumed information coefficients. It ranks portfolios; it is not a forecast.
- The backtest universe is today's hand-picked list (survivorship and hindsight bias) and uses price factors only. Compare methods with `EW universe`, not with SPY/QQQ.
- Yahoo's quote endpoint is rate-limited from cloud IPs, so the engine has no forward estimates or analyst targets; the research agents source those from the web.
- Research output only. Not investment advice. Nothing in this repo places an order.
