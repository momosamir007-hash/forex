"""
AI Filter - Google Gemini
إصلاح: Prompt محسَّن يضمن JSON صحيح دائماً
"""

from __future__ import annotations

import json
import re
import time

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
        temperature=0.1,        # أقل عشوائية = JSON أكثر استقراراً
        max_output_tokens=1200, # زيادة الحد لتجنب الاقتطاع
        top_p=0.8,
        top_k=40,
    ),
)

# ══════════════════════════════════════════
# Prompt - مُحسَّن لضمان JSON صحيح
# ══════════════════════════════════════════

PROMPT = """You are a senior Forex trading analyst. Analyze this signal and return ONLY a JSON object.

SIGNAL:
Symbol: {symbol}
Direction: {side}
Price: {price}
Timeframe: {timeframe}

INDICATORS:
EMA20: {ema20}
EMA50: {ema50}
EMA200: {ema200}
RSI: {rsi}
MACD: {macd}
ATR: {atr}
Volume: {volume}

RULES:
- Reject if RSI above 78 on BUY or below 22 on SELL
- Reject if price against all three EMAs
- Score below 7.0 means approved is false

Return this exact JSON structure with no other text:
{{"trend_score": 7.5, "volume_score": 7.0, "momentum_score": 7.5, "volatility_score": 8.0, "final_score": 7.5, "approved": true, "rejection_reason": null, "market_condition": "TRENDING", "key_levels": {{"support": 1.0840, "resistance": 1.0870}}, "analysis_summary": "Price shows bullish momentum above key EMAs with RSI in neutral zone supporting further upside.", "confidence": "MEDIUM", "risk_reward_assessment": "GOOD"}}

Now analyze and return the JSON for the signal above:"""


# ══════════════════════════════════════════
# JSON Extractor - متعدد الطرق
# ══════════════════════════════════════════

