from dns_bot.cache_control import clear_market_candles_on_key_change


def test_market_key_change_clears_old_candles_and_error_before_fetch():
    old_candles = object()
    state = {
        "market_key": ("BTCUSD", "15m", 1500),
        "market_candles": old_candles,
        "market_error": "previous request failed",
    }

    changed = clear_market_candles_on_key_change(state, ("ETHUSD", "1h", 500))

    assert changed is True
    assert "market_candles" not in state
    assert "market_key" not in state
    assert "market_error" not in state


def test_same_market_key_preserves_existing_candles():
    old_candles = object()
    state = {
        "market_key": ("BTCUSD", "15m", 1500),
        "market_candles": old_candles,
    }

    changed = clear_market_candles_on_key_change(state, ("BTCUSD", "15m", 1500))

    assert changed is False
    assert state["market_candles"] is old_candles
