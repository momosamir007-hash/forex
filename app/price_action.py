"""
Price Action Analysis
─────────────────────
يكتشف:
  • Candlestick Patterns  (Engulfing, Hammer, Doji …)
  • Support / Resistance  (أقوى مستويات)
  • Breakout Detection
  • Market Structure      (HH / HL / LH / LL)
  • Ranging vs Trending
"""

from __future__ import annotations
import pandas as pd
import numpy as np


# ══════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════

def analyze_price_action(df: pd.DataFrame, side: str) -> dict:
    """
    Run full price-action suite.

    Returns
    -------
    dict with keys:
        score          0-10
        patterns       list[str]
        structure      str
        sr_levels      dict
        breakout       bool
        ranging        bool
        approved       bool
        reason         str
    """
    if df is None or len(df) < 30:
        return _empty("Insufficient candle data")

    patterns  = _detect_patterns(df, side)
    structure = _market_structure(df)
    sr        = _support_resistance(df)
    breakout  = _detect_breakout(df, side, sr)
    ranging   = _is_ranging(df)

    score = _calculate_score(
        patterns, structure, breakout, ranging, side
    )

    approved = score >= 6.0 and not ranging
    reason   = _build_reason(patterns, structure, breakout, ranging, score)

    return {
        "score":    round(score, 2),
        "patterns": patterns,
        "structure": structure,
        "sr_levels": sr,
        "breakout":  breakout,
        "ranging":   ranging,
        "approved":  approved,
        "reason":    reason,
    }


# ══════════════════════════════════════════════════
# Candlestick Pattern Detection
# ══════════════════════════════════════════════════

def _detect_patterns(df: pd.DataFrame, side: str) -> list[str]:
    patterns: list[str] = []

    o = df["open"].values
    h = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    i = len(df) - 1   # last candle

    # ── Body / Wick helpers ───────────────
    body   = abs(c[i] - o[i])
    total  = h[i] - lo[i]
    upper  = h[i]  - max(c[i], o[i])
    lower  = min(c[i], o[i]) - lo[i]
    bull_c = c[i] > o[i]
    bear_c = c[i] < o[i]

    body_prev   = abs(c[i-1] - o[i-1])
    total_prev  = h[i-1] - lo[i-1]

    # ── Doji ─────────────────────────────
    if total > 0 and body / total < 0.1:
        patterns.append("Doji ⚖️")

    # ── Hammer / Hanging Man ─────────────
    if (total > 0 and lower / total > 0.60
            and body / total < 0.25 and upper / total < 0.10):
        if side == "BUY":
            patterns.append("Hammer 🔨")
        else:
            patterns.append("Hanging Man 🪓")

    # ── Inverted Hammer / Shooting Star ──
    if (total > 0 and upper / total > 0.60
            and body / total < 0.25 and lower / total < 0.10):
        if side == "SELL":
            patterns.append("Shooting Star ⭐")
        else:
            patterns.append("Inverted Hammer")

    # ── Bullish Engulfing ─────────────────
    if (bull_c and not (c[i-1] > o[i-1])
            and c[i] > o[i-1] and o[i] < c[i-1]
            and body > body_prev):
        patterns.append("Bullish Engulfing 🟢")

    # ── Bearish Engulfing ─────────────────
    if (bear_c and c[i-1] > o[i-1]
            and c[i] < o[i-1] and o[i] > c[i-1]
            and body > body_prev):
        patterns.append("Bearish Engulfing 🔴")

    # ── Bullish Pin Bar ───────────────────
    if (total > 0 and lower > body * 2
            and lower > upper * 2):
        patterns.append("Bullish Pin Bar 📍")

    # ── Bearish Pin Bar ───────────────────
    if (total > 0 and upper > body * 2
            and upper > lower * 2):
        patterns.append("Bearish Pin Bar 📌")

    # ── Morning Star (3-candle) ───────────
    if i >= 2:
        mid_body = abs(c[i-1] - o[i-1])
        mid_total = h[i-1] - lo[i-1]
        if (not (c[i-2] > o[i-2])           # bearish first
                and mid_total > 0
                and mid_body / mid_total < 0.3  # small mid
                and c[i] > o[i]             # bullish last
                and c[i] > (o[i-2] + c[i-2]) / 2):
            patterns.append("Morning Star 🌟")

    # ── Evening Star (3-candle) ───────────
    if i >= 2:
        mid_body  = abs(c[i-1] - o[i-1])
        mid_total = h[i-1] - lo[i-1]
        if (c[i-2] > o[i-2]                 # bullish first
                and mid_total > 0
                and mid_body / mid_total < 0.3
                and not (c[i] > o[i])       # bearish last
                and c[i] < (o[i-2] + c[i-2]) / 2):
            patterns.append("Evening Star 🌆")

    # ── Three White Soldiers ─────────────
    if i >= 2:
        if (c[i]   > o[i]   and
                c[i-1] > o[i-1] and
                c[i-2] > o[i-2] and
                c[i] > c[i-1] > c[i-2]):
            patterns.append("Three White Soldiers 💪")

    # ── Three Black Crows ─────────────────
    if i >= 2:
        if (c[i]   < o[i]   and
                c[i-1] < o[i-1] and
                c[i-2] < o[i-2] and
                c[i] < c[i-1] < c[i-2]):
            patterns.append("Three Black Crows 🐦‍⬛")

    return patterns


