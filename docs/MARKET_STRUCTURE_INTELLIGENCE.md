# SALTY TRADES — Market Structure Intelligence

This module extends the existing Delta-based research terminal. It does not replace
the current zone detector, data collector, journal, or paper-trading safeguards.

## First implementation slice

- Reuses `dns_bot.delta_data.fetch_delta_history` for completed Delta OHLCV.
- Reuses `dns_bot.zones.Zone` and the existing base/leg + swing-origin detector.
- Adds confirmed swing, BOS, and CHoCH event detection in `dns_bot.structure`.
- Adds conditional pullback/rejection scenarios in `dns_bot.scenarios`.

## Causality and safety rules

- A swing is not available until its right-side confirmation candles have closed.
- BOS/CHoCH uses candle closes beyond the latest confirmed swing.
- Scenarios are conditional research plans, not forecasts or orders.
- A long plan requires an active demand zone below current price; a short plan
  requires an active supply zone above current price.
- Stops sit beyond the zone distal edge with a small volatility-independent
  structural buffer. Targets use opposing active zones.
- No API credentials or order execution are used.

## Next integration

1. Add BOS/CHoCH markers and scenario paths to the Plotly chart.
2. Add multi-timeframe context (1h structure, 15m zones, 3m confirmation).
3. Backtest each scenario with candle-by-candle touch, stop, and target handling,
   including fees, slippage, and conservative same-candle ambiguity.
4. Expose the analysis in the Streamlit dashboard after deterministic tests pass.
