from dns_bot import delta_market


def test_public_market_helpers_use_expected_endpoints(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path.startswith("/v2/tickers/"):
            return {"symbol": "BTCUSD", "close": "65000"}
        if path.startswith("/v2/l2orderbook/"):
            return {"buy": [], "sell": []}
        return {"trades": [{"side": "buy", "price": "65000", "size": 1}]}

    monkeypatch.setattr(delta_market, "_get", fake_get)
    assert delta_market.fetch_ticker("BTCUSD")["symbol"] == "BTCUSD"
    assert delta_market.fetch_orderbook("BTCUSD", 10)["buy"] == []
    assert delta_market.fetch_recent_trades("BTCUSD")[0]["side"] == "buy"
    assert calls == [
        ("/v2/tickers/BTCUSD", None),
        ("/v2/l2orderbook/BTCUSD", {"depth": 10}),
        ("/v2/trades/BTCUSD", None),
    ]


def test_recent_trades_handles_unexpected_payload(monkeypatch):
    monkeypatch.setattr(delta_market, "_get", lambda *args, **kwargs: {})
    assert delta_market.fetch_recent_trades("BTCUSD") == []
