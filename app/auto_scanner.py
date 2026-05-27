"""
Auto Scanner - نسخة متوازنة
معايير واقعية تجد فرص حقيقية
"""

from __future__ import annotations

import time
import pandas as pd
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config          import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS
from app.market_filters  import data_fetcher, run_all_filters
from app.price_action    import analyze_price_action
from app.smart_money     import analyze_smc
from app.multi_timeframe import analyze_mtf
from app.news_filter     import check_news_risk
from app.signal_scorer   import calculate_score
from app.entry_engine    import entry_engine
from app.ai_filter       import analyze_signal
from app.logger          import main_logger


# ══════════════════════════════════════════
# Scan Thresholds - قابلة للتعديل
# ══════════════════════════════════════════

SCAN_TIMEFRAMES = ["15m", "1h", "4h"]

# المعايير الصارمة → للـ Signal Analyzer اليدوي
STRICT = {
    "min_score":     7.5,
    "min_rr":        1.5,
    "min_confidence":60,
    "min_mtf":       50,
}

# المعايير المتوسطة → للـ Auto Scanner
MODERATE = {
    "min_score":     6.0,
    "min_rr":        1.3,
    "min_confidence":45,
    "min_mtf":       25,
}

# المعايير المخففة → للاكتشاف فقط
RELAXED = {
    "min_score":     5.0,
    "min_rr":        1.0,
    "min_confidence":35,
    "min_mtf":       0,
}


# ══════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════

