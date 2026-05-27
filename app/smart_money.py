
"""
Smart Money Concepts (SMC)
──────────────────────────
يكتشف:
  • Order Blocks (OB)
  • Fair Value Gaps (FVG)
  • Liquidity Sweeps
  • Break of Structure (BOS)
  • Change of Character (CHOCH)
"""

from __future__ import annotations
import pandas as pd
import numpy as np


# ══════════════════════════════════════════════════
# Main Entry
# ══════════════════════════════════════════════════

def analyze_smc(df: pd.DataFrame, side: str) -> dict:
    """
    Returns
    -------
    dict:
        score       0-10
        ob          dict  – Order Block info
        fvg         dict  – Fair Value Gap info
        sweep       bool  – Liquidity sweep detected
        bos         bool  – Break of Structure
        choch       bool  – Change of Character
        approved    bool
        reason      str
    """
    if df is None or len(df) < 20:
        return _empty("Insufficient data for SMC analysis")

    ob    = _find_order_block(df, side)
    fvg   = _find_fvg(df, side)
    sweep = _detect_liquidity_sweep(df, side)
    bos   = _detect_bos(df, side)
    choch = _detect_choch(df, side)

    score = _smc_score(ob, fvg, sweep, bos, choch, side)

    approved = score >= 5.0
    reason   = _smc_reason(ob, fvg, sweep, bos, choch, score)

    return {
        "score":    round(score, 2),
        "ob":       ob,
        "fvg":      fvg,
        "sweep":    sweep,
        "bos":      bos,
        "choch":    choch,
        "approved": approved,
        "reason":   reason,
    }


# ══════════════════════════════════════════════════
# Order Block Detection
# ══════════════════════════════════════════════════

def _find_order_block(df: pd.DataFrame, side: str) -> dict:
    """
    Bullish OB: last bearish candle before strong bullish move.
    Bearish OB: last bullish candle before strong bearish move.
    """
    o = df["open"].values
    h = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    price   = c[-1]
    lookback = min(30, len(df) - 1)

    if side == "BUY":
        # Find last bearish candle before strong bullish move
        for i in range(len(df) - 2, len(df) - lookback, -1):
            if c[i] < o[i]:   # bearish candle
                # Check if followed by strong bullish move
                if i + 3 < len(df):
                    future_move = c[i+3] - c[i]
                    candle_size = abs(c[i] - o[i])
                    if future_move > candle_size * 1.5:
                        ob_low  = lo[i]
                        ob_high = h[i]
                        in_zone = ob_low <= price <= ob_high
                        return {
                            "found":   True,
                            "type":    "Bullish OB",
                            "high":    round(ob_high, 5),
                            "low":     round(ob_low, 5),
                            "in_zone": in_zone,
                            "index":   i,
                        }
    else:  # SELL
        for i in range(len(df) - 2, len(df) - lookback, -1):
            if c[i] > o[i]:   # bullish candle
                if i + 3 < len(df):
                    future_move = c[i] - c[i+3]
                    candle_size = abs(c[i] - o[i])
                    if future_move > candle_size * 1.5:
                        ob_low  = lo[i]
                        ob_high = h[i]
                        in_zone = ob_low <= price <= ob_high
                        return {
                            "found":   True,
                            "type":    "Bearish OB",
                            "high":    round(ob_high, 5),
                            "low":     round(ob_low, 5),
                            "in_zone": in_zone,
                            "index":   i,
                        }

    return {"found": False, "type": None, "in_zone": False}


# ══════════════════════════════════════════════════
# Fair Value Gap (FVG)
# ══════════════════════════════════════════════════

def _find_fvg(df: pd.DataFrame, side: str) -> dict:
    """
    Bullish FVG: candle[i-1].high < candle[i+1].low
    Bearish FVG: candle[i-1].low  > candle[i+1].high
    """
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    price    = c[-1]
    lookback = min(20, len(df) - 2)

    gaps: list[dict] = []

    for i in range(len(df) - lookback, len(df) - 1):
        if i < 1:
            continue
        if side == "BUY":
            gap = lo[i] - h[i-1]
            if gap > 0:
                gaps.append({
                    "type":  "Bullish FVG",
                    "top":   round(lo[i],   5),
                    "bottom":round(h[i-1],  5),
                    "size":  round(gap, 5),
                    "filled": price <= lo[i],
                })
        else:
            gap = lo[i-1] - h[i]
            if gap > 0:
                gaps.append({
                    "type":  "Bearish FVG",
                    "top":   round(lo[i-1], 5),
                    "bottom":round(h[i],    5),
                    "size":  round(gap, 5),
                    "filled": price >= lo[i-1],
                })

    if not gaps:
        return {"found": False, "count": 0, "gaps": []}

    return {
        "found":  True,
        "count":  len(gaps),
        "gaps":   gaps[-3:],          # last 3 FVGs
        "latest": gaps[-1] if gaps else None,
    }


