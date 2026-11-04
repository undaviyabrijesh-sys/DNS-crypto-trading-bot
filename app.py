from __future__ import annotations

# Streamlit Cloud can launch the entrypoint from a working directory that does
# not reliably expose the repository root as an import path. Add it explicitly
# before importing the local dns_bot package.
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dns_bot.delta_data import fetch_delta_history
from dns_bot.delta_market import fetch_ticker, fetch_orderbook, fetch_recent_trades
from dns_bot.zones import detect_base_leg_zones, track_zone_lifecycle
from dns_bot.entries import find_entry_setups
from dns_bot.structure import detect_market_structure
from dns_bot.scenarios import generate_trade_scenarios
from dns_bot.journal import load_trades, learning_report


st.set_page_config(page_title="SALTY TRADES | Delta Terminal", page_icon="◈", layout="wide")

st.markdown("""
<style>
:root{
  --bg:#080b10;--panel:#101722;--panel2:#0d131c;--line:#202b38;
  --muted:#8290a2;--text:#dce5ef;--cyan:#31c8f2;--green:#14c784;
  --red:#f25f70;--amber:#f0b94b;--violet:#a78bfa;
}
html,body,[data-testid="stAppViewContainer"]{
  background:var(--bg);color:var(--text);
  font-family:ui-monospace,"Cascadia Code","SFMono-Regular",Consolas,monospace;
}
[data-testid="stHeader"]{background:rgba(8,11,16,.94);}
[data-testid="stSidebar"]{
  background:#0b1119;border-right:1px solid var(--line);
}
[data-testid="stSidebar"] *{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;}
.block-container{max-width:1920px;padding-top:.55rem;padding-bottom:1.25rem;}
h1,h2,h3,h4{color:#edf4fb!important;font-family:ui-monospace,Consolas,monospace!important;letter-spacing:.02em;}
h1{font-size:1.22rem!important;}
h2{font-size:1.04rem!important;}
h3{font-size:.94rem!important;}
p,li,label,span,div{font-variant-numeric:tabular-nums;}
div[data-testid="stMetric"]{
  background:linear-gradient(145deg,#121c29,#0d141e);
  border:1px solid #263445;border-radius:4px;padding:9px 12px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.025);
}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:.66rem!important;letter-spacing:.09em;text-transform:uppercase;}
[data-testid="stMetricValue"]{color:#eef6ff!important;font-family:ui-monospace,Consolas,monospace!important;font-size:1.12rem!important;}
[data-testid="stMetricDelta"]{font-family:ui-monospace,Consolas,monospace!important;font-size:.72rem!important;}
div[data-testid="stTabs"] button{
  color:#8796a9!important;font-family:ui-monospace,Consolas,monospace!important;
  font-size:.72rem!important;font-weight:700;letter-spacing:.045em;
  border-bottom:1px solid var(--line);
}
div[data-testid="stTabs"] button[aria-selected="true"]{
  color:var(--cyan)!important;border-bottom:2px solid var(--cyan)!important;
}
.stButton>button,.stDownloadButton>button{
  background:#111d2a;color:#dce8f4;border:1px solid #304153;border-radius:3px;
  font-family:ui-monospace,Consolas,monospace;font-size:.76rem;letter-spacing:.03em;
}
.stButton>button:hover,.stDownloadButton>button:hover{
  border-color:var(--cyan);color:var(--cyan);background:#142536;
}
[data-testid="stDataFrame"]{border:1px solid #263445;border-radius:3px;}
[data-testid="stDataFrame"] *{font-family:ui-monospace,Consolas,monospace!important;}
[data-testid="stSelectbox"] label,[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label,[data-testid="stNumberInput"] label,
[data-testid="stTextInput"] label{color:#94a4b8!important;font-size:.68rem!important;letter-spacing:.06em;text-transform:uppercase;}
hr{border-color:var(--line)!important;}
div[data-testid="stAlert"]{border-radius:3px;border:1px solid #2b394a;}
.small-label,.section-kicker{
  font-size:9px;letter-spacing:1.6px;color:#7d8da1;font-weight:800;
  margin:5px 0 9px;text-transform:uppercase;
}
.terminal-bar{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:9px 12px;margin:0 0 12px;background:#0d141e;
  border:1px solid #253344;border-left:3px solid var(--cyan);border-radius:3px;
}
.terminal-brand{color:#f2f7fd;font-size:13px;font-weight:900;letter-spacing:.1em;}
.terminal-product{color:#7f91a7;font-size:9px;letter-spacing:.13em;margin-left:12px;}
.terminal-meta{display:flex;align-items:center;gap:13px;color:#8292a6;font-size:9px;letter-spacing:.08em;}
.terminal-dot{display:inline-block;width:7px;height:7px;background:var(--green);border-radius:50%;box-shadow:0 0 8px rgba(20,199,132,.75);margin-right:5px;}
.terminal-pill{padding:3px 6px;border:1px solid #2a3b4e;border-radius:2px;color:#a9bbce;}
.market-head{
  display:flex;align-items:center;flex-wrap:wrap;gap:10px;
  padding:2px 0 10px;border-bottom:1px solid var(--line);margin-bottom:12px;
}
.market-symbol{font-size:21px;font-weight:900;letter-spacing:.04em;color:#f3f7fc;}
.market-tag{font-size:9px;color:var(--cyan);border:1px solid #15516a;padding:3px 7px;border-radius:2px;letter-spacing:.1em;}
.muted{color:#8290a2;font-size:10px;letter-spacing:.04em;}
.panel{background:var(--panel);border:1px solid #263445;border-radius:3px;padding:10px;margin-bottom:10px;}
.zone-readout{
  display:flex;flex-wrap:wrap;gap:7px;align-items:center;padding:8px 10px;
  margin:5px 0 12px;background:#0d141e;border:1px solid #202e3d;
  font-size:9px;letter-spacing:.08em;color:#91a2b6;
}
.zone-readout b{font-weight:900;}
.zone-demand{color:var(--green)!important}.zone-supply{color:var(--red)!important}
.zone-rbs{color:var(--cyan)!important}.zone-sbr{color:var(--amber)!important}
[data-testid="stCaptionContainer"]{color:#7f8fa3!important;font-size:.69rem!important;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=10, show_spinner=False)
def get_ticker(symbol: str):
    return fetch_ticker(symbol)


@st.cache_data(ttl=8, show_spinner=False)
def get_book(symbol: str):
    return fetch_orderbook(symbol, 20)


@st.cache_data(ttl=3, show_spinner=False)
def get_trades(symbol: str):
    return fetch_recent_trades(symbol)


def timeframe_minutes(tf: str) -> int:
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    return 1440

def zone_class(zone) -> str:
    """Return the user-facing zone family while keeping trade direction explicit."""
    pattern = str(getattr(zone, "pattern", "")).strip().upper()
    if pattern in ("RBS", "SBR"):
        return pattern
    return "DEMAND" if str(getattr(zone, "kind", "")).lower() == "demand" else "SUPPLY"


@st.cache_data(ttl=30, show_spinner=False)
def get_zones(df: pd.DataFrame, engine: str = "Base / Leg"):
    """Use only base/leg and confirmed swing-origin zones; FVG is disabled."""
    found = detect_base_leg_zones(df)
    return track_zone_lifecycle(df, found)


def build_chart(df: pd.DataFrame, zones: list, show_volume: bool = True,
                chart_style: str = "Candles", indicators: list[str] | None = None,
                show_zones: bool = True, structure_events: list | None = None,
                scenarios: list | None = None, candle_seconds: int = 900):
    """TradingView-inspired interactive chart with editable drawing tools."""
    rows = 2 if show_volume else 1
    heights = [0.80, 0.20] if show_volume else [1]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=.025,
                        row_heights=heights)

    if chart_style == "Candles":
        fig.add_trace(go.Candlestick(
            x=df.timestamp, open=df.open, high=df.high, low=df.low, close=df.close,
            name="BTCUSD", increasing_line_color="#0ecb81", decreasing_line_color="#f6465d",
            increasing_fillcolor="#0ecb81", decreasing_fillcolor="#f6465d",
        ), row=1, col=1)
    elif chart_style == "Line":
        fig.add_trace(go.Scatter(x=df.timestamp, y=df.close, mode="lines", name="Close",
                                 line=dict(color="#d8dee9", width=1.6)), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df.timestamp, y=df.close, mode="lines", name="Close",
                                 line=dict(color="#00c2ff", width=1.6),
                                 fill="tozeroy", fillcolor="rgba(0,194,255,.08)"), row=1, col=1)

    ema_colors = {"EMA 9": "#f0b90b", "EMA 20": "#00c2ff",
                  "EMA 50": "#b084f5", "EMA 200": "#ff8a65"}
    for label in indicators or []:
        period = int(label.split()[-1])
        if len(df) >= period:
            ema = df.close.ewm(span=period, adjust=False).mean()
            fig.add_trace(go.Scatter(x=df.timestamp, y=ema, mode="lines", name=label,
                                     line=dict(color=ema_colors.get(label, "#ffffff"), width=1.25)),
                          row=1, col=1)

    if show_volume and "volume" in df:
        volume_colors = ["#0ecb8180" if c >= o else "#f6465d80"
                         for o, c in zip(df.open, df.close)]
        fig.add_trace(go.Bar(x=df.timestamp, y=df.volume, marker_color=volume_colors,
                             name="Volume", showlegend=False), row=2, col=1)

    if show_zones:
        # Draw each zone as a price-bounded rectangle beginning at the candle
        # where its base formed. Do not use add_hrect: that paints the band
        # across the entire chart and hides the zone's actual origin.
        for zone in zones:
            if zone.status == "broken":
                continue
            demand = zone.kind == "demand"
            family = zone_class(zone)
            palette = {
                "DEMAND": ("rgba(20,199,132,.10)", "rgba(20,199,132,.82)"),
                "SUPPLY": ("rgba(242,95,112,.10)", "rgba(242,95,112,.82)"),
                "RBS": ("rgba(49,200,242,.13)", "rgba(49,200,242,.92)"),
                "SBR": ("rgba(240,185,75,.13)", "rgba(240,185,75,.92)"),
            }
            color, edge = palette[family]
            low, high = sorted((float(zone.distal), float(zone.proximal)))
            # Flip zones begin at the candle that broke the original level,
            # not at the much older candle that first formed that level.
            origin_index = zone.created_index if family in ("RBS", "SBR") else zone.base_start
            start_idx = max(0, min(len(df) - 1, int(origin_index)))
            x0 = df.timestamp.iloc[start_idx]
            x1 = df.timestamp.iloc[-1]
            if x0 >= x1:
                continue
            fig.add_shape(
                type="rect", x0=x0, x1=x1, y0=low, y1=high,
                xref="x", yref="y", fillcolor=color,
                line=dict(color=edge, width=1), layer="below",
            )
            label = f"{family} · {zone.pattern}" if family in ("DEMAND", "SUPPLY") else family
            fig.add_annotation(
                x=x0, y=high if demand else low, xref="x", yref="y",
                text=label, showarrow=False, xanchor="left",
                yanchor="bottom" if demand else "top",
                font=dict(size=8, color=edge), bgcolor="rgba(11,14,17,.72)",
            )

    # Confirmed structure labels are plotted only when their confirmation candle closes.
    if structure_events:
        visible_events = structure_events[-18:]
        for event in visible_events:
            x = df.timestamp.iloc[min(max(int(event.index), 0), len(df) - 1)]
            if event.event == "SWING_HIGH":
                fig.add_trace(go.Scatter(
                    x=[x], y=[event.level], mode="markers+text",
                    marker=dict(symbol="triangle-down", size=9, color="#f6465d"),
                    text=["SH"], textposition="top center",
                    textfont=dict(size=8, color="#f6465d"),
                    name="Confirmed swing high", showlegend=False,
                    hovertemplate="Confirmed swing high<br>Level: %{y:,.2f}<extra></extra>",
                ), row=1, col=1)
            elif event.event == "SWING_LOW":
                fig.add_trace(go.Scatter(
                    x=[x], y=[event.level], mode="markers+text",
                    marker=dict(symbol="triangle-up", size=9, color="#0ecb81"),
                    text=["SL"], textposition="bottom center",
                    textfont=dict(size=8, color="#0ecb81"),
                    name="Confirmed swing low", showlegend=False,
                    hovertemplate="Confirmed swing low<br>Level: %{y:,.2f}<extra></extra>",
                ), row=1, col=1)
            else:
                bullish = event.direction == "bullish"
                color = "#0ecb81" if bullish else "#f6465d"
                fig.add_annotation(
                    x=x, y=event.level, xref="x", yref="y",
                    text=event.event, showarrow=True, arrowhead=2,
                    arrowcolor=color, font=dict(size=9, color=color),
                    bgcolor="rgba(11,14,17,.88)", bordercolor=color,
                    ax=0, ay=-28 if bullish else 28,
                )

    # Conditional plans extend into future chart space; these are not live signals.
    if scenarios:
        future_x = df.timestamp.iloc[-1] + pd.Timedelta(seconds=candle_seconds * 20)
        for scenario in scenarios:
            bullish = scenario.side == "LONG"
            color = "rgba(14,203,129,.14)" if bullish else "rgba(246,70,93,.14)"
            edge = "#0ecb81" if bullish else "#f6465d"
            fig.add_shape(
                type="rect", x0=df.timestamp.iloc[-1], x1=future_x,
                y0=scenario.zone_low, y1=scenario.zone_high,
                xref="x", yref="y", fillcolor=color,
                line=dict(color=edge, width=1, dash="dot"), layer="above",
            )
            fig.add_annotation(
                x=future_x, y=(scenario.zone_low + scenario.zone_high) / 2,
                xref="x", yref="y", text=f"{scenario.side} WATCH · {scenario.zone_pattern}",
                showarrow=False, xanchor="right",
                font=dict(size=9, color=edge), bgcolor="rgba(11,14,17,.85)",
            )
            for label, level, dash in [("SL", scenario.stop, "dash")]:
                fig.add_shape(type="line", x0=df.timestamp.iloc[-1], x1=future_x,
                              y0=level, y1=level, xref="x", yref="y",
                              line=dict(color="#f6465d", width=1, dash=dash))
                fig.add_annotation(x=future_x, y=level, xref="x", yref="y",
                                   text=f"{label} {level:,.1f}", showarrow=False,
                                   xanchor="right", yshift=9,
                                   font=dict(size=8, color="#f6465d"))
            for target_no, level in enumerate(scenario.targets[:3], start=1):
                fig.add_shape(type="line", x0=df.timestamp.iloc[-1], x1=future_x,
                              y0=level, y1=level, xref="x", yref="y",
                              line=dict(color="#0ecb81" if bullish else "#f0b90b",
                                        width=1, dash="dot"))
                fig.add_annotation(x=future_x, y=level, xref="x", yref="y",
                                   text=f"T{target_no} {level:,.1f}", showarrow=False,
                                   xanchor="right", yshift=9,
                                   font=dict(size=8, color="#0ecb81" if bullish else "#f0b90b"))

    last = float(df.close.iloc[-1])
    fig.add_hline(y=last, line_dash="dot", line_color="#00c2ff", line_width=1,
                  annotation_text=f"{last:,.1f}", annotation_position="right",
                  row=1, col=1)
    fig.update_layout(
        height=820, template="plotly_dark", paper_bgcolor="#0b0e11", plot_bgcolor="#0b0e11",
        margin=dict(l=5, r=5, t=8, b=5),
        font=dict(family="Inter", color="#aeb7c2", size=10),
        hovermode="x unified", showlegend=bool(indicators),
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        dragmode="pan", uirevision="salty-trades-chart",
        xaxis=dict(showgrid=True, gridcolor="#1d232d", rangeslider_visible=False,
                   showspikes=True, spikemode="across", spikesnap="cursor",
                   rangeselector=dict(bgcolor="#131722", activecolor="#263747",
                       font=dict(color="#aeb7c2", size=9),
                       buttons=[
                           dict(count=1, label="1H", step="hour", stepmode="backward"),
                           dict(count=4, label="4H", step="hour", stepmode="backward"),
                           dict(count=1, label="1D", step="day", stepmode="backward"),
                           dict(count=7, label="1W", step="day", stepmode="backward"),
                           dict(count=1, label="1M", step="month", stepmode="backward"),
                           dict(step="all", label="ALL"),
                       ])),
        yaxis=dict(side="right", showgrid=True, gridcolor="#1d232d",
                   fixedrange=False, showspikes=True),
        xaxis2=dict(showgrid=True, gridcolor="#1d232d", showspikes=True),
        yaxis2=dict(side="right", showgrid=True, gridcolor="#1d232d"),
    )
    return fig

with st.sidebar:
    st.markdown("## ◈ SALTY TRADES")
    st.caption("DELTA EXCHANGE INDIA · MARKET TERMINAL")
    symbol = st.selectbox("CONTRACT", ["BTCUSD", "ETHUSD"], index=0)
    timeframe = st.selectbox("TIMEFRAME", ["1m", "3m", "5m", "15m", "30m", "1h", "4h"], index=3)
    candle_count = st.select_slider("CHART HISTORY", options=[250, 500, 750, 1000, 1500, 1999], value=1500)
    st.caption("15m chart: 1,500 candles ≈ 15.6 days")
    zone_engine = "Base / Leg"
    st.markdown("**SUPPLY / DEMAND: BASE / LEG ONLY**")
    st.caption("Includes base-leg formations and confirmed swing-candle zones. FVG is disabled.")
    show_volume = st.toggle("Show volume", value=True)
    refresh = st.button("↻  REFRESH MARKET", use_container_width=True, type="primary")
    st.markdown("---")
    st.caption("Public market data · Read-only · No orders sent")


# Instrument header and top-of-screen market statistics
st.markdown(
    '<div class="terminal-bar">'
    '<div><span class="terminal-brand">◈ SALTY TRADES</span>'
    '<span class="terminal-product">MARKET INTELLIGENCE TERMINAL / BUILD 02</span></div>'
    '<div class="terminal-meta"><span><i class="terminal-dot"></i>PUBLIC MARKET FEED</span>'
    '<span class="terminal-pill">READ ONLY</span><span>DELTA EXCHANGE INDIA</span></div></div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="market-head"><span class="market-symbol">{symbol}</span>'
    f'<span class="market-tag">PERPETUAL</span><span class="market-tag">DELTA INDIA</span>'
    f'<span class="muted">USD QUOTED</span><span class="muted">1H STRUCTURE / 15M ZONES / 3M CONFIRMATION</span></div>',
    unsafe_allow_html=True,
)

# A changed contract/timeframe always reloads the matching candle series.
market_key = (symbol, timeframe, candle_count)
if refresh or st.session_state.get("market_key") != market_key:
    # Force the latest zone algorithm to run when the user refreshes the market.
    get_zones.clear()
    st.session_state.pop("market_error", None)
    try:
        days = max(1, int((candle_count * timeframe_minutes(timeframe) + 1439) / 1440))
        with st.spinner(f"Loading {symbol} {timeframe} candles from Delta…"):
            candles = fetch_delta_history(symbol=symbol, timeframe=timeframe, days=days)
        candles = candles.tail(candle_count).reset_index(drop=True)
        if candles.empty or len(candles) < 3:
            raise RuntimeError("Delta returned fewer than 3 completed candles.")
        st.session_state["market_candles"] = candles
        st.session_state["market_key"] = market_key
    except Exception as exc:
        st.session_state["market_error"] = str(exc)

ticker = book = trades = None
market_errors = []
try:
    ticker = get_ticker(symbol)
except Exception as exc:
    market_errors.append(f"Ticker: {exc}")
try:
    book = get_book(symbol)
except Exception as exc:
    market_errors.append(f"Order book: {exc}")
try:
    trades = get_trades(symbol)
except Exception as exc:
    market_errors.append(f"Recent trades: {exc}")

df = st.session_state.get("market_candles")
if df is not None and not df.empty:
    last_price = float(ticker.get("close", df.close.iloc[-1])) if ticker else float(df.close.iloc[-1])
    change = float(ticker.get("ltp_change_24h", 0) or 0) if ticker else 0.0
    day_high = ticker.get("high", "—") if ticker else "—"
    day_low = ticker.get("low", "—") if ticker else "—"
    volume_24h = ticker.get("volume", "—") if ticker else "—"
    mark = ticker.get("mark_price", "—") if ticker else "—"
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("LAST PRICE", f"{last_price:,.2f}", f"{change:+.2f}% 24h")
    c2.metric("MARK PRICE", f"{float(mark):,.2f}" if mark not in (None, "—") else "—")
    c3.metric("24H HIGH", f"{float(day_high):,.2f}" if day_high != "—" else "—")
    c4.metric("24H LOW", f"{float(day_low):,.2f}" if day_low != "—" else "—")
    c5.metric("24H VOLUME", f"{float(volume_24h):,.2f}" if volume_24h != "—" else "—")
    c6.metric("CANDLES", f"{len(df):,}")

    zones = []
    try:
        zones = get_zones(df, zone_engine)
    except Exception as exc:
        st.warning(f"Zone detection issue: {exc}")

    active_zones = [z for z in zones if str(z.status).lower() not in ("broken", "invalidated")]
    zone_totals = {family: sum(1 for z in active_zones if zone_class(z) == family)
                   for family in ("DEMAND", "SUPPLY", "RBS", "SBR")}
    st.markdown(
        '<div class="section-kicker">ZONE INTELLIGENCE / ACTIVE LEVELS</div>',
        unsafe_allow_html=True,
    )
    z1, z2, z3, z4, z5 = st.columns(5)
    z1.metric("DEMAND", zone_totals["DEMAND"])
    z2.metric("SUPPLY", zone_totals["SUPPLY"])
    z3.metric("RBS · RESISTANCE → SUPPORT", zone_totals["RBS"])
    z4.metric("SBR · SUPPORT → RESISTANCE", zone_totals["SBR"])
    z5.metric("ACTIVE ZONES", len(active_zones))

    with st.container():
        st.caption(f"ZONE ENGINE · MAJOR SWING FILTER v2 · {len(zones)} zones detected · refresh clears zone cache")
        st.markdown('<div class="small-label">PRICE CHART · TRADINGVIEW-STYLE WORKSPACE</div>',
                    unsafe_allow_html=True)
        tool1, tool2, tool3, tool4, tool5 = st.columns([1.0, 1.5, 1.0, 1.0, 1.0])
        with tool1:
            chart_style = st.selectbox("CHART TYPE", ["Candles", "Line", "Area"],
                                       index=0, key="chart-style")
        with tool2:
            indicators = st.multiselect("INDICATORS", ["EMA 9", "EMA 20", "EMA 50", "EMA 200"],
                                        default=["EMA 20", "EMA 50"], key="chart-indicators")
        with tool3:
            show_chart_zones = st.toggle("Show zones", value=True, key="chart-zones")
        with tool4:
            show_structure = st.toggle("BOS / CHoCH", value=True, key="chart-structure")
        with tool5:
            show_scenarios = st.toggle("Trade plans", value=True, key="chart-scenarios")
        # Keep more historical structure visible. Rank by displacement/defended
        # quality first, then proximity to current price; do not let recency alone
        # hide a major origin zone such as the manually marked ~79k area.
        chart_zones = []
        for side in ("demand", "supply"):
            side_zones = [z for z in zones if str(z.kind).lower() == side
                          and z.status != "broken"]
            chart_zones.extend(sorted(
                side_zones,
                key=lambda z: (
                    1 if zone_class(z) in ("RBS", "SBR") else 0,
                    0.55 * float(z.strength) + 0.45 * float(z.score),
                    -abs((float(z.proximal) + float(z.distal)) / 2 - last_price)
                ),
                reverse=True
            )[:10])
        structure_events = detect_market_structure(df) if show_structure else []
        trade_scenarios = generate_trade_scenarios(last_price, zones) if show_scenarios else []
        seconds_per_candle = timeframe_minutes(timeframe) * 60
        st.plotly_chart(
            build_chart(df, chart_zones, show_volume, chart_style, indicators,
                        show_chart_zones, structure_events, trade_scenarios,
                        seconds_per_candle),
            use_container_width=True,
            config={
                "displaylogo": False, "scrollZoom": True, "doubleClick": "reset",
                "editable": False,
                "modeBarButtonsToAdd": [
                    "drawline", "drawrect", "drawcircle", "eraseshape"
                ],
                "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                "toImageButtonOptions": {"format": "png", "filename": "salty-trades-chart"}
            },
            key=f"chart-{symbol}-{timeframe}-{zone_engine}-{show_volume}-{chart_style}-{','.join(indicators)}-{show_chart_zones}"
        )
    depth_col, tape_col = st.columns(2, gap="small")
    with depth_col:
        st.markdown('<div class="small-label">ORDER BOOK · L2</div>', unsafe_allow_html=True)
        if book:
            asks = sorted(book.get("sell", []), key=lambda x: float(x.get("price", 0)))[:10]
            bids = sorted(book.get("buy", []), key=lambda x: float(x.get("price", 0)), reverse=True)[:10]
            ask_rows = [{"SIDE":"ASK", "PRICE":f'{float(x["price"]):,.1f}',
                         "SIZE":f'{float(x.get("size",0)):,.0f}'} for x in reversed(asks)]
            bid_rows = [{"SIDE":"BID", "PRICE":f'{float(x["price"]):,.1f}',
                         "SIZE":f'{float(x.get("size",0)):,.0f}'} for x in bids]
            st.dataframe(ask_rows + bid_rows, hide_index=True, height=390,
                         use_container_width=True)
            if asks and bids:
                spread = float(asks[0]["price"]) - float(bids[0]["price"])
                st.metric("BID / ASK SPREAD", f"{spread:,.2f}")
        else:
            st.info("Order book temporarily unavailable.")
    with tape_col:
        st.markdown('<div class="small-label">RECENT TRADES</div>', unsafe_allow_html=True)
        if trades:
            rows = []
            for trade in trades[:12]:
                side = str(trade.get("side", "")).upper()
                rows.append({"SIDE":side,
                             "PRICE":f'{float(trade.get("price",0)):,.1f}',
                             "SIZE":f'{float(trade.get("size",0)):,.0f}'})
            st.dataframe(rows, hide_index=True, height=260, use_container_width=True)
        else:
            st.caption("No recent trade prints returned.")

    lower_tabs = st.tabs(["ZONE MATRIX", "PAPER TICKET", "MARKET DATA", "JOURNAL", "SYSTEM", "ENTRY SCANNER", "STRUCTURE"])
    with lower_tabs[0]:
        st.markdown("**Detected zone matrix · all four zone families**")
        if zones:
            rows = [{
                "ZONE TYPE": zone_class(z), "TRADE BIAS": "LONG" if z.kind == "demand" else "SHORT", "PATTERN": z.pattern, "SOURCE": z.method.upper(),
                "PROXIMAL": round(float(z.proximal), 2), "DISTAL": round(float(z.distal), 2),
                "STRENGTH": round(float(z.strength), 3),
                "SCORE": round(float(z.score), 3),
                "DEFENDED RETESTS": int(z.defended_retests),
                "TOUCHES": int(z.touches), "STATUS": z.status.upper(),
                "FORMED": z.created_at,
            } for z in sorted(zones, key=lambda x: x.created_at, reverse=True)]
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No base/leg or confirmed swing zones found in this chart window. Try a higher timeframe.")
    with lower_tabs[1]:
        st.markdown("**Manual trade ticket · paper planning only**")
        st.caption("Build and track a trade plan here. This version does not send orders to Delta Exchange.")
        if "paper_trade_plans" not in st.session_state:
            st.session_state["paper_trade_plans"] = []

        zone_labels = ["Manual / no zone"] + [
            f"{z.kind.upper()} | {z.method.upper()} | {z.pattern} | "
            f"{min(float(z.proximal), float(z.distal)):.2f}–"
            f"{max(float(z.proximal), float(z.distal)):.2f} | {z.created_at}"
            for z in zones
        ]
        with st.form("paper_trade_ticket", clear_on_submit=False):
            a,b,c1 = st.columns(3)
            with a:
                ticket_side = st.selectbox("DIRECTION", ["LONG", "SHORT"])
                ticket_entry = st.number_input("PLANNED ENTRY", min_value=0.0,
                    value=float(last_price), format="%.2f")
                ticket_stop = st.number_input("STOP LOSS", min_value=0.0,
                    value=round(float(last_price) * (0.995 if ticket_side == "LONG" else 1.005), 2),
                    format="%.2f")
            with b:
                ticket_target = st.number_input("TAKE PROFIT", min_value=0.0,
                    value=round(float(last_price) * (1.01 if ticket_side == "LONG" else 0.99), 2),
                    format="%.2f")
                ticket_qty = st.number_input("CONTRACTS / QTY (manual)", min_value=0.0,
                    value=0.0, step=1.0, format="%.4f")
                ticket_risk_pct = st.number_input("PLANNED RISK %", min_value=0.0,
                    max_value=5.0, value=1.0, step=0.25)
            with c1:
                ticket_zone = st.selectbox("SETUP / ZONE", zone_labels)
                ticket_note = st.text_input("SETUP NOTE", placeholder="e.g. 15m demand retest + bullish close")
                ticket_status = st.selectbox("PLAN STATUS", ["WATCHING", "READY", "ENTERED MANUALLY"])
            if ticket_side == "LONG":
                valid_levels = ticket_stop < ticket_entry < ticket_target
                risk_distance = ticket_entry - ticket_stop
                reward_distance = ticket_target - ticket_entry
            else:
                valid_levels = ticket_target < ticket_entry < ticket_stop
                risk_distance = ticket_stop - ticket_entry
                reward_distance = ticket_entry - ticket_target
            rr = reward_distance / risk_distance if risk_distance > 0 else 0.0
            st.caption(f"Risk distance: {risk_distance:,.2f} · Reward distance: {reward_distance:,.2f} · R:R: {rr:.2f}:1")
            if not valid_levels:
                st.error("Invalid levels: LONG requires SL < Entry < TP; SHORT requires TP < Entry < SL.")
            submitted = st.form_submit_button("＋  SAVE TRADE PLAN", type="primary",
                                               disabled=not valid_levels or ticket_entry <= 0)
        if submitted:
            import datetime as dt
            st.session_state["paper_trade_plans"].append({
                "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "symbol": symbol, "timeframe": timeframe, "side": ticket_side,
                "entry": float(ticket_entry), "stop": float(ticket_stop),
                "target": float(ticket_target), "rr": round(rr, 3),
                "quantity_manual": float(ticket_qty), "risk_pct_planned": float(ticket_risk_pct),
                "zone": ticket_zone, "status": ticket_status, "note": ticket_note,
            })
            st.success("Trade plan saved in this session. No exchange order was placed.")

        plans = st.session_state["paper_trade_plans"]
        if plans:
            plan_df = pd.DataFrame(plans)
            st.markdown("**Saved trade plans (session only)**")
            st.dataframe(plan_df, use_container_width=True, hide_index=True)
            st.download_button("Download trade plans CSV", plan_df.to_csv(index=False),
                file_name="salty_trades_paper_plans.csv", mime="text/csv")
            if st.button("Clear saved plans", key="clear-paper-plans"):
                st.session_state["paper_trade_plans"] = []
                st.rerun()
        else:
            st.info("No trade plans saved in this session yet.")

    with lower_tabs[2]:
        st.markdown("**Latest completed candles**")
        st.dataframe(df.tail(30).sort_values("timestamp", ascending=False),
                     use_container_width=True, hide_index=True)
    with lower_tabs[3]:
        st.markdown("**Trade performance & learning**")
        uploaded = st.file_uploader("Upload backtest trade CSV", type=["csv"], key="journal-upload")
        if uploaded is not None:
            try:
                journal = learning_report(load_trades(uploaded))
                metrics = journal["summary"]
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("TRADES", metrics["trades"])
                m2.metric("WIN RATE", f'{metrics["win_rate_pct"]:.1f}%')
                m3.metric("EXPECTANCY", f'{metrics["expectancy_r"]:.3f} R')
                m4.metric("PROFIT FACTOR", metrics["profit_factor"] if metrics["profit_factor"] is not None else "—")
                st.write(journal["training_note"])
                for label,key in [("Zone pattern","zone_pattern"),("Zone engine","zone_method"),
                                  ("Trend alignment","trend_alignment"),("Side","side")]:
                    st.markdown(f"##### {label}")
                    st.dataframe(journal["groups"][key], use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Journal error: {exc}")
        else:
            st.caption("Upload the backtest trade CSV to inspect the strategy's measured performance.")
    with lower_tabs[4]:
        st.warning("Read-only research terminal. No order entry, account balance, positions or private account data are connected.")
        st.write("Data sources: Delta public OHLC candles, ticker, L2 order book and public trades.")
        if market_errors:
            for error in market_errors:
                st.caption(error)

    with lower_tabs[6]:
        st.markdown("**Confirmed market structure · conditional trade plans**")
        st.caption("Swing labels appear only after right-side confirmation candles close. BOS/CHoCH requires a candle close through a confirmed swing.")
        if structure_events:
            event_rows = [{
                "CONFIRMED AT": event.timestamp,
                "EVENT": event.event,
                "DIRECTION": event.direction.upper(),
                "LEVEL": round(float(event.level), 2),
                "PIVOT INDEX": event.pivot_index,
                "CONFIRM INDEX": event.index,
            } for event in structure_events[-40:]]
            st.dataframe(event_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No confirmed structure events in the loaded chart window.")
        st.markdown("##### Conditional scenarios")
        if trade_scenarios:
            scenario_rows = [{
                "SIDE": item.side,
                "ZONE": item.zone_pattern,
                "ENTRY BAND": f"{item.entry_low:,.2f} – {item.entry_high:,.2f}",
                "STOP": round(item.stop, 2),
                "TARGETS": " / ".join(f"{x:,.2f}" for x in item.targets) or "No opposing zone found",
                "R:R": " / ".join(f"{x:.2f}R" for x in item.risk_reward) or "—",
                "STATUS": item.status,
                "TRIGGER": item.trigger,
                "INVALIDATION": item.invalidation,
            } for item in trade_scenarios]
            st.dataframe(scenario_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No valid active demand/RBS below or supply/SBR above the current price. No forced trade plan.")
        st.warning("Research-only conditional levels. Wait for the stated candle-close confirmation; no order is sent.")

    with lower_tabs[5]:
        st.markdown("**15M ZONE MATRIX / 3M CONFIRMATION / PAPER SIGNAL ONLY**")
        st.caption("All four zone families are scanned: Demand and RBS are LONG-side support; Supply and SBR are SHORT-side resistance. Both sides stay eligible. 1H structure is context only, never a directional gate.")
        try:
            candles_15m = fetch_delta_history(symbol=symbol, timeframe="15m", days=16)
            candles_3m = fetch_delta_history(symbol=symbol, timeframe="3m", days=7)
            zones_15m = track_zone_lifecycle(candles_15m, detect_base_leg_zones(candles_15m))
            setups = find_entry_setups(candles_3m, zones_15m, buffer_atr=0.25)
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("3M ATR BUFFER", "0.25 × ATR(14)")
            e2.metric("RBS ZONES", sum(1 for z in zones_15m if zone_class(z) == "RBS" and z.status != "broken"))
            e3.metric("SBR ZONES", sum(1 for z in zones_15m if zone_class(z) == "SBR" and z.status != "broken"))
            e4.metric("SETUPS FOUND", len(setups))
            if setups:
                st.dataframe(pd.DataFrame(setups), use_container_width=True, hide_index=True)
                st.info("Historical confirmation candidates using the next 3m candle open. Research only; no live orders.")
            else:
                st.info("No qualifying tap-and-close confirmation in the loaded candles. No trade is preferable to a forced entry.")
            st.caption("SL: beyond 15m zone distal edge + ATR buffer. T1: 2R. Runner: nearest opposing 15m zone, only when it offers at least 2R.")
        except Exception as exc:
            st.error(f"Entry module data/analysis error: {exc}")
else:
    st.error(f"Chart data could not be loaded: {st.session_state.get('market_error', 'No candle data available.')}")
    st.info("Use Refresh Market after checking the Delta API connection. This terminal will not draw synthetic or placeholder candles.")

st.markdown('<div style="border-top:1px solid #252b36;padding-top:10px;color:#687382;font-size:10px;letter-spacing:1px;">SALTY TRADES · DELTA EXCHANGE INDIA · READ-ONLY RESEARCH TERMINAL</div>',
            unsafe_allow_html=True)
