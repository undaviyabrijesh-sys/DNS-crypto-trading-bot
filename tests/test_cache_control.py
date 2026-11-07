import pytest

from dns_bot.cache_control import clear_data_caches


class CachedFunction:
    def __init__(self):
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1


def test_explicit_refresh_clears_every_market_data_cache():
    ticker = CachedFunction()
    orderbook = CachedFunction()
    trades = CachedFunction()

    clear_data_caches(ticker, orderbook, trades)

    assert [ticker.clear_calls, orderbook.clear_calls, trades.clear_calls] == [1, 1, 1]


def test_cache_clear_rejects_uncached_callable_to_avoid_silent_stale_data():
    with pytest.raises(TypeError, match="clear"):
        clear_data_caches(lambda: None)
