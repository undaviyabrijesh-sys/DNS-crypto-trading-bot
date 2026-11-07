from __future__ import annotations


def clear_data_caches(*cached_functions) -> None:
    """Clear Streamlit cached-data callables before an explicit market refresh."""
    for cached_function in cached_functions:
        clear = getattr(cached_function, "clear", None)
        if not callable(clear):
            raise TypeError("every cached function must expose a callable clear() method")
        clear()

def clear_market_candles_on_key_change(session_state, market_key) -> bool:
    """Prevent a failed symbol/timeframe reload from displaying another market's candles."""
    if session_state.get("market_key") == market_key:
        return False
    session_state.pop("market_candles", None)
    session_state.pop("market_key", None)
    session_state.pop("market_error", None)
    return True
