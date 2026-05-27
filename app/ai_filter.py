
"""
AI Filter - Google Gemini
──────────────────────────
يحلل إشارة التداول باستخدام Gemini AI
ويعيد تقييماً احترافياً مع نقاط تفصيلية.
"""

from __future__ import annotations

import json
import re

import google.generativeai as genai

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TIMEFRAME_WEIGHTS,
    MIN_SIGNAL_SCORE,
)
from app.logger import ai_logger

# ── تهيئة Gemini ──────────────────────────
genai.configure(api_key=GEMINI_API_KEY)

_model = genai.GenerativeModel(
    model_name=GEMINI_MODEL,
    generation_config=genai.GenerationConfig(
        temperature=0.2,
        max_output_tokens=900,
    ),
)

# ══════════════════════════════════════════
# Prompt Template
# ══════════════════════════════════════════

PROMPT = """
You are a senior Forex & Commodities trading analyst with 15+ years of experience.
Analyze the trading signal below with strict professional criteria.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIGNAL DETAILS
  Symbol    : {symbol}
  Direction : {side}
  Price     : {price}
  Timeframe : {timeframe}

TECHNICAL INDICATORS
  EMA 20    : {ema20}
  EMA 50    : {ema50}
  EMA 200   : {ema200}
  RSI (14)  : {rsi}
  MACD      : {macd}
  ATR (14)  : {atr}
  Volume    : {volume}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AUTO-REJECT CONDITIONS (any one triggers rejection):
  • RSI > 78 on BUY  |  RSI < 22 on SELL
  • Price is against all three EMAs simultaneously
  • Volume below 50% of normal average
  • ATR more than 4× its normal range
  • MACD diverges strongly from signal direction

SCORING GUIDE (each component 0 to 10):
  trend_score      → EMA alignment + market structure (HH/HL or LH/LL)
  volume_score     → volume confirmation vs 20-period average
  momentum_score   → RSI position + MACD alignment
  volatility_score → ATR within acceptable range, no abnormal spike

  final_score      → weighted average of the four scores above

IMPORTANT:
  - Be strict. Only approve genuinely high-probability setups.
  - A score below 7.0 should result in approved: false.
  - Provide concise, actionable analysis_summary.

Return ONLY valid JSON with no markdown fences, no extra text:
{{
  "trend_score":            <number 0-10>,
  "volume_score":           <number 0-10>,
  "momentum_score":         <number 0-10>,
  "volatility_score":       <number 0-10>,
  "final_score":            <number 0-10>,
  "approved":               <true or false>,
  "rejection_reason":       <"string describing reason" or null>,
  "market_condition":       <"TRENDING" or "RANGING" or "VOLATILE">,
  "key_levels": {{
      "support":    <number>,
      "resistance": <number>
  }},
  "analysis_summary":       "<2 to 3 professional sentences>",
  "confidence":             <"HIGH" or "MEDIUM" or "LOW">,
  "risk_reward_assessment": <"EXCELLENT" or "GOOD" or "FAIR" or "POOR">
}}
"""


# ══════════════════════════════════════════
# Public API
# ══════════════════════════════════════════

def analyze_signal(
    data:       dict,
    indicators: dict | None = None,
) -> dict:
    """
    Analyze a trading signal using Gemini AI.

    Parameters
    ----------
    data : dict
        Signal data: symbol, side, price, timeframe, …
    indicators : dict | None
        Live technical indicators from TwelveData.
        Falls back to values inside `data` if None.

    Returns
    -------
    dict with keys:
        approved, final_score, scores, rejection_reason,
        analysis_summary, confidence, market_condition,
        key_levels, risk_reward_assessment
    """
    ind = indicators or {}

    ai_logger.info(
        f"🧠 Gemini analysis → {data.get('symbol')} "
        f"{data.get('side')} @ {data.get('price')}"
    )

    prompt = PROMPT.format(
        symbol    = data.get("symbol",    "N/A"),
        side      = data.get("side",      "N/A"),
        price     = data.get("price",     "N/A"),
        timeframe = data.get("timeframe", "15m"),
        ema20     = ind.get("ema20",      data.get("ema20",   "N/A")),
        ema50     = ind.get("ema50",      data.get("ema50",   "N/A")),
        ema200    = ind.get("ema200",     data.get("ema200",  "N/A")),
        rsi       = ind.get("rsi",        data.get("rsi",     "N/A")),
        macd      = ind.get("macd",       data.get("macd",    "N/A")),
        atr       = ind.get("atr",        data.get("atr",     "N/A")),
        volume    = ind.get("volume",     data.get("volume",  "N/A")),
    )

    try:
        # ── استدعاء Gemini ────────────────
        response    = _model.generate_content(prompt)
        result_text = response.text.strip()

        ai_logger.debug(f"Gemini raw response: {result_text[:200]}")

        # ── تنظيف markdown fences إن وُجدت ──
        result_text = re.sub(r"^```(?:json)?", "", result_text).strip()
        result_text = re.sub(r"```$",           "", result_text).strip()

        # ── تحليل JSON ────────────────────
        result = json.loads(result_text)

        # ── تطبيق وزن الإطار الزمني ──────
        tf_weight = TIMEFRAME_WEIGHTS.get(
            data.get("timeframe", "15m"), 0.7
        )
        raw_score           = float(result.get("final_score", 0))
        result["final_score"] = round(raw_score * tf_weight, 2)

        # ── فلتر الحد الأدنى للنقاط ──────
        if result["final_score"] < MIN_SIGNAL_SCORE:
            result["approved"]         = False
            result["rejection_reason"] = (
                f"Score {result['final_score']}/10 "
                f"is below minimum threshold {MIN_SIGNAL_SCORE}"
            )

        # ── تطبيع sub-scores ─────────────
        result["scores"] = {
            "trend":      float(result.get("trend_score",      0)),
            "volume":     float(result.get("volume_score",     0)),
            "momentum":   float(result.get("momentum_score",   0)),
            "volatility": float(result.get("volatility_score", 0)),
        }

        # ── ضمان وجود key_levels ─────────
        if "key_levels" not in result:
            price = float(data.get("price", 0))
            result["key_levels"] = {
                "support":    round(price * 0.998, 5),
                "resistance": round(price * 1.002, 5),
            }

        ai_logger.info(
            f"✅ Gemini done | Score: {result['final_score']} | "
            f"Approved: {result['approved']} | "
            f"Confidence: {result.get('confidence','N/A')}"
        )

        return result

    except json.JSONDecodeError as e:
        ai_logger.error(f"JSON parse error: {e}\nRaw: {result_text[:300]}")
        return _rejection(f"JSON parse error: {e}")

    except Exception as e:
        ai_logger.error(f"Gemini API error: {e}")
        return _rejection(f"Gemini API error: {e}")


# ══════════════════════════════════════════
# Helper
# ══════════════════════════════════════════

def _rejection(reason: str) -> dict:
    """Return a safe rejection result when analysis fails."""
    return {
        "approved":               False,
        "rejection_reason":       reason,
        "final_score":            0.0,
        "scores": {
            "trend":      0.0,
            "volume":     0.0,
            "momentum":   0.0,
            "volatility": 0.0,
        },
        "trend_score":            0.0,
        "volume_score":           0.0,
        "momentum_score":         0.0,
        "volatility_score":       0.0,
        "confidence":             "LOW",
        "market_condition":       "UNKNOWN",
        "analysis_summary":       reason,
        "risk_reward_assessment": "POOR",
        "key_levels": {
            "support":    0.0,
            "resistance": 0.0,
        },
    }