def _extract_json(text: str) -> dict | None:
    """
    محاولات متعددة لاستخراج JSON صحيح من النص.
    """
    if not text:
        return None

    # ── المحاولة 1: النص كاملاً ───────────
    try:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$",           "", cleaned).strip()
        return json.loads(cleaned)
    except Exception:
        pass

    # ── المحاولة 2: استخراج أول {} ────────
    try:
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    # ── المحاولة 3: استخراج {} متداخل ─────
    try:
        start = text.find('{')
        if start != -1:
            depth   = 0
            end_idx = start
            for i, ch in enumerate(text[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            json_str = text[start:end_idx + 1]
            return json.loads(json_str)
    except Exception:
        pass

    # ── المحاولة 4: إصلاح JSON المقتطع ────
    try:
        start = text.find('{')
        if start != -1:
            fragment = text[start:]
            # أضف الحقول الناقصة إذا انقطع النص
            if not fragment.rstrip().endswith('}'):
                # أغلق الـ string المفتوح والـ JSON
                fragment = fragment.rstrip()
                if fragment.endswith('"'):
                    fragment += ', "risk_reward_assessment": "FAIR"}'
                else:
                    fragment += '"}'
            return json.loads(fragment)
    except Exception:
        pass

    return None


def _extract_fields(text: str) -> dict:
    """
    استخراج القيم مباشرة من النص إذا فشل JSON.
    """
    def find_float(pattern: str, default: float) -> float:
        m = re.search(pattern, text)
        return float(m.group(1)) if m else default

    def find_bool(pattern: str, default: bool) -> bool:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return default
        return m.group(1).lower() == "true"

    def find_str(pattern: str, default: str) -> str:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    return {
        "trend_score":      find_float(r'"trend_score"\s*:\s*([\d.]+)', 6.0),
        "volume_score":     find_float(r'"volume_score"\s*:\s*([\d.]+)', 6.0),
        "momentum_score":   find_float(r'"momentum_score"\s*:\s*([\d.]+)', 6.0),
        "volatility_score": find_float(r'"volatility_score"\s*:\s*([\d.]+)', 7.0),
        "final_score":      find_float(r'"final_score"\s*:\s*([\d.]+)', 6.0),
        "approved":         find_bool(r'"approved"\s*:\s*(true|false)', False),
        "rejection_reason": None,
        "market_condition": find_str(r'"market_condition"\s*:\s*"([^"]+)"', "UNKNOWN"),
        "key_levels":       {"support": 0.0, "resistance": 0.0},
        "analysis_summary": find_str(r'"analysis_summary"\s*:\s*"([^"]+)"',
                                     "Analysis extracted from partial response"),
        "confidence":       find_str(r'"confidence"\s*:\s*"([^"]+)"', "LOW"),
        "risk_reward_assessment": find_str(
            r'"risk_reward_assessment"\s*:\s*"([^"]+)"', "FAIR"
        ),
    }


# ══════════════════════════════════════════
# Public API
# ══════════════════════════════════════════

def analyze_signal(
    data:       dict,
    indicators: dict | None = None,
) -> dict:
    """
    Analyze a trading signal using Gemini AI.
    Robust JSON extraction with multiple fallback methods.
    """
    ind = indicators or {}

    ai_logger.info(
        f"🧠 Analyzing → {data.get('symbol')} "
        f"{data.get('side')} @ {data.get('price')}"
    )

    prompt = PROMPT.format(
        symbol    = data.get("symbol",    "N/A"),
        side      = data.get("side",      "N/A"),
        price     = data.get("price",     "N/A"),
        timeframe = data.get("timeframe", "15m"),
        ema20     = ind.get("ema20",      data.get("ema20",  "N/A")),
        ema50     = ind.get("ema50",      data.get("ema50",  "N/A")),
        ema200    = ind.get("ema200",     data.get("ema200", "N/A")),
        rsi       = ind.get("rsi",        data.get("rsi",    "N/A")),
        macd      = ind.get("macd",       data.get("macd",   "N/A")),
        atr       = ind.get("atr",        data.get("atr",    "N/A")),
        volume    = ind.get("volume",     data.get("volume", "N/A")),
    )

    result_text = ""

    # ── محاولتان للاستدعاء ───────────────
    for attempt in range(2):
        try:
            response    = _model.generate_content(prompt)
            result_text = response.text.strip() if response.text else ""

            ai_logger.debug(
                f"Gemini attempt {attempt+1} | "
                f"Length: {len(result_text)} chars"
            )

            if result_text:
                break

            time.sleep(1)

        except Exception as e:
            ai_logger.error(f"Gemini API error (attempt {attempt+1}): {e}")
            if attempt == 1:
                return _rejection(f"Gemini API error: {e}")
            time.sleep(2)

    if not result_text:
        return _rejection("Gemini returned empty response")

    # ── استخراج JSON ────────────────────
    result = _extract_json(result_text)

    if result is None:
        ai_logger.warning("JSON extraction failed, using field extraction")
        result = _extract_fields(result_text)

    # ── التحقق من الحقول الأساسية ────────
    required = ["final_score", "approved", "analysis_summary"]
    for field in required:
        if field not in result:
            ai_logger.warning(f"Missing field: {field}, using default")
            result[field] = {"final_score": 5.0,
                             "approved": False,
                             "analysis_summary": "Partial analysis"}[field]

    # ── تطبيق وزن الإطار الزمني ──────────
    tf_weight = TIMEFRAME_WEIGHTS.get(data.get("timeframe", "15m"), 0.7)
    raw_score             = float(result.get("final_score", 0))
    result["final_score"] = round(raw_score * tf_weight, 2)

    # ── فلتر الحد الأدنى ──────────────────
    if result["final_score"] < MIN_SIGNAL_SCORE:
        result["approved"]         = False
        result["rejection_reason"] = (
            f"Score {result['final_score']}/10 "
            f"below minimum {MIN_SIGNAL_SCORE}"
        )

    # ── تطبيع الحقول ─────────────────────
    result["scores"] = {
        "trend":      float(result.get("trend_score",      5.0)),
        "volume":     float(result.get("volume_score",     5.0)),
        "momentum":   float(result.get("momentum_score",   5.0)),
        "volatility": float(result.get("volatility_score", 5.0)),
    }

    if "key_levels" not in result or not isinstance(result["key_levels"], dict):
        price = float(str(data.get("price", "0")).replace(",", ""))
        result["key_levels"] = {
            "support":    round(price * 0.998, 5),
            "resistance": round(price * 1.002, 5),
        }

    ai_logger.info(
        f"✅ Score: {result['final_score']} | "
        f"Approved: {result['approved']} | "
        f"Confidence: {result.get('confidence','N/A')}"
    )

    return result


# ══════════════════════════════════════════
# Helper
# ══════════════════════════════════════════

def _rejection(reason: str) -> dict:
    return {
        "approved":               False,
        "rejection_reason":       reason,
        "final_score":            0.0,
        "scores": {"trend": 0.0, "volume": 0.0,
                   "momentum": 0.0, "volatility": 0.0},
        "trend_score":            0.0,
        "volume_score":           0.0,
        "momentum_score":         0.0,
        "volatility_score":       0.0,
        "confidence":             "LOW",
        "market_condition":       "UNKNOWN",
        "analysis_summary":       reason,
        "risk_reward_assessment": "POOR",
        "key_levels":             {"support": 0.0, "resistance": 0.0},
    }