# ══════════════════════════════════════════════════
# Market Structure
# ══════════════════════════════════════════════════

def _market_structure(df: pd.DataFrame) -> str:
    """
    Identify: BULLISH / BEARISH / RANGING
    using pivot highs/lows over last 20 candles.
    """
    c  = df["close"].values[-20:]
    h  = df["high"].values[-20:]
    lo = df["low"].values[-20:]

    # Find local pivots (simplified)
    pivot_highs = [h[i] for i in range(1, len(h)-1)
                   if h[i] > h[i-1] and h[i] > h[i+1]]
    pivot_lows  = [lo[i] for i in range(1, len(lo)-1)
                   if lo[i] < lo[i-1] and lo[i] < lo[i+1]]

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "NEUTRAL"

    hh = pivot_highs[-1] > pivot_highs[-2]   # Higher High
    hl = pivot_lows[-1]  > pivot_lows[-2]    # Higher Low
    lh = pivot_highs[-1] < pivot_highs[-2]   # Lower High
    ll = pivot_lows[-1]  < pivot_lows[-2]    # Lower Low

    if hh and hl:
        return "BULLISH 📈"
    elif lh and ll:
        return "BEARISH 📉"
    else:
        return "RANGING ↔️"


# ══════════════════════════════════════════════════
# Support / Resistance
# ══════════════════════════════════════════════════

def _support_resistance(df: pd.DataFrame) -> dict:
    """Find strongest S/R levels using pivot clustering."""
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    price = c[-1]

    # All pivot levels
    levels: list[float] = []
    for i in range(2, len(df) - 2):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
            levels.append(h[i])
        if lo[i] < lo[i-1] and lo[i] < lo[i-2] and lo[i] < lo[i+1] and lo[i] < lo[i+2]:
            levels.append(lo[i])

    if not levels:
        return {
            "support": round(price * 0.998, 5),
            "resistance": round(price * 1.002, 5),
            "nearest_support": round(price * 0.998, 5),
            "nearest_resistance": round(price * 1.002, 5),
        }

    levels_arr = np.array(levels)

    below = levels_arr[levels_arr < price]
    above = levels_arr[levels_arr > price]

    support    = float(below.max()) if len(below) else price * 0.998
    resistance = float(above.min()) if len(above) else price * 1.002

    return {
        "support":            round(support, 5),
        "resistance":         round(resistance, 5),
        "nearest_support":    round(support, 5),
        "nearest_resistance": round(resistance, 5),
        "distance_to_support":    round(abs(price - support) / price * 100, 3),
        "distance_to_resistance": round(abs(resistance - price) / price * 100, 3),
    }


# ══════════════════════════════════════════════════
# Breakout Detection
# ══════════════════════════════════════════════════

