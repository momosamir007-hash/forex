"""
Entry Engine - نسخة مُصلحة
المشكلة الرئيسية: شرط near_support صارم جداً
الحل: توسيع نطاق البحث + fallback عند عدم وجود S/R
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import ta
from app.logger import main_logger


class EntryEngine:

    def analyze(
        self,
        df:     pd.DataFrame,
        side:   str,
        symbol: str,
    ) -> dict:
        if df is None or len(df) < 30:
            return self._no_entry("Insufficient data")

        price = float(df["close"].iloc[-1])
        atr   = self._get_atr(df)

        if atr == 0 or price == 0:
            return self._no_entry("ATR or price is zero")

        sr        = self._find_sr_levels(df, atr, price)
        structure = self._market_structure(df)
        indicators = self._get_indicators(df)

        # ── محاولة إيجاد إعداد ────────────
        entry = self._find_best_entry(df, side, atr, sr, indicators)

        if entry["type"] == "WAIT":
            return self._no_entry(entry["reason"])

        sl   = self._calculate_sl(df, side, entry["price"], atr, sr)
        tps  = self._calculate_tps(
            side, entry["price"], sl, sr, atr
        )

        risk   = abs(entry["price"] - sl)
        reward = abs(tps["tp1"] - entry["price"])

        if risk == 0:
            return self._no_entry("Risk distance is zero")

        rr   = round(reward / risk, 2)
        conf = self._confidence(
            indicators, side, rr, structure, sr, atr, price
        )

        return {
            "entry_type":      entry["type"],
            "entry_price":     round(entry["price"], 5),
            "stop_loss":       round(sl, 5),
            "take_profit_1":   round(tps["tp1"], 5),
            "take_profit_2":   round(tps["tp2"], 5),
            "take_profit_3":   round(tps["tp3"], 5),
            "rr_ratio":        rr,
            "confidence":      round(conf, 1),
            "reason":          entry["reason"],
            "invalidation":    round(sl, 5),
            "atr":             round(atr, 6),
            "structure":       structure,
            "sr_levels":       sr,
            "risk_distance":   round(risk, 6),
            "reward_distance": round(reward, 6),
        }

    # ══════════════════════════════════════
    # Core: Find Best Entry
    # ══════════════════════════════════════

    def _find_best_entry(
        self,
        df:         pd.DataFrame,
        side:       str,
        atr:        float,
        sr:         dict,
        indicators: dict,
    ) -> dict:
        """
        يبحث عن أفضل إعداد دخول بهذا الترتيب:
        1. Pattern قوي
        2. قرب S/R (بنطاق واسع)
        3. Momentum إعداد
        4. Trend following (fallback)
        """
        c  = df["close"].values
        o  = df["open"].values
        h  = df["high"].values
        lo = df["low"].values
        price = float(c[-1])

        ns  = float(sr.get("nearest_support",    price * 0.995))
        nr  = float(sr.get("nearest_resistance", price * 1.005))

        dist_support    = abs(price - ns)
        dist_resistance = abs(price - nr)

        # نسبة البعد بالنسبة للـ ATR
        atr_to_support    = dist_support    / atr if atr else 99
        atr_to_resistance = dist_resistance / atr if atr else 99

        rsi   = float(indicators.get("rsi",      50))
        macd  = float(indicators.get("macd",      0))
        msig  = float(indicators.get("macd_sig",  0))
        stoch = float(indicators.get("stoch_k",  50))

        # ── بيانات الشمعة ─────────────────
        body       = abs(c[-1] - o[-1])
        candle_rng = h[-1] - lo[-1]
        body_ratio = body / candle_rng if candle_rng > 0 else 0
        is_bull    = c[-1] > o[-1]
        is_bear    = c[-1] < o[-1]

        # ──────────────────────────────────
        # BUY Setups
        # ──────────────────────────────────
        if side == "BUY":

            # 1. Bullish Engulfing (في أي مكان)
            if (is_bull and not (c[-2] > o[-2]) and
                    c[-1] > o[-2] and o[-1] < c[-2] and
                    body > abs(c[-2] - o[-2]) * 0.8):
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": f"Bullish Engulfing | RSI:{rsi:.0f}",
                }

            # 2. قرب Support (نطاق 4 ATR)
            if atr_to_support <= 4.0:
                # Pin Bar
                if (lo[-1] < lo[-2] and
                        (c[-1] - lo[-1]) > body * 2 and
                        (h[-1] - c[-1]) < body):
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Bullish Pin Bar at support "
                            f"{ns:.5f} "
                            f"({atr_to_support:.1f} ATR away)"
                        ),
                    }

                # Hammer
                if (candle_rng > 0 and
                        (lo[-1] - min(c[-1], o[-1])) / candle_rng > 0.5):
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Hammer at support "
                            f"{ns:.5f}"
                        ),
                    }

                # شمعة صاعدة قرب support
                if is_bull and body_ratio > 0.4:
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Bullish close near support "
                            f"{ns:.5f} "
                            f"({atr_to_support:.1f} ATR)"
                        ),
                    }

                # Limit عند Support
                if atr_to_support <= 3.0:
                    lp = round(ns + atr * 0.1, 5)
                    return {
                        "type":   "LIMIT",
                        "price":  lp,
                        "reason": (
                            f"Limit BUY at support zone "
                            f"{ns:.5f}"
                        ),
                    }

            # 3. RSI Oversold + MACD Bullish
            if rsi < 35 and macd > msig:
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"RSI oversold {rsi:.0f} + "
                        f"MACD bullish crossover"
                    ),
                }

            # 4. Stochastic Oversold
            if stoch < 20 and is_bull:
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Stochastic oversold {stoch:.0f} "
                        f"+ bullish candle"
                    ),
                }

            # 5. Trend Following (Fallback)
            e20 = float(indicators.get("ema20", 0))
            e50 = float(indicators.get("ema50", 0))
            if (price > e20 > e50 and
                    is_bull and body_ratio > 0.5 and
                    rsi < 65):
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Trend follow: price above "
                        f"EMA20>EMA50 | RSI:{rsi:.0f}"
                    ),
                }

            # 6. Momentum Pullback
            if (macd > msig and rsi > 45 and rsi < 60 and is_bull):
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Momentum BUY: MACD bullish "
                        f"RSI:{rsi:.0f}"
                    ),
                }

        # ──────────────────────────────────
        # SELL Setups
        # ──────────────────────────────────
        else:

            # 1. Bearish Engulfing
            if (is_bear and c[-2] > o[-2] and
                    c[-1] < o[-2] and o[-1] > c[-2] and
                    body > abs(c[-2] - o[-2]) * 0.8):
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": f"Bearish Engulfing | RSI:{rsi:.0f}",
                }

            # 2. قرب Resistance (نطاق 4 ATR)
            if atr_to_resistance <= 4.0:
                # Pin Bar
                if (h[-1] > h[-2] and
                        (h[-1] - c[-1]) > body * 2 and
                        (c[-1] - lo[-1]) < body):
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Bearish Pin Bar at resistance "
                            f"{nr:.5f}"
                        ),
                    }

                # Shooting Star
                if (candle_rng > 0 and
                        (max(c[-1], o[-1]) - lo[-1]) / candle_rng < 0.3
                        and (h[-1] - max(c[-1], o[-1])) / candle_rng > 0.5):
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Shooting Star at resistance "
                            f"{nr:.5f}"
                        ),
                    }

                # شمعة هابطة قرب resistance
                if is_bear and body_ratio > 0.4:
                    return {
                        "type":   "MARKET",
                        "price":  price,
                        "reason": (
                            f"Bearish close near resistance "
                            f"{nr:.5f} "
                            f"({atr_to_resistance:.1f} ATR)"
                        ),
                    }

                # Limit عند Resistance
                if atr_to_resistance <= 3.0:
                    lp = round(nr - atr * 0.1, 5)
                    return {
                        "type":   "LIMIT",
                        "price":  lp,
                        "reason": (
                            f"Limit SELL at resistance zone "
                            f"{nr:.5f}"
                        ),
                    }

            # 3. RSI Overbought + MACD Bearish
            if rsi > 65 and macd < msig:
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"RSI overbought {rsi:.0f} + "
                        f"MACD bearish crossover"
                    ),
                }

            # 4. Stochastic Overbought
            if stoch > 80 and is_bear:
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Stochastic overbought {stoch:.0f} "
                        f"+ bearish candle"
                    ),
                }

            # 5. Trend Following (Fallback)
            e20 = float(indicators.get("ema20", 0))
            e50 = float(indicators.get("ema50", 0))
            if (price < e20 < e50 and
                    is_bear and body_ratio > 0.5 and
                    rsi > 35):
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Trend follow: price below "
                        f"EMA20<EMA50 | RSI:{rsi:.0f}"
                    ),
                }

            # 6. Momentum Pullback
            if macd < msig and rsi > 40 and rsi < 55 and is_bear:
                return {
                    "type":   "MARKET",
                    "price":  price,
                    "reason": (
                        f"Momentum SELL: MACD bearish "
                        f"RSI:{rsi:.0f}"
                    ),
                }

        return {
            "type":   "WAIT",
            "price":  price,
            "reason": (
                f"No setup found | "
                f"RSI:{rsi:.0f} | "
                f"Stoch:{stoch:.0f} | "
                f"S/R dist: {atr_to_support:.1f}/{atr_to_resistance:.1f} ATR"
            ),
        }

    # ══════════════════════════════════════
    # Indicators
    # ══════════════════════════════════════

    def _get_indicators(self, df: pd.DataFrame) -> dict:
        try:
            c  = df["close"]
            h  = df["high"]
            lo = df["low"]

            rsi   = ta.momentum.RSIIndicator(c, 14).rsi()
            macd  = ta.trend.MACD(c)
            stoch = ta.momentum.StochasticOscillator(h, lo, c, 14, 3)
            e20   = c.ewm(span=20).mean()
            e50   = c.ewm(span=50).mean()
            e200  = c.ewm(span=200).mean()

            return {
                "rsi":      float(rsi.iloc[-1]),
                "macd":     float(macd.macd().iloc[-1]),
                "macd_sig": float(macd.macd_signal().iloc[-1]),
                "stoch_k":  float(stoch.stoch().iloc[-1]),
                "ema20":    float(e20.iloc[-1]),
                "ema50":    float(e50.iloc[-1]),
                "ema200":   float(e200.iloc[-1]),
            }
        except Exception:
            return {
                "rsi": 50.0, "macd": 0.0, "macd_sig": 0.0,
                "stoch_k": 50.0,
                "ema20": 0.0, "ema50": 0.0, "ema200": 0.0,
            }

    # ══════════════════════════════════════
    # ATR
    # ══════════════════════════════════════

    def _get_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            val = ta.volatility.AverageTrueRange(
                df["high"], df["low"], df["close"], period
            ).average_true_range().iloc[-1]
            v = float(val)
            return v if not np.isnan(v) and v > 0 else 0.0
        except Exception:
            rng = (df["high"] - df["low"]).tail(14).mean()
            return float(rng) if float(rng) > 0 else 0.0

    # ══════════════════════════════════════
    # Support / Resistance
    # ══════════════════════════════════════

    def _find_sr_levels(
        self,
        df:    pd.DataFrame,
        atr:   float,
        price: float,
    ) -> dict:
        h  = df["high"].values
        lo = df["low"].values
        n  = len(df)

        levels: list[float] = []

        # Pivot points
        lb = min(3, n // 10)
        for i in range(lb, n - lb):
            if all(h[i] >= h[i-j] for j in range(1, lb+1)) and \
               all(h[i] >= h[i+j] for j in range(1, lb+1)):
                levels.append(float(h[i]))
            if all(lo[i] <= lo[i-j] for j in range(1, lb+1)) and \
               all(lo[i] <= lo[i+j] for j in range(1, lb+1)):
                levels.append(float(lo[i]))

        # Session extremes
        levels.append(float(h[-20:].max()))
        levels.append(float(lo[-20:].min()))
        levels.append(float(h[-50:].max()))
        levels.append(float(lo[-50:].min()))
        levels.append(float(h[-100:].max()) if n >= 100 else float(h.max()))
        levels.append(float(lo[-100:].min()) if n >= 100 else float(lo.min()))

        # إذا لم توجد مستويات → استخدم ATR
        if not levels or len(levels) < 2:
            return {
                "supports":    [
                    round(price - atr * 1.5, 5),
                    round(price - atr * 3.0, 5),
                    round(price - atr * 5.0, 5),
                ],
                "resistances": [
                    round(price + atr * 1.5, 5),
                    round(price + atr * 3.0, 5),
                    round(price + atr * 5.0, 5),
                ],
                "nearest_support":    round(price - atr * 1.5, 5),
                "nearest_resistance": round(price + atr * 1.5, 5),
            }

        arr   = np.array(list(set(levels)))
        below = np.sort(arr[arr < price])[::-1]
        above = np.sort(arr[arr > price])

        # fallback إذا لا توجد مستويات فوق أو تحت
        if len(below) == 0:
            below = np.array([price - atr * 2])
        if len(above) == 0:
            above = np.array([price + atr * 2])

        return {
            "supports":    [round(x, 5) for x in below[:5]],
            "resistances": [round(x, 5) for x in above[:5]],
            "nearest_support":    round(float(below[0]), 5),
            "nearest_resistance": round(float(above[0]), 5),
        }

    # ══════════════════════════════════════
    # Market Structure
    # ══════════════════════════════════════

    def _market_structure(self, df: pd.DataFrame) -> str:
        c  = df["close"].values
        e20 = float(pd.Series(c).ewm(span=20).mean().iloc[-1])
        e50 = float(pd.Series(c).ewm(span=50).mean().iloc[-1])
        cur = float(c[-1])

        if cur > e20 > e50:
            return "BULLISH"
        elif cur < e20 < e50:
            return "BEARISH"
        else:
            return "NEUTRAL"

    # ══════════════════════════════════════
    # Stop Loss
    # ══════════════════════════════════════

    def _calculate_sl(
        self,
        df:    pd.DataFrame,
        side:  str,
        entry: float,
        atr:   float,
        sr:    dict,
    ) -> float:
        lo = df["low"].values
        h  = df["high"].values

        if side == "BUY":
            recent_low = float(lo[-10:].min())
            support    = float(sr.get("nearest_support", entry - atr * 2))
            sl = min(recent_low, support) - atr * 0.3
            # حدود
            sl = max(sl, entry - atr * 4.0)
            sl = min(sl, entry - atr * 0.5)
        else:
            recent_high = float(h[-10:].max())
            resistance  = float(sr.get("nearest_resistance", entry + atr * 2))
            sl = max(recent_high, resistance) + atr * 0.3
            sl = min(sl, entry + atr * 4.0)
            sl = max(sl, entry + atr * 0.5)

        return round(sl, 5)

    # ══════════════════════════════════════
    # Take Profits
    # ══════════════════════════════════════

    def _calculate_tps(
        self,
        side:  str,
        entry: float,
        sl:    float,
        sr:    dict,
        atr:   float,
    ) -> dict:
        risk = abs(entry - sl)
        if risk == 0:
            risk = atr

        if side == "BUY":
            tp1 = entry + risk * 1.5
            tp2 = entry + risk * 2.5
            tp3 = entry + risk * 4.0

            # تحسين بناءً على Resistance
            for r in sr.get("resistances", []):
                r = float(r)
                if tp1 * 0.998 < r < tp1 * 1.05:
                    tp1 = r - atr * 0.1
                    break
            for r in sr.get("resistances", []):
                r = float(r)
                if tp1 < r < tp3:
                    tp2 = r - atr * 0.1
                    break
        else:
            tp1 = entry - risk * 1.5
            tp2 = entry - risk * 2.5
            tp3 = entry - risk * 4.0

            for s in sr.get("supports", []):
                s = float(s)
                if tp1 * 0.995 < s < tp1 * 1.002:
                    tp1 = s + atr * 0.1
                    break
            for s in sr.get("supports", []):
                s = float(s)
                if tp3 < s < tp1:
                    tp2 = s + atr * 0.1
                    break

        return {
            "tp1": round(tp1, 5),
            "tp2": round(tp2, 5),
            "tp3": round(tp3, 5),
        }

    # ══════════════════════════════════════
    # Confidence
    # ══════════════════════════════════════

    def _confidence(
        self,
        ind:       dict,
        side:      str,
        rr:        float,
        structure: str,
        sr:        dict,
        atr:       float,
        price:     float,
    ) -> float:
        score = 45.0

        # Structure
        if side == "BUY":
            if structure == "BULLISH":  score += 20
            elif structure == "NEUTRAL": score += 8
            else:                        score += 0
        else:
            if structure == "BEARISH":  score += 20
            elif structure == "NEUTRAL": score += 8
            else:                        score += 0

        # R:R
        if rr >= 3.0:    score += 20
        elif rr >= 2.0:  score += 14
        elif rr >= 1.5:  score += 8
        elif rr >= 1.2:  score += 4

        # RSI
        rsi = float(ind.get("rsi", 50))
        if side == "BUY":
            if rsi < 30:           score += 12
            elif rsi < 45:         score += 7
            elif rsi < 60:         score += 3
            elif rsi > 70:         score -= 5
        else:
            if rsi > 70:           score += 12
            elif rsi > 55:         score += 7
            elif rsi > 40:         score += 3
            elif rsi < 30:         score -= 5

        # MACD alignment
        macd = float(ind.get("macd",     0))
        msig = float(ind.get("macd_sig", 0))
        if side == "BUY"  and macd > msig: score += 5
        if side == "SELL" and macd < msig: score += 5

        return max(0.0, min(100.0, score))

    # ══════════════════════════════════════
    # No Entry
    # ══════════════════════════════════════

    def _no_entry(self, reason: str) -> dict:
        return {
            "entry_type":      "WAIT",
            "entry_price":     0.0,
            "stop_loss":       0.0,
            "take_profit_1":   0.0,
            "take_profit_2":   0.0,
            "take_profit_3":   0.0,
            "rr_ratio":        0.0,
            "confidence":      0.0,
            "reason":          reason,
            "invalidation":    0.0,
            "atr":             0.0,
            "structure":       "UNKNOWN",
            "sr_levels":       {},
            "risk_distance":   0.0,
            "reward_distance": 0.0,
        }


# ── Singleton ─────────────────────────────
entry_engine = EntryEngine()
