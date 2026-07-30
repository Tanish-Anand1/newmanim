from __future__ import annotations

import os
import signal
import socket
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import func, or_, select, update, case

from app.models import Job, JobStatus, SessionLocal, engine, init_db, utc_now


TERMINAL_STATUSES = {JobStatus.complete, JobStatus.failed}
ACTIVE_STATUSES = {
    JobStatus.generating_voiceover,
    JobStatus.generating_code,
    JobStatus.rendering,
    JobStatus.retrying,
    JobStatus.muxing,
}


def execution_mode() -> str:
    mode = os.getenv("JOB_EXECUTION_MODE", "inline").strip().lower()
    if mode not in {"inline", "worker", "rq"}:
        raise RuntimeError("JOB_EXECUTION_MODE must be 'inline', 'worker', or 'rq'.")
    return mode


def make_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def claim_next_job(worker_id: str, lease_seconds: int) -> str | None:
    now = utc_now()
    lease_until = now + timedelta(seconds=lease_seconds)
    with SessionLocal() as db:
        if engine.dialect.name != "sqlite":
            with db.begin():
                job = db.scalar(
                    select(Job)
                    .where(
                        Job.status == JobStatus.queued,
                        or_(Job.worker_id.is_(None), Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
                    )
                    .order_by(Job.priority.desc(), Job.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is None:
                    return None
                job.worker_id = worker_id
                job.lease_expires_at = lease_until
                job.last_heartbeat_at = now
                if job.started_at is None:
                    job.started_at = now
                    job.attempt_number += 1
                job.progress_message = "Starting queued video job."
                return job.id

        candidate_ids = list(
            db.scalars(
                select(Job.id)
                .where(
                    Job.status == JobStatus.queued,
                    or_(Job.worker_id.is_(None), Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
                )
                .order_by(Job.priority.desc(), Job.created_at.asc())
                .limit(20)
            )
        )
        for job_id in candidate_ids:
            result = db.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.queued,
                    or_(Job.worker_id.is_(None), Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
                )
                .values(
                    worker_id=worker_id,
                    lease_expires_at=lease_until,
                    last_heartbeat_at=now,
                    started_at=case(
                        (Job.started_at.is_(None), now),
                        else_=Job.started_at
                    ),
                    attempt_number=case(
                        (Job.started_at.is_(None), Job.attempt_number + 1),
                        else_=Job.attempt_number
                    ),
                    progress_message="Starting queued video job.",
                )
            )
            if result.rowcount == 1:
                db.commit()
                return job_id
            db.rollback()
    return None


def heartbeat_job(job_id: str, worker_id: str, lease_seconds: int) -> bool:
    now = utc_now()
    with SessionLocal() as db:
        result = db.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.status.notin_(list(TERMINAL_STATUSES)),
            )
            .values(
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                last_heartbeat_at=now,
            )
        )
        db.commit()
        return result.rowcount == 1


def recover_expired_jobs() -> int:
    now = utc_now()
    with SessionLocal() as db:
        result = db.execute(
            update(Job)
            .where(
                Job.status.in_(ACTIVE_STATUSES),
                Job.worker_id.is_not(None),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < now,
            )
            .values(
                status=JobStatus.queued,
                progress_message="Recovered after a worker lease expired; queued for a fresh run.",
                worker_id=None,
                lease_expires_at=None,
                last_heartbeat_at=None,
                error=None,
                output_video_url=None,
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def finish_claim(job_id: str, worker_id: str) -> None:
    now = utc_now()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.worker_id != worker_id:
            return
        if job.status in TERMINAL_STATUSES:
            job.completed_at = job.completed_at or now
        job.worker_id = None
        job.lease_expires_at = None
        job.last_heartbeat_at = now
        db.commit()


def fail_unhandled_job(job_id: str, worker_id: str, exc: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.worker_id != worker_id:
            return
        if job.status not in TERMINAL_STATUSES:
            job.status = JobStatus.failed
            job.progress_message = "Video generation failed in the worker."
            job.error = f"{type(exc).__name__}: {exc}"
            job.completed_at = utc_now()
        db.commit()


def dispatch_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} was not found.")
        payload = dict(job.request_payload or {})
        job_kind = job.job_kind or "storyboard"
        profile = job.pipeline_profile or "legacy"

    from app.pipeline import (
        run_beat_param_render_for_job,
        run_beat_regeneration_for_job,
        run_pipeline_for_job,
        run_topic_pipeline_for_job,
    )

    if job_kind == "topic":
        run_topic_pipeline_for_job(
            job_id,
            payload["topic"],
            int(payload["duration_seconds"]),
            payload["audience"],
            payload["scene_name"],
            payload.get("orientation", "portrait"),
            pipeline_profile=profile,
        )
        return
    if job_kind == "beat_regeneration":
        run_beat_regeneration_for_job(
            job_id,
            payload["parent_job_id"],
            int(payload["beat_number"]),
            payload["on_screen"],
            payload["vo_text"],
        )
        return
    if job_kind == "beat_param_render":
        run_beat_param_render_for_job(
            job_id,
            payload["parent_job_id"],
            int(payload["beat_number"]),
            dict(payload["values"]),
        )
        return
    if job_kind != "storyboard":
        raise RuntimeError(f"Unsupported job kind: {job_kind}")

    storyboard = payload.get("storyboard")
    if not storyboard:
        raise RuntimeError("Storyboard job payload is missing storyboard text.")
    if profile == "craft":
        from app.craft_pipeline import run_craft_pipeline_for_job
        from app.pipeline import parse_storyboard, WORK_ROOT, provider_for_job

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            beats = parse_storyboard(storyboard)
            work_dir = WORK_ROOT / job_id
            debug_log_path = work_dir / "debug_timing.log"
            provider = provider_for_job(db, job_id)
            run_craft_pipeline_for_job(job_id, db, work_dir, provider, job, beats, debug_log_path)
        return
    if profile == "template":
        from app.template_pipeline import run_template_pipeline_for_job

        run_template_pipeline_for_job(
            job_id,
            storyboard,
            payload["scene_name"],
            payload.get("orientation", "portrait"),
        )
        return
    run_pipeline_for_job(
        job_id,
        storyboard,
        payload["scene_name"],
        payload.get("orientation", "portrait"),
    )


def _heartbeat_loop(job_id: str, worker_id: str, lease_seconds: int, stop_event: threading.Event) -> None:
    interval = max(5.0, lease_seconds / 3)
    while not stop_event.wait(interval):
        if not heartbeat_job(job_id, worker_id, lease_seconds):
            return


def run_worker(shutdown_event: threading.Event | None = None) -> None:
    init_db()
    shutdown_event = shutdown_event or threading.Event()
    worker_id = os.getenv("WORKER_ID") or make_worker_id()
    lease_seconds = max(60, int(os.getenv("WORKER_LEASE_SECONDS", "900")))
    poll_seconds = max(0.2, float(os.getenv("WORKER_POLL_SECONDS", "1")))
    recovery_interval = max(15.0, float(os.getenv("WORKER_RECOVERY_INTERVAL_SECONDS", "60")))
    # Zero means keep the worker alive. A finite recycle limit is useful for
    # supervised production deployments, but must be explicitly configured so
    # the local queue cannot silently stop accepting new jobs.
    max_jobs = max(0, int(os.getenv("WORKER_MAX_JOBS", "0")))
    completed_jobs = 0
    last_recovery = 0.0

    def request_shutdown(signum, _frame) -> None:
        print(f"Vivacity worker {worker_id} received signal {signum}; stopping after the current job.", flush=True)
        shutdown_event.set()

    if threading.current_thread() is threading.main_thread():
        for signal_name in ("SIGINT", "SIGTERM"):
            worker_signal = getattr(signal, signal_name, None)
            if worker_signal is not None:
                signal.signal(worker_signal, request_shutdown)

    print(f"Vivacity worker {worker_id} started.", flush=True)

    while not shutdown_event.is_set():
        now = time.monotonic()
        if now - last_recovery >= recovery_interval:
            recovered = recover_expired_jobs()
            if recovered:
                print(f"Recovered {recovered} expired job lease(s).", flush=True)
            last_recovery = now

        job_id = claim_next_job(worker_id, lease_seconds)
        if job_id is None:
            shutdown_event.wait(poll_seconds)
            continue

        print(f"Claimed job {job_id}.", flush=True)
        stop_event = threading.Event()
        heartbeat = threading.Thread(
            target=_heartbeat_loop,
            args=(job_id, worker_id, lease_seconds, stop_event),
            daemon=True,
        )
        heartbeat.start()
        try:
            dispatch_job(job_id)
        except Exception as exc:
            fail_unhandled_job(job_id, worker_id, exc)
            print(f"Job {job_id} failed in worker: {type(exc).__name__}: {exc}", flush=True)
        finally:
            stop_event.set()
            heartbeat.join(timeout=5)
            finish_claim(job_id, worker_id)
            completed_jobs += 1
            if max_jobs and completed_jobs >= max_jobs:
                print(f"Vivacity worker {worker_id} reached WORKER_MAX_JOBS={max_jobs}; exiting for recycle.", flush=True)
                shutdown_event.set()

    print(f"Vivacity worker {worker_id} stopped after {completed_jobs} job(s).", flush=True)