class AutoScanner:

    def __init__(self):
        self.last_scan:    datetime | None = None
        self.last_results: list[dict]      = []
        self.scan_stats:   dict            = {}

    # ── Full Scan ─────────────────────────

    def scan_all(
        self,
        timeframes:   list[str] | None = None,
        pairs:        list[str] | None = None,
        use_ai:       bool  = False,
        max_workers:  int   = 4,
        mode:         str   = "moderate",   # strict / moderate / relaxed
    ) -> list[dict]:
        """
        يفحص السوق ويعيد الفرص المكتشفة.

        Parameters
        ----------
        mode : str
            "strict"   → معايير عالية  (إشارات أقل لكن أجود)
            "moderate" → معايير وسطى   (الافتراضي)
            "relaxed"  → معايير منخفضة (اكتشاف أكثر)
        """
        tfs  = timeframes or SCAN_TIMEFRAMES
        syms = pairs      or list(SUPPORTED_PAIRS.keys())

        thresholds = {
            "strict":   STRICT,
            "moderate": MODERATE,
            "relaxed":  RELAXED,
        }.get(mode, MODERATE)

        tasks = [(sym, tf) for sym in syms for tf in tfs]

        main_logger.info(
            f"🔍 Scan [{mode}] | "
            f"{len(syms)} pairs × {len(tfs)} TFs = {len(tasks)} checks"
        )

        raw: list[dict] = []

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(
                    self._scan_one, sym, tf, use_ai, thresholds
                ): (sym, tf)
                for sym, tf in tasks
            }
            for future in as_completed(futures):
                sym, tf = futures[future]
                try:
                    r = future.result(timeout=30)
                    if r:
                        raw.append(r)
                except Exception as e:
                    main_logger.warning(f"Error {sym} {tf}: {e}")

        results = self._post_process(raw)

        self.last_scan    = datetime.now(timezone.utc)
        self.last_results = results
        self.scan_stats   = {
            "mode":       mode,
            "total_checked": len(tasks),
            "raw_found":  len(raw),
            "after_filter": len(results),
        }

        main_logger.info(
            f"✅ Done | Checked: {len(tasks)} | "
            f"Raw: {len(raw)} | Final: {len(results)}"
        )
        return results

    # ── Post Processing ───────────────────

    def _post_process(self, raw: list[dict]) -> list[dict]:
        """
        فلترة خفيفة فقط:
        - رفض التناقض الصريح (patterns هبوطية مع BUY)
        - أفضل فرصة لكل زوج
        - ترتيب حسب النقاط
        """
        filtered: list[dict] = []

        for r in raw:
            # رفض التناقض الصريح فقط (ليس NEUTRAL)
            if self._hard_conflict(r):
                continue
            filtered.append(r)

        # أفضل timeframe لكل زوج
        best: dict[str, dict] = {}
        for r in filtered:
            sym = r["symbol"]
            if sym not in best or \
               r["final_score"] > best[sym]["final_score"]:
                best[sym] = r

        return sorted(
            best.values(),
            key=lambda x: (x["final_score"], x["rr_ratio"]),
            reverse=True,
        )

    def _hard_conflict(self, r: dict) -> bool:
        """
        رفض التناقض الصريح فقط:
        أنماط هبوطية قوية مع BUY
        أنماط صاعدة قوية مع SELL
        """
        patterns = r.get("patterns", [])
        side     = r.get("side", "BUY")

        STRONG_BEAR = {
            "Bearish Engulfing 🔴",
            "Evening Star 🌆",
            "Three Black Crows 🐦‍⬛",
        }
        STRONG_BULL = {
            "Bullish Engulfing 🟢",
            "Morning Star 🌟",
            "Three White Soldiers 💪",
        }

        if side == "BUY" and patterns:
            if all(p in STRONG_BEAR for p in patterns):
                return True

        if side == "SELL" and patterns:
            if all(p in STRONG_BULL for p in patterns):
                return True

        return False

    # ── Scan One ─────────────────────────

    def _scan_one(
        self,
        symbol:     str,
        timeframe:  str,
        use_ai:     bool,
        thresholds: dict,
    ) -> dict | None:

        try:
            # ── 1. Data ───────────────────
            df = data_fetcher.get_ohlcv(symbol, timeframe, limit=200)
            if df is None or len(df) < 50:
                return None

            ind = data_fetcher.get_indicators(df)
            if not ind:
                return None

            price = float(ind.get("current_price", 0))
            if price == 0:
                return None

            # ── 2. Direction ──────────────
            side = self._detect_direction(df, ind)

            # ── 3. News ───────────────────
            news = check_news_risk(symbol)
            if not news["safe"]:
                return None

            # ── 4. Entry Engine ───────────
            entry = entry_engine.analyze(df, side, symbol)

            if entry["entry_type"] == "WAIT":
                return None

            # R:R check
            if entry["rr_ratio"] < thresholds["min_rr"]:
                main_logger.debug(
                    f"Skip {symbol} {timeframe}: "
                    f"R:R {entry['rr_ratio']} < {thresholds['min_rr']}"
                )
                return None

            # Confidence check
            if entry["confidence"] < thresholds["min_confidence"]:
                main_logger.debug(
                    f"Skip {symbol} {timeframe}: "
                    f"Conf {entry['confidence']:.0f}% "
                    f"< {thresholds['min_confidence']}%"
                )
                return None

            # ── 5. Filters ────────────────
            sig = {
                "symbol": symbol, "side": side,
                "price": str(price), "timeframe": timeframe,
                **{k: str(v) for k, v in ind.items()},
            }
            filters = run_all_filters(sig, ind)

            # ── 6. PA ─────────────────────
            pa = analyze_price_action(df, side)

            # ── 7. SMC ────────────────────
            smc = analyze_smc(df, side)

            # ── 8. MTF ────────────────────
            mtf     = analyze_mtf(symbol, timeframe, side)
            mtf_pct = float(mtf.get("alignment_pct", 0))

            if mtf_pct < thresholds["min_mtf"]:
                main_logger.debug(
                    f"Skip {symbol} {timeframe}: "
                    f"MTF {mtf_pct:.0f}% < {thresholds['min_mtf']}%"
                )
                return None

            # ── 9. Score ──────────────────
            score = calculate_score(
                ai_result     = {"final_score": 7.0, "approved": True},
                filter_result = filters,
                pa_result     = pa,
                smc_result    = smc,
                mtf_result    = mtf,
                news_result   = news,
            )

            if score["final_score"] < thresholds["min_score"]:
                main_logger.debug(
                    f"Skip {symbol} {timeframe}: "
                    f"Score {score['final_score']} "
                    f"< {thresholds['min_score']}"
                )
                return None

            # ── 10. AI (optional) ─────────
            ai_result = None
            if use_ai:
                ai_result = analyze_signal(sig, ind)
                if not ai_result.get("approved"):
                    return None
                score = calculate_score(
                    ai_result, filters, pa, smc, mtf, news
                )
                if score["final_score"] < thresholds["min_score"]:
                    return None

            # ── Build Result ──────────────
            pair_info = SUPPORTED_PAIRS.get(symbol, {})

            # نقاط الفلاتر التقنية
            passed_filters = sum(
                1 for v in filters["filters"].values()
                if v["passed"]
            )
            total_filters  = len(filters["filters"])

            return {
                # Identity
                "symbol":     symbol,
                "timeframe":  timeframe,
                "side":       side,
                "pair_name":  pair_info.get("name", symbol),
                "emoji":      pair_info.get("emoji", "💱"),
                "category":   pair_info.get("category", "forex"),

                # Entry
                "entry_type":    entry["entry_type"],
                "entry_price":   entry["entry_price"],
                "stop_loss":     entry["stop_loss"],
                "take_profit_1": entry["take_profit_1"],
                "take_profit_2": entry["take_profit_2"],
                "take_profit_3": entry["take_profit_3"],
                "rr_ratio":      entry["rr_ratio"],
                "entry_reason":  entry["reason"],
                "structure":     entry["structure"],
                "atr":           entry.get("atr", 0),
                "sr_levels":     entry.get("sr_levels", {}),

                # Scores
                "final_score":   score["final_score"],
                "grade":         score["grade"],
                "breakdown":     score["breakdown"],
                "confidence":    entry["confidence"],

                # Filters
                "filters_passed": f"{passed_filters}/{total_filters}",
                "blocked_by":     filters.get("blocked_by", []),

                # Analysis
                "patterns":   pa.get("patterns",  []),
                "pa_score":   pa.get("score",      0),
                "ranging":    pa.get("ranging",    False),
                "smc_score":  smc.get("score",     0),
                "ob_found":   smc.get("ob", {}).get("found", False),
                "ob_zone":    smc.get("ob", {}).get("in_zone", False),
                "sweep":      smc.get("sweep",     False),
                "bos":        smc.get("bos",       False),
                "mtf_aligned": mtf_pct,
                "mtf_details": mtf.get("details",  {}),

                # AI
                "ai_used":  use_ai,
                "ai_score": (ai_result.get("final_score")
                             if ai_result else None),

                # Meta
                "scanned_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
            }

        except Exception as e:
            main_logger.warning(
                f"_scan_one error {symbol} {timeframe}: {e}"
            )
            return None

    # ── Direction Detection ────────────────

    def _detect_direction(self, df: pd.DataFrame, ind: dict) -> str:
        bull = 0
        bear = 0

        price = float(ind.get("current_price", df["close"].iloc[-1]))
        e20   = float(ind.get("ema20",  0))
        e50   = float(ind.get("ema50",  0))
        e200  = float(ind.get("ema200", 0))

        # EMA
        if price > e200: bull += 3
        else:            bear += 3
        if e20 > e50:    bull += 2
        else:            bear += 2
        if price > e50:  bull += 1
        else:            bear += 1

        # RSI
        rsi = float(ind.get("rsi", 50))
        if rsi < 35:   bull += 2
        elif rsi > 65: bear += 2
        elif rsi > 50: bull += 1
        else:          bear += 1

        # MACD
        hist = float(ind.get("macd_hist", 0))
        if hist > 0: bull += 1
        else:        bear += 1

        # Stochastic
        k = float(ind.get("stoch_k", 50))
        if k < 20:   bull += 2
        elif k > 80: bear += 2

        # آخر شمعة
        c = df["close"].values
        o = df["open"].values
        if c[-1] > o[-1]: bull += 1
        else:             bear += 1

        return "BUY" if bull >= bear else "SELL"


# ── Singleton ─────────────────────────────
auto_scanner = AutoScanner()
