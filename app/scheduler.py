"""Monthly job — generate prior month's report on the 1st at 09:00."""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.excel_report import generate_report

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def _generate_prior_month() -> None:
    now = datetime.now()
    if now.month == 1:
        y, m = now.year - 1, 12
    else:
        y, m = now.year, now.month - 1
    try:
        out = generate_report(y, m)
        log.info("Generated monthly report: %s", out)
    except Exception as exc:
        log.exception("Monthly report generation failed: %s", exc)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler()
    # 1st of every month, 09:00 local time
    sched.add_job(_generate_prior_month, "cron", day=1, hour=9, minute=0, id="monthly_report")
    sched.start()
    _scheduler = sched
    log.info("Scheduler started: monthly report on day=1 hour=9")
    return sched
