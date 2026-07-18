from __future__ import annotations

import os
import logging
import uuid
from datetime import datetime, timedelta, timezone

from redis import Redis
from rq import Queue

from app.models import Job, JobStatus, SessionLocal


QUEUE_NAME = os.getenv("RQ_QUEUE_NAME", "vivacity")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
RQ_JOB_TIMEOUT_SECONDS = max(60, int(os.getenv("RQ_JOB_TIMEOUT_SECONDS", "1800")))
RQ_RESULT_TTL_SECONDS = max(0, int(os.getenv("RQ_RESULT_TTL_SECONDS", "86400")))
RQ_FAILURE_TTL_SECONDS = max(0, int(os.getenv("RQ_FAILURE_TTL_SECONDS", "604800")))
logger = logging.getLogger(__name__)


def redis_connection() -> Redis:
    return Redis.from_url(
        REDIS_URL,
        decode_responses=False,
        socket_connect_timeout=3,
        socket_timeout=5,
        # Redis-py uses protocol 2 for RESP2. Older Redis services do not
        # implement the RESP3 HELLO handshake used by protocol 3.
        protocol=2,
    )


def generation_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis_connection(), default_timeout=RQ_JOB_TIMEOUT_SECONDS)


def enqueue_job(job_id: str) -> str:
    rq_job = generation_queue().enqueue(
        execute_queued_job,
        job_id,
        job_id=f"vivacity-{job_id}",
        job_timeout=RQ_JOB_TIMEOUT_SECONDS,
        result_ttl=RQ_RESULT_TTL_SECONDS,
        failure_ttl=RQ_FAILURE_TTL_SECONDS,
    )
    return rq_job.id


def recall_followup_task(video_id: str, student_id: str) -> None:
    """Placeholder body for the 24-hour recap job."""
    logger.info("Recall follow-up requested for video_id=%s student_id=%s", video_id, student_id)


def queue_recall_followup(video_id: str, student_id: str) -> str:
    """Schedule the recap stub with the existing RQ scheduler, 24 hours later."""
    run_at = datetime.now(timezone.utc) + timedelta(hours=24)
    rq_job = generation_queue().enqueue_at(
        run_at,
        recall_followup_task,
        video_id,
        student_id,
        job_id=f"vivacity-recall-{uuid.uuid4()}",
        result_ttl=RQ_RESULT_TTL_SECONDS,
        failure_ttl=RQ_FAILURE_TTL_SECONDS,
    )
    return rq_job.id


def mark_dead_letter(job_id: str, reason: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.dead_lettered_at = datetime.now(timezone.utc)
        job.dead_letter_reason = reason[:4000]
        db.commit()


def execute_queued_job(job_id: str) -> None:
    """RQ entrypoint. Pipeline failures are preserved in the database and dead-lettered."""
    try:
        from app.job_queue import dispatch_job

        dispatch_job(job_id)
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.failed
                job.progress_message = "Video generation failed in the queue worker."
                job.error = f"{type(exc).__name__}: {exc}"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        mark_dead_letter(job_id, f"Queue worker exception: {type(exc).__name__}: {exc}")
        return

    dead_letter_reason: str | None = None
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is not None and job.status == JobStatus.failed:
            dead_letter_reason = job.error or "Pipeline exhausted its retry budget."
    if dead_letter_reason:
        mark_dead_letter(job_id, dead_letter_reason)


def queue_depth() -> int | None:
    try:
        return int(generation_queue().count)
    except Exception:
        return None
