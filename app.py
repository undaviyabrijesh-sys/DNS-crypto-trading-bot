from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from dns_bot.data import fetch_ohlcv
from dns_bot.zones import detect_fvg_zones, detect_base_leg_zones

st.set_page_config(page_title="DNS Trader", layout="wide")
st.title("DNS Trader")
st.caption("BTC / ETH • Supply & Demand research desk • Public market data • Paper-only")

with st.sidebar:
    st.header("Market")
    exchange_id = st.selectbox("Exchange", ["binance", "bybit", "okx"], index=0)
    symbol = st.selectbox("Pair", ["BTC/USDT", "ETH/USDT"])
    timeframe = st.selectbox("Timeframe", ["1m", "3m", "5m", "15m", "1h", "4h"], index=2)
    limit = st.slider("Candles", 100, 1000, 500, 50)
    detector = st.selectbox("Zone detector", ["Both", "FVG", "Base / Leg"])
    refresh = st.button("Fetch latest candles", type="primary")

if "candles" not in st.session_state or refresh:
    try:
        st.session_state.candles = fetch_ohlcv(exchange_id, symbol, timeframe, limit)
        st.session_state.load_error = None
    except Exception as exc:
        st.session_state.load_error = str(exc)

if st.session_state.get("load_error"):
    st.error(f"Market data unavailable: {st.session_state.load_error}")
    st.stop()

df = st.session_state.candles
zones = []
if detector in ("Both", "FVG"):
    zones.extend(detect_fvg_zones(df))
if detector in ("Both", "Base / Leg"):
    zones.extend(detect_base_leg_zones(df))

left, mid, right = st.columns(3)
left.metric("Last price", f"{df.close.iloc[-1]:,.2f}")
mid.metric("Candles loaded", f"{len(df):,}")
right.metric("Zones detected", f"{len(zones):,}")

fig = go.Figure(data=[go.Candlestick(
    x=df.timestamp, open=df.open, high=df.high, low=df.low, close=df.close,
    name=symbol
)])
for zone in zones[-30:]:
    color = "rgba(0,170,100,0.18)" if zone.kind == "demand" else "rgba(220,60,60,0.18)"
    fig.add_hrect(y0=min(zone.distal, zone.proximal), y1=max(zone.distal, zone.proximal), fillcolor=color,
                  line_width=1, annotation_text=f"{zone.kind.upper()} · {zone.method} · {zone.pattern}",
                  annotation_position="top left")
fig.update_layout(height=680, xaxis_rangeslider_visible=False,
                  template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Detected zones")
if zones:
    st.dataframe([z.to_dict() for z in sorted(zones, key=lambda z: z.created_at, reverse=True)],
                 use_container_width=True, hide_index=True)
else:
    st.info("No zones detected with the current mechanical definitions.")

st.warning("Research/paper mode only. This version does not place orders. Validate zone definitions, fees, slippage, funding and exchange contract sizing before any live deployment.")
