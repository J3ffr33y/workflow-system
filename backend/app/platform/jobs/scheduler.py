"""Scheduled jobs declared in code, executed by the worker.

A job runs when ``every`` has elapsed since its last start. A PostgreSQL
advisory lock per job guarantees one execution at a time even with several
worker processes. Every run is recorded in ``job_runs``.
"""

import logging
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, text, update

from app.core.db import write_session
from app.core.time import utcnow
from app.platform.jobs.models import JobRun

log = logging.getLogger("flow.jobs")


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    every: timedelta
    run: Callable[[], str | None]  # returns a short summary


_jobs: dict[str, ScheduledJob] = {}


def scheduled(name: str, every: timedelta) -> Callable[[Callable[[], str | None]], Callable[[], str | None]]:
    def deco(fn: Callable[[], str | None]) -> Callable[[], str | None]:
        if name in _jobs:
            raise ValueError(f"duplicate job {name}")
        _jobs[name] = ScheduledJob(name, every, fn)
        return fn

    return deco


def jobs() -> list[ScheduledJob]:
    return list(_jobs.values())


def _lock_key(name: str) -> int:
    return zlib.crc32(f"flow-job:{name}".encode())


def run_job(job: ScheduledJob, *, force: bool = False) -> bool:
    """Run ``job`` if due (or ``force``). Returns True if it ran."""
    with write_session() as s, s.begin():
        if not s.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _lock_key(job.name)}):
            return False
        last = s.scalar(select(func.max(JobRun.started_at)).where(JobRun.job == job.name))
        if not force and last is not None and utcnow() - last < job.every:
            return False
        run_id = s.scalar(
            JobRun.__table__.insert().values(job=job.name, status="running").returning(JobRun.id)  # type: ignore[attr-defined]
        )
    started = time.monotonic()
    status, summary, error = "succeeded", None, None
    try:
        summary = job.run()
    except Exception as e:
        status, error = "failed", repr(e)[:4000]
        log.exception("job %s failed", job.name)
    with write_session() as s, s.begin():
        s.execute(
            update(JobRun)
            .where(JobRun.id == run_id)
            .values(
                status=status,
                summary=summary,
                error=error,
                finished_at=utcnow(),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
    return True


def run_due_jobs() -> int:
    return sum(1 for j in jobs() if run_job(j))
