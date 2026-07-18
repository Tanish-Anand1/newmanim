from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Job, JobStatus, utc_now
from app.operations import production_summary


def test_production_summary_reports_cost_and_capacity(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    now = utc_now()
    with session_local() as db:
        db.add_all(
            [
                Job(
                    status=JobStatus.complete,
                    attempt_number=1,
                    estimated_cost_usd=0.08,
                    started_at=now - timedelta(seconds=120),
                    completed_at=now,
                ),
                Job(
                    status=JobStatus.complete,
                    attempt_number=2,
                    estimated_cost_usd=0.12,
                    started_at=now - timedelta(seconds=180),
                    completed_at=now,
                ),
                Job(status=JobStatus.failed, completed_at=now),
                Job(status=JobStatus.queued, created_at=now - timedelta(seconds=30)),
            ]
        )
        db.commit()
        monkeypatch.setenv("TARGET_VIDEOS_PER_DAY", "10000")
        monkeypatch.setenv("MAX_ESTIMATED_COST_USD_PER_VIDEO", "0.15")
        summary = production_summary(db)

    assert summary["queue"]["queued"] == 1
    assert summary["last_24_hours"]["completed"] == 2
    assert summary["last_24_hours"]["failed"] == 1
    assert summary["sample"]["average_cost_usd"] == 0.1
    assert summary["sample"]["first_attempt_success_rate"] == 0.5
    assert summary["capacity"]["cost_target_met"] is True
    assert summary["capacity"]["required_concurrent_workers"] > 0

