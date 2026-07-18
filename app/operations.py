from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, JobStatus


ACTIVE_STATUSES = {
    JobStatus.generating_voiceover,
    JobStatus.generating_code,
    JobStatus.rendering,
    JobStatus.retrying,
    JobStatus.muxing,
}


def _seconds_between(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if started_at is None or completed_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return max(0.0, (completed_at - started_at).total_seconds())


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def production_summary(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    target_videos_per_day = max(1, int(os.getenv("TARGET_VIDEOS_PER_DAY", "10000")))
    target_cost_usd = max(0.0, float(os.getenv("MAX_ESTIMATED_COST_USD_PER_VIDEO", "0.15")))
    target_utilization = min(0.95, max(0.1, float(os.getenv("CAPACITY_TARGET_UTILIZATION", "0.70"))))
    fallback_job_seconds = max(1.0, float(os.getenv("CAPACITY_PLANNING_JOB_SECONDS", "180")))
    sample_size = max(20, int(os.getenv("OPERATIONS_SAMPLE_SIZE", "1000")))
    rolling_cost_window = max(1, int(os.getenv("COST_ROLLING_WINDOW_JOBS", "100")))

    status_counts = {
        status.value: int(count)
        for status, count in db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)).all()
    }
    for status in JobStatus:
        status_counts.setdefault(status.value, 0)

    oldest_queued = db.scalar(select(func.min(Job.created_at)).where(Job.status == JobStatus.queued))
    if oldest_queued is not None and oldest_queued.tzinfo is None:
        oldest_queued = oldest_queued.replace(tzinfo=timezone.utc)
    oldest_queue_age_seconds = max(0.0, (now - oldest_queued).total_seconds()) if oldest_queued else 0.0

    active_workers = int(
        db.scalar(
            select(func.count(func.distinct(Job.worker_id))).where(
                Job.status.in_(list(ACTIVE_STATUSES)),
                Job.worker_id.is_not(None),
            )
        )
        or 0
    )

    recent_terminal = list(
        db.scalars(
            select(Job).where(
                Job.completed_at.is_not(None),
                Job.completed_at >= cutoff,
                Job.status.in_([JobStatus.complete, JobStatus.failed]),
            )
        )
    )
    recent_complete = [job for job in recent_terminal if job.status == JobStatus.complete]
    recent_failed = [job for job in recent_terminal if job.status == JobStatus.failed]
    recent_total = len(recent_terminal)

    sample = list(
        db.scalars(
            select(Job)
            .where(Job.status == JobStatus.complete, Job.completed_at.is_not(None))
            .order_by(Job.completed_at.desc())
            .limit(sample_size)
        )
    )
    wall_seconds = [
        duration
        for job in sample
        if (duration := _seconds_between(job.started_at, job.completed_at)) is not None and duration > 0
    ]
    costs = [float(job.estimated_cost_usd or 0.0) for job in sample]
    observed_average_seconds = sum(wall_seconds) / len(wall_seconds) if wall_seconds else None
    observed_p95_seconds = _percentile(wall_seconds, 0.95)
    planning_job_seconds = observed_p95_seconds or observed_average_seconds or fallback_job_seconds
    required_workers = math.ceil(
        target_videos_per_day * planning_job_seconds / (86_400.0 * target_utilization)
    )
    average_cost = sum(costs) / len(costs) if costs else None
    p95_cost = _percentile(costs, 0.95)
    projected_daily_cost = average_cost * target_videos_per_day if average_cost is not None else None
    first_attempt_successes = sum(1 for job in sample if int(job.attempt_number or 0) <= 1)
    rolling_jobs = sample[:rolling_cost_window]
    rolling_costs = [float(job.estimated_cost_usd or 0.0) for job in rolling_jobs]
    rolling_average_cost = sum(rolling_costs) / len(rolling_costs) if rolling_costs else None

    rq_queue_depth = None
    if os.getenv("JOB_EXECUTION_MODE", "inline").strip().lower() == "rq":
        from app.rq_queue import queue_depth

        rq_queue_depth = queue_depth()

    return {
        "generated_at": now.isoformat(),
        "targets": {
            "videos_per_day": target_videos_per_day,
            "max_cost_usd_per_video": target_cost_usd,
            "worker_utilization": target_utilization,
        },
        "queue": {
            "status_counts": status_counts,
            "queued": status_counts[JobStatus.queued.value],
            "active": sum(status_counts[status.value] for status in ACTIVE_STATUSES),
            "active_workers": active_workers,
            "oldest_queue_age_seconds": round(oldest_queue_age_seconds, 3),
            "rq_queue_depth": rq_queue_depth,
        },
        "last_24_hours": {
            "completed": len(recent_complete),
            "failed": len(recent_failed),
            "success_rate": round(len(recent_complete) / recent_total, 4) if recent_total else None,
        },
        "sample": {
            "completed_jobs": len(sample),
            "first_attempt_success_rate": round(first_attempt_successes / len(sample), 4) if sample else None,
            "average_cost_usd": round(average_cost, 6) if average_cost is not None else None,
            "p95_cost_usd": round(p95_cost, 6) if p95_cost is not None else None,
            "average_wall_seconds": round(observed_average_seconds, 3) if observed_average_seconds else None,
            "p95_wall_seconds": round(observed_p95_seconds, 3) if observed_p95_seconds else None,
        },
        "rolling_cost": {
            "window_completed_jobs": len(rolling_jobs),
            "average_cost_usd": round(rolling_average_cost, 6) if rolling_average_cost is not None else None,
            "target_cost_usd": target_cost_usd,
            "target_met": rolling_average_cost <= target_cost_usd if rolling_average_cost is not None else None,
        },
        "capacity": {
            "planning_job_seconds": round(planning_job_seconds, 3),
            "required_concurrent_workers": required_workers,
            "projected_daily_cost_usd": round(projected_daily_cost, 2) if projected_daily_cost is not None else None,
            "cost_target_met": average_cost <= target_cost_usd if average_cost is not None else None,
            "throughput_target_met_last_24h": len(recent_complete) >= target_videos_per_day,
        },
    }
