"""
Market Filters + TwelveData Fetcher - النسخة المُصحَّحة
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests
import ta

from app.config import (
    TWELVEDATA_API_KEY,
    TWELVEDATA_BASE,
    TIMEFRAME_MAP,
    MIN_VOLUME_RATIO,
    TRADING_START_HOUR,
    TRADING_END_HOUR,
    SESSIONS,
)
from app.logger import filter_logger


class TwelveDataFetcher:

    _cache: dict[str, tuple[float, pd.DataFrame]] = {}
    _TTL = 60

    def get_ohlcv(self, symbol: str, timeframe: str,
                  limit: int = 200) -> pd.DataFrame | None:
        cache_key = f"{symbol}|{timeframe}|{limit}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._TTL:
            return cached[1]

        interval = TIMEFRAME_MAP.get(timeframe, "15min")
        try:
            resp = requests.get(
                f"{TWELVEDATA_BASE}/time_series",
                params={
                    "symbol": symbol, "interval": interval,
                    "apikey": TWELVEDATA_API_KEY,
                    "outputsize": limit, "format": "JSON",
                },
                timeout=12,
            )
            resp.raise_for_status()
            payload = resp.json()

            if payload.get("status") == "error":
                filter_logger.error(
                    f"TwelveData: {payload.get('message','unknown')}"
                )
                return None

            values = payload.get("values", [])
            if not values:
                return None

            df = pd.DataFrame(values)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()

            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df["volume"] = (
                pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
                if "volume" in df.columns else 0.0
            )

            df = df.dropna(subset=["open", "high", "low", "close"])
            self._cache[cache_key] = (time.time(), df)
            filter_logger.info(
                f"✅ {symbol} {timeframe} → {len(df)} candles"
            )
            return df

        except Exception as e:
            filter_logger.error(f"TwelveData error: {e}")
            return None

    def get_indicators(self, df: pd.DataFrame | None) -> dict:
        if df is None or len(df) < 50:
            return {}
        c, h, lo, v = df["close"], df["high"], df["low"], df["volume"]
        try:
            ema20  = ta.trend.EMAIndicator(c, 20).ema_indicator()
            ema50  = ta.trend.EMAIndicator(c, 50).ema_indicator()
            ema200 = ta.trend.EMAIndicator(c, 200).ema_indicator()
            macd_o = ta.trend.MACD(c)
            rsi    = ta.momentum.RSIIndicator(c, 14).rsi()
            atr    = ta.volatility.AverageTrueRange(h, lo, c, 14).average_true_range()
            bb     = ta.volatility.BollingerBands(c, 20, 2)
            stoch  = ta.momentum.StochasticOscillator(h, lo, c, 14, 3)
            vol_sma   = v.rolling(20).mean()
            vol_ratio = (v / vol_sma).fillna(1.0)

            return {
                "ema20":         round(float(ema20.iloc[-1]),  6),
                "ema50":         round(float(ema50.iloc[-1]),  6),
                "ema200":        round(float(ema200.iloc[-1]), 6),
                "macd":          round(float(macd_o.macd().iloc[-1]),        6),
                "macd_signal":   round(float(macd_o.macd_signal().iloc[-1]), 6),
                "macd_hist":     round(float(macd_o.macd_diff().iloc[-1]),   6),
                "rsi":           round(float(rsi.iloc[-1]), 2),
                "stoch_k":       round(float(stoch.stoch().iloc[-1]),        2),
                "stoch_d":       round(float(stoch.stoch_signal().iloc[-1]), 2),
                "atr":           round(float(atr.iloc[-1]), 6),
                "bb_upper":      round(float(bb.bollinger_hband().iloc[-1]), 6),
                "bb_middle":     round(float(bb.bollinger_mavg().iloc[-1]),  6),
                "bb_lower":      round(float(bb.bollinger_lband().iloc[-1]), 6),
                "bb_width":      round(float(bb.bollinger_wband().iloc[-1]), 6),
                "volume":        round(float(v.iloc[-1]),        2),
                "volume_sma":    round(float(vol_sma.iloc[-1]),  2),
                "volume_ratio":  round(float(vol_ratio.iloc[-1]), 3),
                "current_price": round(float(c.iloc[-1]),  6),
                "prev_close":    round(float(c.iloc[-2]),  6),
                "high_session":  round(float(h.tail(24).max()),  6),
                "low_session":   round(float(lo.tail(24).min()), 6),
            }
        except Exception as e:
            filter_logger.error(f"Indicator error: {e}")
            return {}


def run_all_filters(data: dict, ind: dict) -> dict:
    side  = data.get("side",  "BUY")
    price = float(str(data.get("price", "0")).replace(",", ""))

    checks = {
        "Trend":      _trend_filter(side, price, ind),
        "Volume":     _volume_filter(ind),
        "RSI":        _rsi_filter(side, ind),
        "MACD":       _macd_filter(side, ind),
        "Stochastic": _stoch_filter(side, ind),
        "Volatility": _volatility_filter(ind),
        "Session":    _session_filter(),
        "Spread":     _spread_filter(ind),
    }

    blocked = [k for k, v in checks.items() if not v["passed"]]
    return {"passed": len(blocked) == 0,
            "filters": checks, "blocked_by": blocked}


def _trend_filter(side: str, price: float, ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    e20  = float(ind.get("ema20",  0))
    e50  = float(ind.get("ema50",  0))
    e200 = float(ind.get("ema200", 0))

    if side == "BUY":
        c1 = price > e200
        c2 = e20   > e50
        c3 = price > e50
        passed_conditions = sum([c1, c2, c3])
        passed = passed_conditions >= 2
        details = (f"price>EMA200:{'✅' if c1 else '❌'} | "
                   f"EMA20>EMA50:{'✅' if c2 else '❌'} | "
                   f"price>EMA50:{'✅' if c3 else '❌'}")
    else:
        c1 = price < e200
        c2 = e20   < e50
        c3 = price < e50
        passed_conditions = sum([c1, c2, c3])
        passed = passed_conditions >= 2
        details = (f"price<EMA200:{'✅' if c1 else '❌'} | "
                   f"EMA20<EMA50:{'✅' if c2 else '❌'} | "
                   f"price<EMA50:{'✅' if c3 else '❌'}")

    direction = "Bullish" if side == "BUY" else "Bearish"
    reason = (
        f"✅ {direction} ({passed_conditions}/3): {details}"
        if passed else
        f"❌ Weak {direction.lower()} ({passed_conditions}/3): {details}"
    )
    return {
        "passed": passed, "reason": reason,
        "values": {"price": price, "ema20": e20,
                   "ema50": e50, "ema200": e200},
    }


def _volume_filter(ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}
    if ind.get("volume", 0) == 0:
        return {"passed": True,
                "reason": "ℹ️ Volume unavailable — skipped", "value": None}
    vr     = float(ind.get("volume_ratio", 1.0))
    passed = vr >= MIN_VOLUME_RATIO
    return {
        "passed": passed,
        "reason": (f"✅ Volume ×{vr:.2f} ≥ ×{MIN_VOLUME_RATIO}"
                   if passed else
                   f"❌ Volume ×{vr:.2f} < ×{MIN_VOLUME_RATIO}"),
        "value": vr,
    }


def _rsi_filter(side: str, ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}
    rsi    = float(ind.get("rsi", 50.0))
    passed = rsi < 75 if side == "BUY" else rsi > 25
    return {
        "passed": passed,
        "reason": (f"✅ RSI {rsi:.1f} — OK"
                   if passed else
                   f"❌ RSI {rsi:.1f} — extreme for {side}"),
        "value": rsi,
    }


def _macd_filter(side: str, ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}
    macd = float(ind.get("macd",       0.0))
    sig  = float(ind.get("macd_signal",0.0))
    hist = float(ind.get("macd_hist",  0.0))
    passed = (macd > sig or hist > 0) if side == "BUY" else (macd < sig or hist < 0)
    return {
        "passed": passed,
        "reason": (f"✅ MACD {'bullish' if side=='BUY' else 'bearish'} momentum"
                   if passed else
                   f"❌ MACD against {side}"),
        "values": {"macd": macd, "signal": sig, "hist": hist},
    }


def _stoch_filter(side: str, ind: dict) -> dict:
    """Stochastic - مُصحَّح: رفض عند الإفراط الشديد فقط"""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    k = float(ind.get("stoch_k", 50.0))
    d = float(ind.get("stoch_d", 50.0))

    if side == "BUY":
        passed = k < 85      # رفض فقط عند overbought شديد
        if not passed:
            reason = f"❌ Stoch K:{k:.1f} — severely overbought (>85)"
        elif k < 20:
            reason = f"✅ Stoch K:{k:.1f} — oversold, great for BUY"
        else:
            reason = f"✅ Stoch K:{k:.1f} D:{d:.1f} — acceptable for BUY"
    else:
        passed = k > 15      # رفض فقط عند oversold شديد
        if not passed:
            reason = f"❌ Stoch K:{k:.1f} — severely oversold (<15)"
        elif k > 80:
            reason = f"✅ Stoch K:{k:.1f} — overbought, great for SELL"
        else:
            reason = f"✅ Stoch K:{k:.1f} D:{d:.1f} — acceptable for SELL"

    return {"passed": passed, "reason": reason,
            "values": {"k": round(k, 2), "d": round(d, 2)}}


def _volatility_filter(ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}
    atr   = float(ind.get("atr",           0.0))
    price = float(ind.get("current_price",  1.0))
    if price == 0:
        return {"passed": True, "reason": "ℹ️ Price zero — skipped"}
    atr_pct = atr / price * 100
    passed  = atr_pct <= 5.0
    return {
        "passed": passed,
        "reason": (f"✅ ATR {atr_pct:.3f}% — OK"
                   if passed else
                   f"❌ ATR {atr_pct:.3f}% — too volatile"),
        "value": round(atr_pct, 4),
    }


def _session_filter() -> dict:
    now  = datetime.now(timezone.utc)
    hour = now.hour
    in_window = TRADING_START_HOUR <= hour <= TRADING_END_HOUR
    open_sessions = [
        name for name, (start, end) in SESSIONS.items()
        if (start < end and start <= hour < end) or
           (start >= end and (hour >= start or hour < end))
    ]
    label = ", ".join(open_sessions) if open_sessions else "none"
    return {
        "passed": in_window,
        "reason": (f"✅ Active ({label}) — {hour:02d}:00 UTC"
                   if in_window else
                   f"❌ Outside window ({TRADING_START_HOUR}–{TRADING_END_HOUR} UTC)"),
    }


def _spread_filter(ind: dict) -> dict:
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}
    price = float(ind.get("current_price", 0))
    upper = float(ind.get("bb_upper",      0))
    lower = float(ind.get("bb_lower",      0))
    if not upper or not lower or price == 0:
        return {"passed": True, "reason": "ℹ️ BB unavailable — skipped"}
    bb_w   = (upper - lower) / price * 100
    passed = bb_w > 0.05
    return {
        "passed": passed,
        "reason": (f"✅ BB width {bb_w:.3f}% — OK"
                   if passed else
                   f"❌ BB width {bb_w:.3f}% — too tight"),
        "value": round(bb_w, 4),
    }


# ── Singleton ─────────────────────────────
try:
    data_fetcher = TwelveDataFetcher()
    filter_logger.info("✅ TwelveDataFetcher ready")
except Exception as _e:
    filter_logger.error(f"TwelveDataFetcher failed: {_e}")
    data_fetcher = None
