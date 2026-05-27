
import os
import streamlit as st
from app.database import init_db
from app.logger   import main_logger

# ── إنشاء المجلدات الضرورية ──────────────
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ── إعداد الصفحة ─────────────────────────
st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── تهيئة قاعدة البيانات ─────────────────
init_db()
main_logger.info("🚀 AI Trading Bot started")

# ══════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/bot.png",
        width=72,
    )
    st.title("🤖 AI Trading Bot")
    st.caption("v3.0 · Gemini + TwelveData")
    st.markdown("---")

    st.markdown("""
    **📌 Navigation**
    - 🏠 Home
    - 📊 Dashboard
    - 🔍 Signal Analyzer
    - 📈 Trade History
    - ⚙️ Settings
    - 📉 Backtesting
    """)

    st.markdown("---")

    # ── Status Indicators ────────────────
    from app.config import GEMINI_API_KEY, TWELVEDATA_API_KEY

    gemini_ok  = bool(GEMINI_API_KEY  and GEMINI_API_KEY  != "your_gemini_api_key_here")
    twelved_ok = bool(TWELVEDATA_API_KEY and TWELVEDATA_API_KEY != "your_twelvedata_api_key_here")

    st.markdown("**🔌 API Status**")
    st.write(f"{'🟢' if gemini_ok  else '🔴'} Gemini AI")
    st.write(f"{'🟢' if twelved_ok else '🔴'} TwelveData")

    if not gemini_ok or not twelved_ok:
        st.warning("⚙️ Add API keys in **Settings**")

# ══════════════════════════════════════════
# Home Page
# ══════════════════════════════════════════
st.title("🤖 AI Trading Bot")
st.markdown("### Professional 7-Layer Signal Analysis · Forex & Commodities")
st.markdown("---")

# ── KPI Strip ────────────────────────────
from app.database import get_stats
stats = get_stats()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Signals",   stats.get("total_trades",    0))
k2.metric("✅ Winners",      stats.get("winning_trades",  0))
k3.metric("📈 Win Rate",     f"{stats.get('win_rate', 0):.1f}%")
k4.metric("⭐ Avg Score",    f"{stats.get('avg_score', 0):.1f}/10")
k5.metric("💰 Total P&L",   f"{stats.get('total_pnl', 0):+.2f}%")

st.markdown("---")

# ── Pipeline Visual ──────────────────────
st.markdown("## 🔄 7-Layer Analysis Pipeline")

layers = [
    ("1", "📡", "Market Data",       "TwelveData REST API",    "#6366f1"),
    ("2", "📰", "News Filter",       "Economic Calendar",      "#f59e0b"),
    ("3", "📊", "Technical Filters", "EMA · RSI · MACD · ATR", "#10b981"),
    ("4", "📈", "Price Action",      "Patterns · S/R · BOS",   "#3b82f6"),
    ("5", "💎", "Smart Money",       "OB · FVG · Sweep",       "#8b5cf6"),
    ("6", "⏱️", "Multi-Timeframe",   "Higher TF Confirmation", "#ec4899"),
    ("7", "🤖", "Gemini AI",         "Final AI Verdict",       "#f97316"),
]

cols = st.columns(len(layers))
for col, (num, emoji, title, sub, color) in zip(cols, layers):
    col.markdown(
        f"""
        <div style="
            background:#1e293b;
            border-left: 4px solid {color};
            border-radius: 8px;
            padding: 12px 10px;
            text-align: center;
            height: 110px;
        ">
            <div style="font-size:24px">{emoji}</div>
            <div style="color:{color}; font-weight:700; font-size:13px">
                Layer {num}
            </div>
            <div style="color:#e2e8f0; font-size:12px; font-weight:600">
                {title}
            </div>
            <div style="color:#64748b; font-size:10px">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ── Upcoming News ────────────────────────
from app.news_filter import get_upcoming_events

st.markdown("## 📰 Upcoming High-Impact Events (Next 8h)")
events = get_upcoming_events(hours_ahead=8)

if events:
    for ev in events[:5]:
        color = "#ef4444" if "HIGH" in ev["impact"] else "#f59e0b"
        st.markdown(
            f"""
            <div style="
                background:#1e293b;
                border-left: 4px solid {color};
                border-radius: 8px;
                padding: 10px 16px;
                margin-bottom: 8px;
                display: flex;
                justify-content: space-between;
            ">
                <span style="color:#e2e8f0">
                    {ev['impact']} &nbsp; <b>{ev['name']}</b>
                </span>
                <span style="color:#94a3b8">
                    🕐 {ev['utc_time']} UTC &nbsp; | &nbsp;
                    ⏳ {ev['minutes_away']} min
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.success("✅ No high-impact events in the next 8 hours.")

st.markdown("---")
st.info("👈 Use the **sidebar** to navigate · Start with **🔍 Signal Analyzer**")
