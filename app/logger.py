"""
Professional Logger
───────────────────
سجل موحد لكل أجزاء التطبيق.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# ── تأكد من وجود مجلد logs ──────────────
Path("logs").mkdir(exist_ok=True)

# ── Format ──────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)


def _build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    # تجنب إضافة handlers متعددة عند reload
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Console ─────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # ── File (كل شيء) ───────────────────
    log_file = f"logs/trading_{datetime.now().strftime('%Y%m%d')}.log"
    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(formatter)
    logger.addHandler(file_h)

    # ── File (أخطاء فقط) ────────────────
    err_h = logging.FileHandler("logs/errors.log", encoding="utf-8")
    err_h.setLevel(logging.ERROR)
    err_h.setFormatter(formatter)
    logger.addHandler(err_h)

    return logger


# ── Loggers المُصدَّرة ───────────────────
main_logger   = _build_logger("main")
signal_logger = _build_logger("signal")
ai_logger     = _build_logger("ai")
db_logger     = _build_logger("database")
filter_logger = _build_logger("filters")
