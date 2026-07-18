from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job_queue, rq_queue
from app.models import Base, Job, JobStatus


def isolated_sessions(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rq.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(rq_queue, "SessionLocal", session_local)
    return session_local


def test_enqueue_job_uses_a_stable_rq_job_id(monkeypatch):
    captured = {}

    class FakeQueue:
        def enqueue(self, function, *args, **kwargs):
            captured["function"] = function
            captured["args"] = args
            captured["kwargs"] = kwargs
            return type("JobRef", (), {"id": kwargs["job_id"]})()

    monkeypatch.setattr(rq_queue, "generation_queue", lambda: FakeQueue())

    queued_id = rq_queue.enqueue_job("job-123")

    assert queued_id == "vivacity-job-123"
    assert captured["function"] is rq_queue.execute_queued_job
    assert captured["args"] == ("job-123",)


def test_failed_pipeline_job_is_recorded_in_dead_letter_registry(monkeypatch, tmp_path):
    session_local = isolated_sessions(monkeypatch, tmp_path)
    with session_local() as db:
        job = Job(status=JobStatus.queued, cost_breakdown={})
        db.add(job)
        db.commit()
        job_id = job.id

    def fail_pipeline(dispatched_job_id: str):
        with session_local() as db:
            job = db.get(Job, dispatched_job_id)
            job.status = JobStatus.failed
            job.error = "All render attempts failed."
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

    monkeypatch.setattr(job_queue, "dispatch_job", fail_pipeline)

    rq_queue.execute_queued_job(job_id)

    with session_local() as db:
        job = db.get(Job, job_id)
        assert job.dead_lettered_at is not None
        assert job.dead_letter_reason == "All render attempts failed."
