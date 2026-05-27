import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from app.database    import get_stats, get_all_trades, get_all_rejected, init_db
from app.news_filter import get_upcoming_events

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
init_db()

# Auto-refresh every 60 s
st_autorefresh(interval=60_000, key="dash_refresh")

st.title("📊 Dashboard")
st.markdown("---")

# ── KPIs ─────────────────────────────────
stats = get_stats()

k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Total Trades",     stats["total_trades"])
k2.metric("✅ Winners",       stats["winning_trades"])
k3.metric("❌ Losers",        stats["losing_trades"])
k4.metric("📈 Win Rate",      f"{stats['win_rate']}%")
k5.metric("💰 Total P&L",    f"{stats['total_pnl']:+.2f}%")
k6.metric("⭐ Avg Score",    f"{stats['avg_score']}/10")

st.markdown("---")

# ── Trades Data ───────────────────────────
trades = get_all_trades()

if not trades:
    st.info("📭 No trades yet. Go to **🔍 Signal Analyzer** to start.")
    st.stop()

df = pd.DataFrame(trades)
df["created_at"] = pd.to_datetime(df["created_at"])

# ── Charts Row 1 ─────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Win / Loss Distribution")
    counts = df["result"].fillna("PENDING").value_counts().reset_index()
    counts.columns = ["Result", "Count"]
    fig = px.pie(
        counts, values="Count", names="Result", hole=0.4,
        color="Result",
        color_discrete_map={
            "WIN":"#22c55e","LOSS":"#ef4444","PENDING":"#94a3b8"
        },
    )
    fig.update_layout(
        height=300, showlegend=True,
        paper_bgcolor="rgba(0,0,0,0)", font_color="white",
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📊 Score Distribution")
    fig2 = px.histogram(
        df, x="final_score", nbins=12,
        color_discrete_sequence=["#6366f1"],
        labels={"final_score": "Final Score"},
    )
    fig2.add_vline(x=7.5, line_dash="dash", line_color="#ef4444",
                   annotation_text="Min 7.5", annotation_font_color="white")
    fig2.update_layout(
        height=300, margin=dict(t=10,b=10,l=10,r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Equity Curve ──────────────────────────
st.subheader("📈 Cumulative P&L")
closed = df[df["pnl_percent"].notna()].sort_values("created_at").copy()

if not closed.empty:
    closed["cumulative_pnl"] = closed["pnl_percent"].cumsum()
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=closed["created_at"],
        y=closed["cumulative_pnl"],
        mode="lines+markers",
        fill="tozeroy",
        line=dict(color="#22c55e", width=2),
        fillcolor="rgba(34,197,94,0.1)",
        name="Cum. P&L",
    ))
    fig3.add_hline(y=0, line_dash="dash", line_color="gray")
    fig3.update_layout(
        height=300, margin=dict(t=10,b=10,l=10,r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        xaxis_title="Date", yaxis_title="P&L %",
    )
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No closed trades yet to build equity curve.")

# ── Symbol Performance ────────────────────
st.subheader("🪙 Performance by Symbol")
if not df.empty:
    sym = (
        df.groupby("symbol")
          .agg(
              Trades   = ("id","count"),
              Avg_Score= ("final_score","mean"),
              Avg_PnL  = ("pnl_percent","mean"),
              Wins     = ("result", lambda x: (x=="WIN").sum()),
          )
          .reset_index()
          .round(2)
    )
    sym["Win%"] = (sym["Wins"] / sym["Trades"] * 100).round(1)
    st.dataframe(sym, use_container_width=True)

# ── Recent Rejections ─────────────────────
st.subheader("🚫 Recent Rejected Signals")
rejected = get_all_rejected()
if rejected:
    rdf = pd.DataFrame(rejected).head(8)
    st.dataframe(
        rdf[["symbol","side","price","score","reason","created_at"]],
        use_container_width=True,
    )
else:
    st.info("No rejections recorded.")

# ── Upcoming News ─────────────────────────
st.subheader("📰 Upcoming Events")
events = get_upcoming_events(8)
if events:
    edf = pd.DataFrame(events)[["impact","name","utc_time","minutes_away"]]
    st.dataframe(edf, use_container_width=True)
else:
    st.success("✅ Calendar is clear for the next 8 hours.")
