"""Run the background jobs inside the web app: no separate cron services to deploy.

The pilot runs as one instance on one SQLite disk, so an in-process scheduler is the simplest reliable option. Each
job's last run is stored in the database, so a restart neither skips nor repeats a run. With more than one instance,
turn this on (FHG_SCHEDULER=on) for exactly one of them.

Times are India time (IST):

* ``care``         hourly            medicine reminders, missed doses, refill alerts
* ``reminders``    daily 10:00       tests still to book, labs that haven't confirmed, results not in
* ``backup``       daily 02:30       encrypted database backup
* ``housekeeping`` daily 03:15       delete expired codes, tokens, invites and links
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Job:
    name: str
    run: Callable[[], dict]
    hourly: bool = False
    at: tuple[int, int] = (0, 0)     # (hour, minute) IST, for daily jobs
    first_run_now: bool = False      # on a fresh install, run at once instead of waiting for the next slot


def due_since(job: Job, now: datetime) -> datetime:
    """The most recent moment this job should have started by ``now``."""
    local = now.astimezone(IST)
    if job.hourly:
        return local.replace(minute=0, second=0, microsecond=0)
    slot = local.replace(hour=job.at[0], minute=job.at[1], second=0, microsecond=0)
    return slot if local >= slot else slot - timedelta(days=1)


def is_due(job: Job, now: datetime, last_run: Optional[str]) -> bool:
    if last_run is None:
        return True
    return datetime.fromisoformat(last_run) < due_since(job, now)


class Scheduler:
    def __init__(self, store, jobs: list[Job], interval_seconds: int = 60,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.store, self.jobs, self.interval, self.clock = store, jobs, interval_seconds, clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self) -> list[str]:
        """Run every job that is due; returns the names run. Safe to call from tests."""
        ran = []
        now = self.clock()
        for job in self.jobs:
            last = self.store.job_run(job.name)
            if last is None and not (job.hourly or job.first_run_now):
                # Fresh install: start counting from now, so daily jobs don't all fire at whatever hour we boot.
                self.store.record_job_run(job.name, now.isoformat(), "scheduled", {})
                continue
            if not is_due(job, now, last["last_run_at"] if last else None):
                continue
            try:
                detail = job.run()
                self.store.record_job_run(job.name, now.isoformat(), "ok", detail)
            except Exception as exc:  # one failing job mustn't stop the others
                log.exception("scheduled job %s failed", job.name)
                self.store.record_job_run(job.name, now.isoformat(), "error", {"error": str(exc)[:500]})
            ran.append(job.name)
        return ran

    def start(self) -> None:
        if self._thread:
            return

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.tick()
        self._thread = threading.Thread(target=loop, name="fhg-scheduler", daemon=True)
        self._thread.start()
        log.info("scheduler started: %s", ", ".join(j.name for j in self.jobs))

    def stop(self) -> None:
        self._stop.set()
