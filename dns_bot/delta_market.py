from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.india.delta.exchange"


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}{path}",
        params=params or {},
        headers={"Accept": "application/json", "User-Agent": "salty-trades-terminal/1.0"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise RuntimeError(f"Delta API request failed: {payload}")
    return payload.get("result") or {}


def fetch_ticker(symbol: str = "BTCUSD") -> dict[str, Any]:
    return _get(f"/v2/tickers/{symbol}")


def fetch_orderbook(symbol: str = "BTCUSD", depth: int = 20) -> dict[str, Any]:
    return _get(f"/v2/l2orderbook/{symbol}", {"depth": depth})


def fetch_recent_trades(symbol: str = "BTCUSD") -> list[dict[str, Any]]:
    result = _get(f"/v2/trades/{symbol}")
    trades = result.get("trades", []) if isinstance(result, dict) else []
    return trades if isinstance(trades, list) else []
