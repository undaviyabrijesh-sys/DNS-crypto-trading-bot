# DNS Crypto Trading Bot

A paper-only BTC/ETH market desk with a Streamlit terminal, public market data, supply/demand research tools, and deterministic tests.

## Current dashboard

- `app.py` is the SALTY TRADES Streamlit terminal. It uses **Delta Exchange India public REST endpoints** for completed OHLCV candles, ticker, level-2 order book, and recent trades.
- The dashboard currently offers `BTCUSD` and `ETHUSD`, with selectable chart timeframes and history length. Delta India is fixed in the app; there is no exchange selector.
- The dashboard is read-only. It does not connect to private account data and does not place orders.
- The chart uses a dark TradingView-inspired workspace with candles, volume, EMA overlays, and price-bounded supply/demand drawings.
- The dashboard currently displays base/leg and confirmed swing-origin zones. The FVG detector remains available as a research helper but FVG display is disabled in the dashboard.
- The explicit **REFRESH MARKET** button clears the cached ticker, order-book, and recent-trade snapshots before fetching fresh market data.

## Data sources

- `dns_bot/delta_data.py`: public Delta India candle-history requests used by the dashboard.
- `dns_bot/delta_market.py`: public Delta India ticker, L2 order-book, and recent-trade requests.
- `dns_bot/data.py`: public CCXT OHLCV helper, defaulting to Binance `BTC/USDT` at 5m. This is separate from the Delta dashboard feed; do not mix instruments or contract types in one backtest.
- No API keys or exchange credentials are required for these public-data paths.

## Zone and entry conventions

- FVG helper: a three-candle gap is bounded by the space between candle 1 and candle 3. It is not currently drawn in the dashboard.
- Base/leg defaults: compact base candles have body/range at most 55%; incoming leg body/range is at least 60%; base length is 1–6 candles; outgoing displacement can span 1–3 candles and must exceed the rolling-median range expansion filter.
- Confirmed swing-origin zones use the full high-low range of the pivot candle and are only available after the right-side confirmation candles close.
- Zone lifecycle tracks touches, defended reactions, close-through invalidation, and SBR/RBS flips. A wick through a zone is not, by itself, a close-confirmed break.
- The 15m/3m entry module uses only a completed 15m zone after its formation/confirmation candle has closed. Demand confirmation requires a later 3m close above the high of the lowest-low touch candle; supply confirmation mirrors this using the highest-high touch candle. Entry is the following 3m open. A missing 3m candle resets the touch sequence, and a missing next bar prevents an entry from being inferred.
- The entry module places its stop beyond the 15m zone distal boundary with a 0.25 × 3m ATR buffer and calculates a 2R first target. A nearby opposing zone is used as a runner target only when it offers at least 2R.
- Signals are based on closed candles. In the OHLC backtest, if stop and target are both touched in one candle, stop is assumed first.

These are explicit, configurable chart interpretations—not claims of institutional order-flow visibility or a proven trading edge. Validate any strategy against chronological out-of-sample data and realistic costs before considering capital.

## Historical research

The backtest module compares rule-based zone retests and exposes fee/slippage assumptions. Scores are transparent ranking points, not machine-learning probabilities or win probabilities. A backtest is a research result, not proof of future profitability; include spread, funding, contract specifications, and realistic execution costs when relevant.

## Quick start

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Safety and known app limitations

- Paper/read-only only. No live execution, leverage, or credential handling is implemented.
- Manual trade plans are currently held in Streamlit session state; they are not yet a durable cross-session paper-position ledger.
- The dashboard refresh is user-triggered; it is not an unattended streaming terminal.
- Historical spread/depth and executable market impact must not be inferred from a single L2 snapshot.
- Keep spot and perpetual price series, contract multipliers, and settlement conventions separate.

## Project layout

- `app.py`: SALTY TRADES Streamlit dashboard.
- `dns_bot/delta_data.py`: Delta India public candle history.
- `dns_bot/delta_market.py`: Delta India public ticker, order book, and trade tape.
- `dns_bot/data.py`: CCXT public OHLCV helper.
- `dns_bot/zones.py`: FVG, base/leg, swing-origin, and zone-lifecycle logic.
- `dns_bot/entries.py`: causal 15m-zone / 3m touch-confirmation entry candidates.
- `dns_bot/risk.py`: basic linear position sizing and R-multiple helpers.
- `dns_bot/backtest.py`: causal OHLC backtest with conservative stop/target handling and fee/slippage inputs.
- `dns_bot/journal.py`: descriptive trade-journal metrics and sample-size warnings.
- `tests/`: deterministic unit tests.
