import os
import sys
import streamlit as st
from dotenv import set_key, load_dotenv

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

ENV_FILE = ".env"
load_dotenv(ENV_FILE)

st.title("⚙️ Settings")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🔑 API Keys", "📊 Signal Settings", "ℹ️ System Info"])

# ══════════════════════════════════════════
# API Keys
# ══════════════════════════════════════════
with tab1:
    st.subheader("🔑 API Configuration")
    st.warning("⚠️ Keys are stored in your `.env` file.")

    with st.form("api_form"):
        gemini_key = st.text_input(
            "🤖 Gemini API Key",
            value=os.getenv("GEMINI_API_KEY",""),
            type="password",
            help="Get it free at: https://aistudio.google.com/app/apikey",
        )
        gemini_model = st.selectbox(
            "Gemini Model",
            ["gemini-1.5-flash","gemini-1.5-pro","gemini-2.0-flash"],
        )
        st.markdown("---")
        twelvedata_key = st.text_input(
            "📡 TwelveData API Key",
            value=os.getenv("TWELVEDATA_API_KEY",""),
            type="password",
            help="Get it free at: https://twelvedata.com",
        )

        if st.form_submit_button("💾 Save API Keys", type="primary"):
            set_key(ENV_FILE, "GEMINI_API_KEY",    gemini_key)
            set_key(ENV_FILE, "GEMINI_MODEL",       gemini_model)
            set_key(ENV_FILE, "TWELVEDATA_API_KEY", twelvedata_key)
            st.success("✅ Saved! Restart the app to apply new keys.")

# ══════════════════════════════════════════
# Signal Settings
# ══════════════════════════════════════════
with tab2:
    st.subheader("📊 Signal Filter Parameters")

    with st.form("signal_form"):
        c1, c2 = st.columns(2)

        with c1:
            min_score = st.slider(
                "Minimum Signal Score (higher = fewer but better signals)",
                5.0, 9.5, float(os.getenv("MIN_SIGNAL_SCORE","7.5")), 0.5,
            )
            min_rr = st.slider(
                "Minimum R:R Ratio",
                1.0, 4.0, float(os.getenv("MIN_RR_RATIO","1.5")), 0.5,
            )
            max_risk = st.slider(
                "Maximum Risk % per trade",
                0.5, 5.0, float(os.getenv("MAX_RISK_PERCENT","2.0")), 0.5,
            )

        with c2:
            min_vol = st.slider(
                "Minimum Volume Ratio",
                1.0, 3.0, float(os.getenv("MIN_VOLUME_RATIO","1.2")), 0.1,
            )
            start_h = st.number_input(
                "Trading Start Hour (UTC)",
                0, 23, int(os.getenv("TRADING_START_HOUR","7")),
            )
            end_h = st.number_input(
                "Trading End Hour (UTC)",
                0, 23, int(os.getenv("TRADING_END_HOUR","20")),
            )
            block_min = st.number_input(
                "News Block Window (minutes before/after)",
                5, 60, int(os.getenv("NEWS_BLOCK_MINUTES","30")),
            )

        if st.form_submit_button("💾 Save Settings", type="primary"):
            set_key(ENV_FILE, "MIN_SIGNAL_SCORE",  str(min_score))
            set_key(ENV_FILE, "MIN_RR_RATIO",      str(min_rr))
            set_key(ENV_FILE, "MAX_RISK_PERCENT",  str(max_risk))
            set_key(ENV_FILE, "MIN_VOLUME_RATIO",  str(min_vol))
            set_key(ENV_FILE, "TRADING_START_HOUR",str(start_h))
            set_key(ENV_FILE, "TRADING_END_HOUR",  str(end_h))
            set_key(ENV_FILE, "NEWS_BLOCK_MINUTES",str(block_min))
            st.success("✅ Settings saved! Restart to apply.")

# ══════════════════════════════════════════
# System Info
# ══════════════════════════════════════════
with tab3:
    st.subheader("ℹ️ System Information")
    import streamlit as st_ver
    import platform

    col1, col2 = st.columns(2)
    with col1:
        st.json({
            "Python":          sys.version.split()[0],
            "Platform":        platform.system(),
            "Streamlit":       st_ver.__version__,
            "AI Engine":       "Google Gemini",
            "Market Data":     "TwelveData",
            "Database":        "SQLite",
        })
    with col2:
        st.json({
            "Min Score":       os.getenv("MIN_SIGNAL_SCORE","7.5"),
            "Min R:R":         os.getenv("MIN_RR_RATIO","1.5"),
            "Max Risk %":      os.getenv("MAX_RISK_PERCENT","2.0"),
            "Min Volume ×":    os.getenv("MIN_VOLUME_RATIO","1.2"),
            "Trading Hours":   f"{os.getenv('TRADING_START_HOUR','7')}"
                               f"–{os.getenv('TRADING_END_HOUR','20')} UTC",
            "News Block":      f"±{os.getenv('NEWS_BLOCK_MINUTES','30')} min",
            "Gemini Model":    os.getenv("GEMINI_MODEL","gemini-1.5-flash"),
        })
