from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job_queue
from app.models import Base, Job, JobStatus, utc_now


def isolated_queue(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(job_queue, "engine", engine)
    monkeypatch.setattr(job_queue, "SessionLocal", session_local)
    return session_local


def test_claim_next_job_is_priority_ordered_and_exclusive(monkeypatch, tmp_path):
    session_local = isolated_queue(monkeypatch, tmp_path)
    with session_local() as db:
        low = Job(priority=1, status=JobStatus.queued)
        high = Job(priority=10, status=JobStatus.queued)
        db.add_all([low, high])
        db.commit()
        low_id = low.id
        high_id = high.id

    assert job_queue.claim_next_job("worker-a", 300) == high_id
    assert job_queue.claim_next_job("worker-b", 300) == low_id
    assert job_queue.claim_next_job("worker-c", 300) is None

    with session_local() as db:
        assert db.get(Job, high_id).worker_id == "worker-a"
        assert db.get(Job, low_id).worker_id == "worker-b"


def test_recover_expired_active_job_returns_it_to_queue(monkeypatch, tmp_path):
    session_local = isolated_queue(monkeypatch, tmp_path)
    with session_local() as db:
        job = Job(
            status=JobStatus.rendering,
            worker_id="dead-worker",
            lease_expires_at=utc_now() - timedelta(minutes=1),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    assert job_queue.recover_expired_jobs() == 1
    with session_local() as db:
        recovered = db.get(Job, job_id)
        assert recovered.status == JobStatus.queued
        assert recovered.worker_id is None
        assert recovered.lease_expires_at is None

