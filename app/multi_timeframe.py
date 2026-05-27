
"""
Multi-Timeframe Confirmation
────────────────────────────
يتحقق أن الاتجاه متوافق على:
  • timeframe أعلى (×2)
  • timeframe أعلى (×3)
قبل الموافقة على الإشارة.
"""

from __future__ import annotations
import pandas as pd
from app.config import TIMEFRAME_MAP
from app.market_filters import data_fetcher

# ─────────────────────────────────────────
# Timeframe Hierarchy
# ─────────────────────────────────────────
HIGHER_TF = {
    "1m":  ["5m",  "15m"],
    "5m":  ["15m", "1h"],
    "15m": ["1h",  "4h"],
    "30m": ["1h",  "4h"],
    "1h":  ["4h",  "1d"],
    "4h":  ["1d"],
    "1d":  [],
}


def analyze_mtf(symbol: str, base_tf: str, side: str) -> dict:
    """
    Returns
    -------
    dict:
        score          0-10
        aligned        bool
        alignment_pct  float
        details        dict  {tf: {trend, score}}
        reason         str
    """
    higher = HIGHER_TF.get(base_tf, [])

    if not higher:
        return {
            "score": 8.0, "aligned": True,
            "alignment_pct": 100.0,
            "details": {}, "reason": "Top timeframe – no higher TF to check",
        }

    results = {}
    aligned_count = 0

    for tf in higher:
        try:
            df = data_fetcher.get_ohlcv(symbol, tf, limit=50)
            if df is None or len(df) < 20:
                results[tf] = {"trend": "N/A", "aligned": True, "score": 7.0}
                aligned_count += 1
                continue

            trend    = _tf_trend(df)
            aligned  = _is_aligned(trend, side)
            tf_score = 10.0 if aligned else 3.0

            if aligned:
                aligned_count += 1

            results[tf] = {
                "trend":   trend,
                "aligned": aligned,
                "score":   tf_score,
            }

        except Exception as e:
            results[tf] = {"trend": "ERROR", "aligned": True, "score": 7.0}
            aligned_count += 1

    total   = len(higher)
    pct     = aligned_count / total * 100 if total else 100
    score   = pct / 10.0

    reason_parts = [
        f"{tf}: {v['trend']} {'✅' if v['aligned'] else '❌'}"
        for tf, v in results.items()
    ]

    return {
        "score":          round(score, 2),
        "aligned":        pct >= 50,
        "alignment_pct":  round(pct, 1),
        "details":        results,
        "reason":         " | ".join(reason_parts),
    }


def _tf_trend(df: pd.DataFrame) -> str:
    c   = df["close"]
    e20 = c.ewm(span=20).mean().iloc[-1]
    e50 = c.ewm(span=50).mean().iloc[-1]
    cur = c.iloc[-1]

    if cur > e20 > e50:
        return "BULLISH"
    elif cur < e20 < e50:
        return "BEARISH"
    else:
        return "NEUTRAL"


def _is_aligned(trend: str, side: str) -> bool:
    if side == "BUY":
        return trend in ("BULLISH", "NEUTRAL")
    else:
        return trend in ("BEARISH", "NEUTRAL")