def _detect_breakout(df: pd.DataFrame, side: str, sr: dict) -> bool:
    """True if price has just broken a key level with momentum."""
    c = df["close"].values
    v = df["volume"].values if "volume" in df.columns else None

    current = c[-1]
    prev    = c[-2]

    resistance = sr.get("resistance", current * 1.002)
    support    = sr.get("support",    current * 0.998)

    # Volume confirmation (if available)
    vol_surge = True
    if v is not None and len(v) >= 20 and v[-20:].mean() > 0:
        vol_surge = v[-1] > v[-20:].mean() * 1.3

    if side == "BUY":
        return prev < resistance <= current and vol_surge
    else:
        return prev > support >= current and vol_surge


# ══════════════════════════════════════════════════
# Ranging Market Detection
# ══════════════════════════════════════════════════

def _is_ranging(df: pd.DataFrame) -> bool:
    """
    True if the market is in a tight range.
    Uses ATR relative to price range over last 20 candles.
    """
    if len(df) < 20:
        return False

    last20 = df.tail(20)
    price_range = last20["high"].max() - last20["low"].min()
    avg_atr     = (last20["high"] - last20["low"]).mean()

    if avg_atr == 0:
        return False

    # If range is less than 3× ATR → ranging
    ratio = price_range / avg_atr
    return ratio < 3.0


# ══════════════════════════════════════════════════
# Score
# ══════════════════════════════════════════════════

def _calculate_score(
    patterns: list[str],
    structure: str,
    breakout: bool,
    ranging: bool,
    side: str,
) -> float:
    score = 5.0   # base

    # ── Ranging penalty ─────────────────
    if ranging:
        score -= 3.0

    # ── Structure bonus ──────────────────
    if "BULLISH" in structure and side == "BUY":
        score += 2.0
    elif "BEARISH" in structure and side == "SELL":
        score += 2.0
    elif "RANGING" in structure:
        score -= 1.0

    # ── Breakout bonus ───────────────────
    if breakout:
        score += 1.5

    # ── Pattern bonus ────────────────────
    # Strong reversal/continuation patterns
    STRONG_PATTERNS = {
        "Bullish Engulfing 🟢", "Bearish Engulfing 🔴",
        "Morning Star 🌟",      "Evening Star 🌆",
        "Three White Soldiers 💪", "Three Black Crows 🐦‍⬛",
    }
    MEDIUM_PATTERNS = {
        "Hammer 🔨", "Shooting Star ⭐",
        "Bullish Pin Bar 📍", "Bearish Pin Bar 📌",
    }

    for p in patterns:
        if p in STRONG_PATTERNS:
            score += 1.5
        elif p in MEDIUM_PATTERNS:
            score += 0.8

    # ── Alignment bonus (pattern direction) ──
    bullish_patterns = {
        "Bullish Engulfing 🟢", "Hammer 🔨", "Morning Star 🌟",
        "Bullish Pin Bar 📍",   "Inverted Hammer",
        "Three White Soldiers 💪",
    }
    bearish_patterns = {
        "Bearish Engulfing 🔴", "Shooting Star ⭐", "Evening Star 🌆",
        "Bearish Pin Bar 📌",   "Hanging Man 🪓",
        "Three Black Crows 🐦‍⬛",
    }

    aligned = any(
        (side == "BUY"  and p in bullish_patterns) or
        (side == "SELL" and p in bearish_patterns)
        for p in patterns
    )
    if aligned:
        score += 0.5

    return max(0.0, min(10.0, score))


# ══════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════

def _build_reason(patterns, structure, breakout, ranging, score) -> str:
    parts = [f"Structure: {structure}"]
    if patterns:
        parts.append(f"Patterns: {', '.join(patterns)}")
    if breakout:
        parts.append("Breakout confirmed ✅")
    if ranging:
        parts.append("⚠️ Ranging market – caution")
    parts.append(f"PA Score: {score:.1f}/10")
    return " | ".join(parts)


def _empty(reason: str) -> dict:
    return {
        "score": 5.0, "patterns": [], "structure": "UNKNOWN",
        "sr_levels": {}, "breakout": False, "ranging": False,
        "approved": True, "reason": reason,
    }
