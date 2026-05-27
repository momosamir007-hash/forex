"""
Scanner Scheduler
─────────────────
يشغّل المسح التلقائي في الخلفية كل X دقيقة
ويحفظ النتائج في session_state و database.

الاستخدام:
    from app.scanner_scheduler import scheduler
    scheduler.start()
    scheduler.stop()
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

from app.auto_scanner import auto_scanner
from app.config       import SUPPORTED_PAIRS
from app.logger       import main_logger


# ══════════════════════════════════════════
# Scheduler
# ══════════════════════════════════════════

class ScannerScheduler:
    """
    Thread-based scheduler يشغّل المسح كل interval دقيقة.

    Attributes
    ----------
    interval_minutes : int
        الفترة بين كل مسح وآخر (افتراضي 15 دقيقة)
    pairs : list[str]
        الأزواج التي يفحصها
    timeframes : list[str]
        الإطارات الزمنية
    use_ai : bool
        هل يستخدم Gemini AI في كل مسح
    on_result : Callable | None
        callback يُستدعى عند وجود نتائج جديدة
    """

    def __init__(
        self,
        interval_minutes: int        = 15,
        pairs:            list[str]  | None = None,
        timeframes:       list[str]  | None = None,
        use_ai:           bool       = False,
        on_result:        Callable   | None = None,
    ):
        self.interval_minutes = interval_minutes
        self.pairs            = pairs      or list(SUPPORTED_PAIRS.keys())
        self.timeframes       = timeframes or ["15m", "1h", "4h"]
        self.use_ai           = use_ai
        self.on_result        = on_result

        # State
        self._running:  bool                   = False
        self._thread:   threading.Thread | None = None
        self._lock:     threading.Lock          = threading.Lock()

        # Results store
        self.last_results:  list[dict]      = []
        self.last_scan_at:  datetime | None = None
        self.total_scans:   int             = 0
        self.scan_history:  list[dict]      = []   # آخر 10 عمليات مسح

    # ── Public API ────────────────────────

    def start(self) -> bool:
        """
        يبدأ المسح في الخلفية.
        Returns False إذا كان يعمل بالفعل.
        """
        with self._lock:
            if self._running:
                main_logger.warning("Scheduler already running")
                return False

            self._running = True
            self._thread  = threading.Thread(
                target   = self._loop,
                daemon   = True,       # يموت مع البرنامج الرئيسي
                name     = "ScannerScheduler",
            )
            self._thread.start()

        main_logger.info(
            f"✅ Scheduler started | "
            f"Interval: {self.interval_minutes} min | "
            f"Pairs: {len(self.pairs)} | "
            f"TFs: {self.timeframes}"
        )
        return True

    def stop(self) -> bool:
        """
        يوقف المسح.
        Returns False إذا لم يكن يعمل.
        """
        with self._lock:
            if not self._running:
                return False
            self._running = False

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        main_logger.info("🛑 Scheduler stopped")
        return True

    def run_now(self) -> list[dict]:
        """
        يُشغّل مسحاً فورياً (blocking) بدون انتظار الجدول.
        """
        main_logger.info("🔍 Manual scan triggered")
        return self._do_scan()

    def update_config(
        self,
        interval_minutes: int       | None = None,
        pairs:            list[str] | None = None,
        timeframes:       list[str] | None = None,
        use_ai:           bool      | None = None,
    ):
        """تحديث الإعدادات أثناء التشغيل."""
        with self._lock:
            if interval_minutes is not None:
                self.interval_minutes = interval_minutes
            if pairs is not None:
                self.pairs = pairs
            if timeframes is not None:
                self.timeframes = timeframes
            if use_ai is not None:
                self.use_ai = use_ai

        main_logger.info(
            f"⚙️ Scheduler config updated | "
            f"interval={self.interval_minutes}m | "
            f"pairs={len(self.pairs)}"
        )

    # ── Properties ────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def next_scan_in(self) -> int:
        """دقائق حتى المسح القادم."""
        if not self._running or not self.last_scan_at:
            return 0
        elapsed = (
            datetime.now(timezone.utc) - self.last_scan_at
        ).total_seconds() / 60
        remaining = self.interval_minutes - elapsed
        return max(0, int(remaining))

    def get_status(self) -> dict:
        """معلومات حالة الـ Scheduler."""
        return {
            "running":          self._running,
            "interval_minutes": self.interval_minutes,
            "pairs":            self.pairs,
            "timeframes":       self.timeframes,
            "use_ai":           self.use_ai,
            "total_scans":      self.total_scans,
            "last_scan_at":     (
                self.last_scan_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if self.last_scan_at else "Never"
            ),
            "next_scan_in_min": self.next_scan_in,
            "opportunities":    len(self.last_results),
        }

    # ── Internal Loop ─────────────────────

    def _loop(self):
        """
        الحلقة الرئيسية تعمل في thread منفصل.
        تُشغّل المسح ثم تنتظر interval_minutes.
        """
        main_logger.info("🔄 Scheduler loop started")

        # مسح فوري عند البدء
        self._do_scan()

        while self._running:
            # انتظر الفترة المحددة (تحقق كل ثانية للتوقف السريع)
            interval_secs = self.interval_minutes * 60
            waited        = 0

            while waited < interval_secs and self._running:
                time.sleep(1)
                waited += 1

            if self._running:
                self._do_scan()

        main_logger.info("🔄 Scheduler loop ended")

    def _do_scan(self) -> list[dict]:
        """
        ينفذ عملية المسح الفعلية وتحديث النتائج.
        """
        scan_start = datetime.now(timezone.utc)

        main_logger.info(
            f"🔍 Scan #{self.total_scans + 1} starting | "
            f"{len(self.pairs)} pairs × {len(self.timeframes)} TFs"
        )

        try:
            results = auto_scanner.scan_all(
                timeframes  = self.timeframes,
                pairs       = self.pairs,
                use_ai      = self.use_ai,
                max_workers = 4,
            )

            scan_end     = datetime.now(timezone.utc)
            elapsed_secs = (scan_end - scan_start).total_seconds()

            with self._lock:
                self.last_results  = results
                self.last_scan_at  = scan_end
                self.total_scans  += 1

                # احتفظ بآخر 10 عمليات مسح
                self.scan_history.append({
                    "scan_number":   self.total_scans,
                    "timestamp":     scan_end.strftime("%H:%M:%S UTC"),
                    "opportunities": len(results),
                    "elapsed_sec":   round(elapsed_secs, 1),
                    "pairs_scanned": len(self.pairs),
                    "top_signal":    results[0]["symbol"] if results else "—",
                    "top_score":     results[0]["final_score"] if results else 0,
                })
                if len(self.scan_history) > 10:
                    self.scan_history.pop(0)

            main_logger.info(
                f"✅ Scan #{self.total_scans} done | "
                f"Found: {len(results)} | "
                f"Time: {elapsed_secs:.1f}s"
            )

            # ── Callback ──────────────────
            if self.on_result and results:
                try:
                    self.on_result(results)
                except Exception as cb_err:
                    main_logger.error(f"Callback error: {cb_err}")

            return results

        except Exception as e:
            main_logger.error(f"Scan error: {e}")
            return []


# ══════════════════════════════════════════
# Alert System
# ══════════════════════════════════════════

class AlertSystem:
    """
    يراقب نتائج المسح ويُصدر تنبيهات عند:
    - وجود فرصة بنقطة عالية (≥ 8.0)
    - وجود إعداد Market Entry
    - R:R ≥ 2.5
    """

    def __init__(self, min_score: float = 8.0, min_rr: float = 2.0):
        self.min_score   = min_score
        self.min_rr      = min_rr
        self.alerts:     list[dict] = []
        self.seen_keys:  set[str]   = set()

    def check(self, results: list[dict]) -> list[dict]:
        """
        يفحص النتائج ويُعيد التنبيهات الجديدة فقط.
        يتجنب تكرار نفس التنبيه.
        """
        new_alerts: list[dict] = []

        for r in results:
            # مفتاح فريد للإشارة
            key = f"{r['symbol']}_{r['timeframe']}_{r['side']}"

            if key in self.seen_keys:
                continue

            is_high_score  = r.get("final_score", 0)  >= self.min_score
            is_good_rr     = r.get("rr_ratio",    0)  >= self.min_rr
            is_market      = r.get("entry_type")      == "MARKET"

            if is_high_score and is_good_rr:
                alert = {
                    "key":     key,
                    "symbol":  r["symbol"],
                    "side":    r["side"],
                    "tf":      r["timeframe"],
                    "score":   r["final_score"],
                    "grade":   r["grade"],
                    "rr":      r["rr_ratio"],
                    "entry":   r["entry_price"],
                    "sl":      r["stop_loss"],
                    "tp1":     r["take_profit_1"],
                    "type":    "MARKET 🚀" if is_market else "LIMIT 🔵",
                    "time":    datetime.now(timezone.utc).strftime("%H:%M UTC"),
                    "reason":  r.get("entry_reason", ""),
                }
                new_alerts.append(alert)
                self.alerts.append(alert)
                self.seen_keys.add(key)

                main_logger.info(
                    f"🚨 ALERT: {r['symbol']} {r['side']} "
                    f"Score:{r['final_score']} R:R:{r['rr_ratio']}"
                )

        # احتفظ بآخر 50 تنبيه فقط
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]

        return new_alerts

    def reset_seen(self):
        """إعادة تعيين التنبيهات المرئية (كل يوم)."""
        self.seen_keys.clear()
        main_logger.info("🔄 Alert seen-keys reset")

    def get_recent(self, n: int = 10) -> list[dict]:
        """آخر N تنبيهات."""
        return self.alerts[-n:]


# ══════════════════════════════════════════
# Singletons
# ══════════════════════════════════════════

scheduler     = ScannerScheduler()
alert_system  = AlertSystem()


# ── ربط التنبيهات بالـ Scheduler ──────────
def _on_scan_result(results: list[dict]):
    new_alerts = alert_system.check(results)
    if new_alerts:
        main_logger.info(
            f"🚨 {len(new_alerts)} new high-quality alerts!"
        )

scheduler.on_result = _on_scan_result
