import pandas as pd
import pytest

from dns_bot.delta_data import _resolution_seconds, fetch_delta_history


def test_resolution_seconds():
    assert _resolution_seconds("15m") == 900
    assert _resolution_seconds("4h") == 14400
    assert _resolution_seconds("1d") == 86400


def test_delta_history_normalizes_and_deduplicates(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"success": True, "result": [
                {"time": 1700000000, "open": "1", "high": "3", "low": "0.5", "close": "2", "volume": "10"},
                {"time": 1700000000, "open": "1", "high": "3", "low": "0.5", "close": "2", "volume": "10"},
            ]}
    class Session:
        def __init__(self):
            self.headers = {}
        def get(self, *args, **kwargs):
            return Response()
    monkeypatch.setattr("dns_bot.delta_data.requests.Session", Session)
    # End time far enough after the sample candle, but short request window.
    df = fetch_delta_history("BTCUSD", "15m", days=1, end_time=1700005000)
    assert len(df) == 1
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert df.iloc[0]["close"] == 2


def test_invalid_resolution_rejected():
    with pytest.raises(ValueError):
        fetch_delta_history("BTCUSD", "2m", days=1)
