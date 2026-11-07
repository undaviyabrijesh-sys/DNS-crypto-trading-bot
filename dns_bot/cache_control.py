from __future__ import annotations


def clear_data_caches(*cached_functions) -> None:
    """Clear Streamlit cached-data callables before an explicit market refresh."""
    for cached_function in cached_functions:
        clear = getattr(cached_function, "clear", None)
        if not callable(clear):
            raise TypeError("every cached function must expose a callable clear() method")
        clear()
