import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# Gemini AI
# ─────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# ─────────────────────────────────────────
# TwelveData
# ─────────────────────────────────────────
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
TWELVEDATA_BASE    = "https://api.twelvedata.com"

# ─────────────────────────────────────────
# Signal Settings
# ─────────────────────────────────────────
MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "7.5"))
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.2"))
MAX_RISK_PERCENT = float(os.getenv("MAX_RISK_PERCENT", "2.0"))
MIN_RR_RATIO     = float(os.getenv("MIN_RR_RATIO",     "1.5"))

# ─────────────────────────────────────────
# Trading Session UTC
# ─────────────────────────────────────────
TRADING_START_HOUR = int(os.getenv("TRADING_START_HOUR", "7"))
TRADING_END_HOUR   = int(os.getenv("TRADING_END_HOUR",   "20"))

# ─────────────────────────────────────────
# News Filter
# ─────────────────────────────────────────
NEWS_API_KEY        = os.getenv("NEWS_API_KEY", "")
NEWS_BLOCK_MINUTES  = int(os.getenv("NEWS_BLOCK_MINUTES", "30"))

# ─────────────────────────────────────────
# Database
# ─────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/trades.db")

# ─────────────────────────────────────────
# Supported Pairs
# ─────────────────────────────────────────
SUPPORTED_PAIRS = {
    "EUR/USD": {
        "name": "Euro / US Dollar", "emoji": "💶",
        "category": "forex", "pip": 0.0001,
        "atr_normal": 0.0080,
        "session": ["london", "newyork"],
    },
    "GBP/USD": {
        "name": "British Pound / US Dollar", "emoji": "💷",
        "category": "forex", "pip": 0.0001,
        "atr_normal": 0.0120,
        "session": ["london", "newyork"],
    },
    "USD/JPY": {
        "name": "US Dollar / Japanese Yen", "emoji": "💴",
        "category": "forex", "pip": 0.01,
        "atr_normal": 0.80,
        "session": ["tokyo", "london"],
    },
    "GBP/JPY": {
        "name": "Pound / Yen", "emoji": "🇬🇧",
        "category": "forex", "pip": 0.01,
        "atr_normal": 1.20,
        "session": ["tokyo", "london"],
    },
    "XAU/USD": {
        "name": "Gold / US Dollar", "emoji": "🥇",
        "category": "commodity", "pip": 0.01,
        "atr_normal": 15.0,
        "session": ["london", "newyork"],
    },
    "XAG/USD": {
        "name": "Silver / US Dollar", "emoji": "🥈",
        "category": "commodity", "pip": 0.001,
        "atr_normal": 0.35,
        "session": ["london", "newyork"],
    },
    "WTI/USD": {
        "name": "Crude Oil WTI", "emoji": "🛢️",
        "category": "commodity", "pip": 0.01,
        "atr_normal": 1.20,
        "session": ["newyork"],
    },
}

# ─────────────────────────────────────────
# Timeframes
# ─────────────────────────────────────────
TIMEFRAME_MAP = {
    "1m": "1min", "5m": "5min", "15m": "15min",
    "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1day",
}

TIMEFRAME_WEIGHTS = {
    "1m": 0.30, "5m": 0.50, "15m": 0.70,
    "30m": 0.80, "1h": 0.90, "4h": 1.00, "1d": 1.00,
}

# ─────────────────────────────────────────
# Sessions UTC
# ─────────────────────────────────────────
SESSIONS = {
    "sydney":  (21, 6),
    "tokyo":   (0,  9),
    "london":  (7,  16),
    "newyork": (12, 21),
}

# ─────────────────────────────────────────
# Score Weights
# ─────────────────────────────────────────
SCORE_WEIGHTS = {
    "trend":       0.20,
    "price_action":0.20,
    "smart_money": 0.15,
    "ai":          0.15,
    "momentum":    0.10,
    "volume":      0.08,
    "mtf":         0.07,
    "news":        0.05,
}