# ══════════════════════════════════════════════════
# Liquidity Sweep
# ══════════════════════════════════════════════════

def _detect_liquidity_sweep(df: pd.DataFrame, side: str) -> bool:
    """
    Detects if price swept a recent high/low (stop-hunt)
    and then reversed – classic smart money signature.
    """
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    if len(df) < 5:
        return False

    if side == "BUY":
        # Swept below recent lows then closed back above
        recent_low = lo[-6:-1].min()
        swept      = lo[-1] < recent_low
        recovered  = c[-1]  > lo[-1] + (h[-1] - lo[-1]) * 0.6
        return swept and recovered

    else:  # SELL
        recent_high = h[-6:-1].max()
        swept       = h[-1]  > recent_high
        rejected    = c[-1]  < h[-1]  - (h[-1] - lo[-1]) * 0.6
        return swept and rejected


# ══════════════════════════════════════════════════
# Break of Structure (BOS)
# ══════════════════════════════════════════════════

def _detect_bos(df: pd.DataFrame, side: str) -> bool:
    """
    BOS: price breaks the last significant swing high/low
    in the direction of the trade.
    """
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values

    if len(df) < 10:
        return False

    if side == "BUY":
        prev_high = h[-11:-1].max()
        return c[-1] > prev_high

    else:
        prev_low = lo[-11:-1].min()
        return c[-1] < prev_low


# ══════════════════════════════════════════════════
# Change of Character (CHOCH)
# ══════════════════════════════════════════════════

def _detect_choch(df: pd.DataFrame, side: str) -> bool:
    """
    CHOCH: market was moving one direction but just broke
    the most recent swing in opposite direction.
    """
    c  = df["close"].values
    h  = df["high"].values
    lo = df["low"].values

    if len(df) < 15:
        return False

    mid   = len(df) // 2
    first = c[:mid]
    last  = c[mid:]

    was_bearish = first[-1] < first[0]
    was_bullish = first[-1] > first[0]

    if side == "BUY" and was_bearish:
        return last[-1] > last[0]

    if side == "SELL" and was_bullish:
        return last[-1] < last[0]

    return False


# ══════════════════════════════════════════════════
# Score
# ══════════════════════════════════════════════════

def _smc_score(ob, fvg, sweep, bos, choch, side) -> float:
    score = 5.0

    if ob.get("found"):
        score += 1.5
        if ob.get("in_zone"):
            score += 1.0   # price is inside OB = perfect entry

    if fvg.get("found"):
        score += 1.0
        if fvg.get("count", 0) >= 2:
            score += 0.5

    if sweep:
        score += 1.5       # Liquidity sweep = strong SMC signal

    if bos:
        score += 1.0       # BOS = confirmation

    if choch:
        score += 0.5       # CHOCH = early trend change

    return max(0.0, min(10.0, score))


# ══════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════

def _smc_reason(ob, fvg, sweep, bos, choch, score) -> str:
    parts = []
    if ob.get("found"):
        zone = " (price in zone ✅)" if ob.get("in_zone") else ""
        parts.append(f"{ob['type']}{zone}")
    if fvg.get("found"):
        parts.append(f"FVG ×{fvg['count']}")
    if sweep:
        parts.append("Liquidity Sweep ✅")
    if bos:
        parts.append("BOS confirmed ✅")
    if choch:
        parts.append("CHOCH detected")
    parts.append(f"SMC Score: {score:.1f}/10")
    return " | ".join(parts) if parts else "No SMC signals"


def _empty(reason: str) -> dict:
    return {
        "score": 5.0, "ob": {"found": False},
        "fvg": {"found": False}, "sweep": False,
        "bos": False, "choch": False,
        "approved": True, "reason": reason,
    }
