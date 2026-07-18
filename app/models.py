import enum
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, Index, Integer, JSON, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vivacity.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_options: dict = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(
        pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "10"))),
        max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "20"))),
        pool_timeout=max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))),
        pool_recycle=max(60, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800"))),
    )
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    queued = "queued"
    generating_voiceover = "generating_voiceover"
    generating_code = "generating_code"
    rendering = "rendering"
    retrying = "retrying"
    muxing = "muxing"
    complete = "complete"
    failed = "failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_queue_order", "status", "priority", "created_at"),
        Index("ix_jobs_completed_at", "completed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), nullable=False, default=JobStatus.queued)
    progress_message: Mapped[str] = mapped_column(String(500), nullable=False, default="Queued.")
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    storyboard: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_storyboard: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    scene_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    orientation: Mapped[str] = mapped_column(String(20), nullable=False, default="portrait")
    parent_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    edited_beat_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_scores: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    practice_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    job_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="storyboard")
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    pipeline_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="legacy")
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy-v1")
    llm_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="anthropic")
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_fast_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_attempt_llm_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_attempt_llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tts_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="openai")
    tts_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cache_source_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    render_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_compute_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RecallResponse(Base):
    __tablename__ = "recall_responses"
    __table_args__ = (Index("ix_recall_responses_video_student", "video_id", "student_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(120), nullable=False)
    answer_given: Mapped[str] = mapped_column(Text, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        ensure_sqlite_columns()


def ensure_sqlite_columns() -> None:
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("jobs")}
    with engine.begin() as connection:
        if "cost_breakdown" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN cost_breakdown JSON NOT NULL DEFAULT '{}'"))
        if "quality_scores" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN quality_scores JSON NOT NULL DEFAULT '[]'"))
        if "practice_questions" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN practice_questions JSON"))
        if "estimated_cost_usd" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN estimated_cost_usd FLOAT NOT NULL DEFAULT 0.0"))
        if "storyboard" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN storyboard TEXT"))
        if "generated_storyboard" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN generated_storyboard TEXT"))
        if "generated_code" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN generated_code TEXT"))
        if "scene_name" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN scene_name VARCHAR(120)"))
        if "orientation" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN orientation VARCHAR(20) NOT NULL DEFAULT 'portrait'"))
        if "parent_job_id" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN parent_job_id VARCHAR(36)"))
        if "edited_beat_number" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN edited_beat_number INTEGER"))
        if "cost_budget_usd" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN cost_budget_usd FLOAT"))
        if "job_kind" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN job_kind VARCHAR(40) NOT NULL DEFAULT 'storyboard'"))
        if "request_payload" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN request_payload JSON NOT NULL DEFAULT '{}'"))
        if "request_fingerprint" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN request_fingerprint VARCHAR(64)"))
        if "idempotency_key" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN idempotency_key VARCHAR(255)"))
        if "pipeline_profile" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN pipeline_profile VARCHAR(20) NOT NULL DEFAULT 'legacy'"))
        if "pipeline_version" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN pipeline_version VARCHAR(80) NOT NULL DEFAULT 'legacy-v1'"))
        if "llm_provider" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN llm_provider VARCHAR(20) NOT NULL DEFAULT 'anthropic'"))
        if "llm_model" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN llm_model VARCHAR(120)"))
        if "llm_fast_model" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN llm_fast_model VARCHAR(120)"))
        if "first_attempt_llm_provider" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN first_attempt_llm_provider VARCHAR(20)"))
        if "first_attempt_llm_model" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN first_attempt_llm_model VARCHAR(120)"))
        if "tts_provider" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN tts_provider VARCHAR(20) NOT NULL DEFAULT 'openai'"))
        if "tts_model" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN tts_model VARCHAR(120)"))
        if "priority" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"))
        if "worker_id" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN worker_id VARCHAR(120)"))
        if "lease_expires_at" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN lease_expires_at DATETIME"))
        if "last_heartbeat_at" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN last_heartbeat_at DATETIME"))
        if "started_at" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN started_at DATETIME"))
        if "completed_at" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN completed_at DATETIME"))
        if "cache_hit" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN cache_hit BOOLEAN NOT NULL DEFAULT 0"))
        if "cache_source_job_id" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN cache_source_job_id VARCHAR(36)"))
        if "render_seconds" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN render_seconds FLOAT NOT NULL DEFAULT 0.0"))
        if "estimated_compute_cost_usd" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN estimated_compute_cost_usd FLOAT NOT NULL DEFAULT 0.0"))
        if "dead_lettered_at" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN dead_lettered_at DATETIME"))
        if "dead_letter_reason" not in columns:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN dead_letter_reason TEXT"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_request_fingerprint ON jobs (request_fingerprint)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_idempotency_key ON jobs (idempotency_key)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_worker_id ON jobs (worker_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_lease_expires_at ON jobs (lease_expires_at)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_jobs_queue_order ON jobs (status, priority, created_at)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_completed_at ON jobs (completed_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_dead_lettered_at ON jobs (dead_lettered_at)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
