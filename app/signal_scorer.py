"""
Final Signal Scorer
───────────────────
يجمع نتائج كل الطبقات السبع في نقطة نهائية واحدة.
"""

from __future__ import annotations
from app.config import MIN_SIGNAL_SCORE, SCORE_WEIGHTS


def calculate_score(
    ai_result:     dict,
    filter_result: dict,
    pa_result:     dict | None = None,
    smc_result:    dict | None = None,
    mtf_result:    dict | None = None,
    news_result:   dict | None = None,
) -> dict:
    """
    Calculates weighted final score.

    Returns
    -------
    dict:
        final_score   float
        approved      bool
        grade         str
        hard_blocks   list[str]
        breakdown     dict
    """
    W  = SCORE_WEIGHTS
    f  = filter_result.get("filters", {})

    pa  = pa_result  or {}
    smc = smc_result or {}
    mtf = mtf_result or {}
    nws = news_result or {}

    # ── Individual Scores ────────────────
    trend_s  = 10.0 if f.get("Trend",  {}).get("passed") else 3.0
    vol_s    = _vol_score(f.get("Volume", {}).get("value"))
    mom_s    = _rsi_score(f.get("RSI",   {}).get("value", 50))
    ai_s     = float(ai_result.get("final_score", 5.0))
    pa_s     = float(pa.get("score",  5.0))
    smc_s    = float(smc.get("score", 5.0))
    mtf_s    = float(mtf.get("score", 7.0))
    news_s   = 10.0 if nws.get("safe", True) else 2.0

    # ── Weighted Final ───────────────────
    final = (
        trend_s * W["trend"]        +
        pa_s    * W["price_action"] +
        smc_s   * W["smart_money"]  +
        ai_s    * W["ai"]           +
        mom_s   * W["momentum"]     +
        vol_s   * W["volume"]       +
        mtf_s   * W["mtf"]          +
        news_s  * W["news"]
    )
    final = round(final, 2)

    # ── Hard Blocks (instant reject) ─────
    hard_blocks: list[str] = []

    if not nws.get("safe", True):
        hard_blocks.append(
            f"📰 High-impact news: {nws.get('reason','')}"
        )
    if pa.get("ranging", False):
        hard_blocks.append("↔️ Ranging market detected")

    if not mtf.get("aligned", True):
        pct = mtf.get("alignment_pct", 0)
        hard_blocks.append(f"⏱️ MTF misaligned ({pct:.0f}%)")

    approved = (final >= MIN_SIGNAL_SCORE) and (len(hard_blocks) == 0)

    return {
        "final_score": final,
        "approved":    approved,
        "grade":       _grade(final),
        "hard_blocks": hard_blocks,
        "breakdown": {
            "trend":        round(trend_s, 2),
            "price_action": round(pa_s,    2),
            "smart_money":  round(smc_s,   2),
            "ai":           round(ai_s,    2),
            "momentum":     round(mom_s,   2),
            "volume":       round(vol_s,   2),
            "mtf":          round(mtf_s,   2),
            "news":         round(news_s,  2),
        },
    }


# ── Helpers ───────────────────────────────

def _vol_score(vr: float | None) -> float:
    if vr is None: return 6.0
    if vr >= 3.0:  return 10.0
    if vr >= 2.0:  return 9.0
    if vr >= 1.5:  return 7.0
    if vr >= 1.0:  return 5.0
    return 2.0


def _rsi_score(rsi: float) -> float:
    if 45 <= rsi <= 65: return 9.0
    if 35 <= rsi <= 75: return 7.0
    if 25 <= rsi <= 80: return 5.0
    return 2.0


def _grade(s: float) -> str:
    if s >= 9.0: return "A+"
    if s >= 8.5: return "A"
    if s >= 8.0: return "A-"
    if s >= 7.5: return "B+"
    if s >= 7.0: return "B"
    if s >= 6.0: return "C"
    return "F"
