# DNS Crypto Trading Bot

A deliberately small, testable BTC/ETH demand-and-supply trading desk.

## Current scope
- Exchange market data through CCXT (public OHLCV; no credentials required).
- Two separate zone detectors:
  1. Three-candle FVG zones (your shared rules).
  2. Base/leg zones (DBR, RBR, RBD, DBD) inspired by the supplied ebook.
- Touch-candle confirmation signals.
- Risk/position sizing helpers.
- Streamlit monitoring dashboard.
- Paper-only by default. No live order placement is implemented.

## Important strategy conventions
- FVG demand: candle 3 low > candle 1 high. The zone is candle 1 high-to-low, per your notes.
- FVG supply: candle 3 high < candle 1 low. The zone is candle 1 high-to-low.
- Base/leg zones use proximal/distal boundaries around the base. A leg candle body/range >= 75%; a base candle body/range <= 50%; base has 1–5 candles. Relative range expansion is also checked against a configurable rolling median.
- Long confirmation: after price touches demand, track the lowest-low touch candle; a later closed candle must close above that touch candle's high. Short logic is mirrored.
- Signals are generated only on closed candles. Ambiguous same-candle SL/TP outcomes are not simulated as wins.

These are explicit, configurable interpretations for backtesting—not claims of institutional order-flow visibility. Validate them against historical data before risking capital.

## Quick start
Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard fetches public candles from OKX by default. Change the exchange/symbol/timeframe in the sidebar. For Delta Exchange, select the CCXT exchange id only if supported in your installed CCXT version and verify the correct market symbol first.

## Historical backtest\n\nThe GitHub Actions workflow runs a 365-day BTC/USDT 15-minute backtest on changes to the strategy and uploads candle, trade and metrics files as an artifact. It compares strict 3R, balanced 2R and looser 2R filters. Open Actions → DNS historical backtest → Artifacts to inspect the results. The workflow can also be started manually for another CCXT symbol and history length.\n\nThe score is a transparent rule-based ranking, not machine learning or a win-probability estimate. The backtest is a first research pass, not proof of profitability.\n\n## Configuration
Copy `.env.example` to `.env` only if you later add private API access. Never commit API keys. This starter does not read or need API credentials.

## Safety
- Paper mode only.
- No live execution, leverage, or automated credential handling.
- Add fees, slippage, funding and exchange contract specifications to any backtest before evaluating profitability.
- Start with BTC/USDT and ETH/USDT spot/perpetual market data consistently; do not mix contract price series.

## Project layout
- `dns_bot/zones.py`: FVG and base/leg zone detection.
- `dns_bot/signals.py`: touch and confirmation state logic.
- `dns_bot/risk.py`: risk sizing and R-multiple calculations.\n- `dns_bot/backtest.py`: paginated historical candles, causal zone retests, conservative SL/TP handling, fees/slippage and strategy comparisons.
- `dns_bot/data.py`: public OHLCV fetching.
- `app.py`: Streamlit market desk.
- `tests/`: deterministic unit tests.
