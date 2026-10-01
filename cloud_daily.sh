#!/usr/bin/env bash
# Daily post-close run for the cloud routine. Band engines MUST run before trade_plan_charts.py.
set -u; export PYTHONIOENCODING=utf-8 MPLBACKEND=Agg; D=$(date +%F)
run(){ echo "--- $1"; python "$@" 2>&1 | tail -4; }
run bollinger_top_strategy.py; run bollinger_bottom_strategy.py
run stock_analysis.py; run technical_macd_volume_strategy.py; run crypto_derivs.py; run market_internals.py; run long_term_strategy.py; run earnings_plays.py
run trade_plan_charts.py
run whale_options_strategy.py || true
echo "== outputs =="; ls -la *_"$D".* 2>/dev/null
