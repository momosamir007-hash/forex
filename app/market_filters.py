"""
Market Filters + TwelveData Fetcher
─────────────────────────────────────
• TwelveDataFetcher  – جلب بيانات OHLCV وحساب المؤشرات
• run_all_filters    – تشغيل جميع فلاتر السوق
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import ta

import requests

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


# ══════════════════════════════════════════
# TwelveData Fetcher
# ══════════════════════════════════════════

class TwelveDataFetcher:
    """
    Fetch OHLCV candles from TwelveData REST API
    and compute technical indicators.

    Built-in cache (60 s TTL) to avoid redundant requests.
    """

    # {cache_key: (timestamp, DataFrame)}
    _cache: dict[str, tuple[float, pd.DataFrame]] = {}
    _TTL   = 60   # seconds

    # ── Public: OHLCV ─────────────────────

    def get_ohlcv(
        self,
        symbol:    str,
        timeframe: str,
        limit:     int = 200,
    ) -> pd.DataFrame | None:
        """
        Return OHLCV DataFrame.
        Columns: open, high, low, close, volume
        Index:   datetime (UTC)
        """
        cache_key = f"{symbol}|{timeframe}|{limit}"
        cached    = self._cache.get(cache_key)

        if cached and (time.time() - cached[0]) < self._TTL:
            filter_logger.debug(f"Cache hit: {cache_key}")
            return cached[1]

        interval = TIMEFRAME_MAP.get(timeframe, "15min")

        try:
            resp = requests.get(
                f"{TWELVEDATA_BASE}/time_series",
                params={
                    "symbol":     symbol,
                    "interval":   interval,
                    "apikey":     TWELVEDATA_API_KEY,
                    "outputsize": limit,
                    "format":     "JSON",
                },
                timeout=12,
            )
            resp.raise_for_status()
            payload = resp.json()

            # ── API error ─────────────────
            if payload.get("status") == "error":
                filter_logger.error(
                    f"TwelveData API error for {symbol}: "
                    f"{payload.get('message','unknown')}"
                )
                return None

            values = payload.get("values", [])
            if not values:
                filter_logger.warning(f"No values returned for {symbol}")
                return None

            # ── Build DataFrame ───────────
            df = pd.DataFrame(values)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()

            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # volume absent for many FX pairs
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
            else:
                df["volume"] = 0.0

            df = df.dropna(subset=["open", "high", "low", "close"])

            self._cache[cache_key] = (time.time(), df)

            filter_logger.info(
                f"✅ TwelveData: {symbol} {timeframe} "
                f"→ {len(df)} candles"
            )
            return df

        except requests.exceptions.Timeout:
            filter_logger.error(f"TwelveData timeout for {symbol}")
            return None

        except requests.exceptions.RequestException as e:
            filter_logger.error(f"TwelveData request error: {e}")
            return None

        except Exception as e:
            filter_logger.error(f"TwelveData unexpected error: {e}")
            return None

    # ── Public: Indicators ────────────────

    def get_indicators(
        self,
        df: pd.DataFrame | None,
    ) -> dict:
        """
        Calculate all technical indicators from OHLCV DataFrame.
        Returns empty dict if data is insufficient.
        """
        if df is None or len(df) < 50:
            filter_logger.warning("Insufficient data for indicators")
            return {}

        c  = df["close"]
        h  = df["high"]
        lo = df["low"]
        v  = df["volume"]

        try:
            # ── Moving Averages ───────────
            ema20  = ta.trend.EMAIndicator(c, 20).ema_indicator()
            ema50  = ta.trend.EMAIndicator(c, 50).ema_indicator()
            ema200 = ta.trend.EMAIndicator(c, 200).ema_indicator()

            # ── MACD ──────────────────────
            macd_obj  = ta.trend.MACD(c)
            macd_line = macd_obj.macd()
            macd_sig  = macd_obj.macd_signal()
            macd_hist = macd_obj.macd_diff()

            # ── RSI ───────────────────────
            rsi = ta.momentum.RSIIndicator(c, 14).rsi()

            # ── Volatility ────────────────
            atr = ta.volatility.AverageTrueRange(
                h, lo, c, 14
            ).average_true_range()

            bb  = ta.volatility.BollingerBands(c, 20, 2)

            # ── Stochastic ────────────────
            stoch = ta.momentum.StochasticOscillator(
                h, lo, c, 14, 3
            )

            # ── Volume ────────────────────
            vol_sma   = v.rolling(20).mean()
            vol_ratio = (v / vol_sma).fillna(1.0)

            return {
                # EMAs
                "ema20":          round(float(ema20.iloc[-1]),  6),
                "ema50":          round(float(ema50.iloc[-1]),  6),
                "ema200":         round(float(ema200.iloc[-1]), 6),

                # MACD
                "macd":           round(float(macd_line.iloc[-1]), 6),
                "macd_signal":    round(float(macd_sig.iloc[-1]),  6),
                "macd_hist":      round(float(macd_hist.iloc[-1]), 6),

                # RSI
                "rsi":            round(float(rsi.iloc[-1]), 2),

                # Stochastic
                "stoch_k":        round(float(stoch.stoch().iloc[-1]),        2),
                "stoch_d":        round(float(stoch.stoch_signal().iloc[-1]), 2),

                # ATR & BB
                "atr":            round(float(atr.iloc[-1]),              6),
                "bb_upper":       round(float(bb.bollinger_hband().iloc[-1]), 6),
                "bb_middle":      round(float(bb.bollinger_mavg().iloc[-1]),  6),
                "bb_lower":       round(float(bb.bollinger_lband().iloc[-1]), 6),
                "bb_width":       round(float(bb.bollinger_wband().iloc[-1]), 6),

                # Volume
                "volume":         round(float(v.iloc[-1]),        2),
                "volume_sma":     round(float(vol_sma.iloc[-1]),  2),
                "volume_ratio":   round(float(vol_ratio.iloc[-1]), 3),

                # Price reference
                "current_price":  round(float(c.iloc[-1]),          6),
                "prev_close":     round(float(c.iloc[-2]),           6),
                "high_session":   round(float(h.tail(24).max()),     6),
                "low_session":    round(float(lo.tail(24).min()),    6),
            }

        except Exception as e:
            filter_logger.error(f"Indicator calculation error: {e}")
            return {}


# ══════════════════════════════════════════
# Market Filters
# ══════════════════════════════════════════

def run_all_filters(data: dict, ind: dict) -> dict:
    """
    Run every market filter and aggregate results.

    Returns
    -------
    dict:
        passed     bool   – 
