import asyncio
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.learning import learning_summary
from app.job_queue import execution_mode
from app.llm_provider import get_llm_provider
from app.models import (
    Job,
    JobStatus,
    RecallResponse as RecallResponseRecord,
    VideoProblemReport,
    SessionLocal,
    get_db,
    init_db,
)
from app.operations import production_summary
from app.prerequisite_gate import StudentSignal
from app.pipeline import (
    JOB_COST_CEILING_USD,
    MAX_RETRIES,
    OPENAI_TTS_MODEL,
    TOPIC_MAX_TARGET_SECONDS,
    beat_thumbnail_url,
    empty_cost_breakdown,
    generate_storyboard_draft,
    output_video_path_for_job,
    patch_beat_params_in_code,
    parse_storyboard,
    replace_storyboard_beat,
    run_beat_param_render_for_job,
    run_beat_regeneration_for_job,
    run_pipeline_for_job,
    run_topic_pipeline_for_job,
    safe_scene_name,
    scene_file_for_job,
    storyboard_topic_hint,
    beat_params_from_code,
    validate_generated_storyboard_integrity,
    validate_storyboard_or_raise,
)
from app.storage import OUTPUT_DIR


DEFAULT_PIPELINE_PROFILE = os.getenv("DEFAULT_PIPELINE_PROFILE", "template").strip().lower()
if DEFAULT_PIPELINE_PROFILE not in {"template", "legacy"}:
    DEFAULT_PIPELINE_PROFILE = "template"
BATCH_MAX_ITEMS = max(1, int(os.getenv("BATCH_MAX_ITEMS", "1000")))
ENABLE_REQUEST_DEDUPLICATION = os.getenv("ENABLE_REQUEST_DEDUPLICATION", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "template-v1").strip() or "template-v1"
ACTIVE_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
CHEAP_LLM_PROVIDER = os.getenv("CHEAP_LLM_PROVIDER", "openai").strip().lower()
ACTIVE_TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai").strip().lower()
ALLOW_LEGACY_PIPELINE = os.getenv("ALLOW_LEGACY_PIPELINE", "1").strip().lower() not in {"0", "false", "no"}


def configured_llm_model(provider_name: str) -> str | None:
    if provider_name == "openai":
        return os.getenv("OPENAI_CODE_MODEL")
    if provider_name == "gemini":
        return os.getenv("GEMINI_MODEL")
    return os.getenv("ANTHROPIC_MODEL")


def configured_fast_llm_model(provider_name: str) -> str | None:
    if provider_name == "openai":
        return os.getenv("OPENAI_CODE_MODEL_FAST") or configured_llm_model(provider_name)
    if provider_name == "gemini":
        return os.getenv("GEMINI_MODEL_FAST") or configured_llm_model(provider_name)
    return os.getenv("ANTHROPIC_MODEL_FAST") or configured_llm_model(provider_name)


def configured_tts_model(provider_name: str) -> str | None:
    return OPENAI_TTS_MODEL if provider_name == "openai" else None


class GenerateRequest(BaseModel):
    storyboard: str | None = Field(None, min_length=1, max_length=50_000)
    topic: str | None = Field(None, min_length=1, max_length=2000)
    duration_seconds: int | None = Field(None, ge=10, le=TOPIC_MAX_TARGET_SECONDS)
    audience: str | None = Field(None, min_length=1, max_length=1000)
    scene_name: str = Field(..., min_length=1, max_length=120)
    orientation: Literal["portrait", "landscape"] = "portrait"
    pipeline_profile: Literal["craft", "template", "legacy"] = DEFAULT_PIPELINE_PROFILE
    reuse_existing: bool = True
    exam_context: Literal["JEE Main", "JEE Advanced", "NEET"] | None = None
    student_signal: StudentSignal | None = None
    assumed_prerequisites: list[str] | None = None

    @model_validator(mode="after")
    def require_storyboard_or_topic(self):
        has_storyboard = bool(self.storyboard and self.storyboard.strip())
        has_topic = bool(self.topic and self.topic.strip())
        if has_storyboard == has_topic:
            raise ValueError("Provide either storyboard or topic, but not both.")
        if has_topic and (self.duration_seconds is None or not self.audience or not self.audience.strip()):
            raise ValueError("Topic-based generation requires duration_seconds and audience.")
        return self


class StoryboardDraftRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    duration_seconds: int = Field(60, ge=10, le=TOPIC_MAX_TARGET_SECONDS)
    audience: str = Field(..., min_length=1, max_length=1000)
    exam_context: Literal["JEE Main", "JEE Advanced", "NEET"] | None = None
    student_signal: StudentSignal | None = None
    assumed_prerequisites: list[str] | None = None


class StoryboardDraftResponse(BaseModel):
    storyboard: str
    estimated_cost_usd: float
    cost_breakdown: dict[str, Any]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list, max_length=20)


class RecallResponse(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=120)
    question_id: str = Field(..., min_length=1, max_length=120)
    answer_given: str = Field(..., min_length=1, max_length=10_000)


class RecallResponseResult(BaseModel):
    correct: bool


class ProblemReportRequest(BaseModel):
    student_id: str | None = Field(None, max_length=120)
    category: str = Field("video_quality", min_length=1, max_length=80)
    details: str = Field(..., min_length=1, max_length=5000)


class ProblemReportResult(BaseModel):
    accepted: bool


class GenerateResponse(BaseModel):
    job_id: str
    cache_hit: bool = False


class BatchGenerateRequest(BaseModel):
    requests: list[GenerateRequest] = Field(..., min_length=1, max_length=BATCH_MAX_ITEMS)


class BatchGenerateResponse(BaseModel):
    jobs: list[GenerateResponse]


class PublicBeatSummary(BaseModel):
    beat_number: int
    start: float
    end: float
    on_screen: str
    vo_text: str | None


class BeatResponse(BaseModel):
    beat_number: int
    start: float
    end: float
    on_screen: str
    vo_text: str | None
    thumbnail_url: str


class BeatRegenerateRequest(BaseModel):
    on_screen: str = Field(..., min_length=1, max_length=5000)
    vo_text: str = Field(..., min_length=1, max_length=5000)


class BeatParamsResponse(BaseModel):
    scale: float | None = None
    gap: float | None = None
    speed: float | None = None


class BeatParamsPatchRequest(BaseModel):
    scale: float | None = Field(None, ge=0.5, le=2.0)
    gap: float | None = Field(None, ge=-6.0, le=6.0)
    speed: float | None = Field(None, ge=0.3, le=3.0)

    @model_validator(mode="after")
    def require_one_value(self):
        if self.scale is None and self.gap is None and self.speed is None:
            raise ValueError("Provide at least one parameter value.")
        return self


class PublicJobResponse(BaseModel):
    id: str
    status: JobStatus
    progress_message: str
    output_video_url: str | None
    orientation: str
    duration_seconds: float | None
    estimated_cost_usd: float
    cost_budget_usd: float | None
    cost_budget_remaining_usd: float | None
    pipeline_profile: str
    cache_hit: bool
    parent_job_id: str | None
    edited_beat_number: int | None
    failure_code: str | None
    error: str | None = None
    beats: list[PublicBeatSummary]
    practice_questions: list[dict[str, Any]] | None = None
    recall_question: dict[str, Any] | None = None


class InternalJobResponse(BaseModel):
    id: str
    status: JobStatus
    progress_message: str
    attempt_number: int
    max_attempts: int
    error: str | None
    output_video_url: str | None
    storyboard: str | None
    generated_storyboard: str | None
    raw_code: str | None
    orientation: str
    duration_seconds: float | None
    parent_job_id: str | None
    edited_beat_number: int | None
    cost_breakdown: dict[str, Any]
    quality_scores: list[dict[str, Any]]
    practice_questions: list[dict[str, Any]] | None
    estimated_cost_usd: float
    estimated_compute_cost_usd: float
    render_seconds: float
    cost_budget_usd: float | None
    job_kind: str
    request_payload: dict[str, Any]
    request_fingerprint: str | None
    idempotency_key: str | None
    pipeline_profile: str
    pipeline_version: str
    llm_provider: str
    llm_model: str | None
    llm_fast_model: str | None
    first_attempt_llm_provider: str | None
    first_attempt_llm_model: str | None
    tts_provider: str
    tts_model: str | None
    priority: int
    worker_id: str | None
    lease_expires_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cache_hit: bool
    cache_source_job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LearningSummaryResponse(BaseModel):
    learning_memory_dir: str
    staged_reference_examples: int
    approved_reference_examples: int
    staged_failure_patterns: int
    approved_failure_patterns: int
    categories: list[dict[str, Any]]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Vivacity API", lifespan=lifespan)

configured_origins = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
allowed_origins = list(
    dict.fromkeys(
        [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            *configured_origins,
        ]
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Serve frontend static files under /app/ path
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend_reference"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/workspace.html")


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    return {
        "status": "ready",
        "execution_mode": execution_mode(),
        "default_pipeline_profile": DEFAULT_PIPELINE_PROFILE,
        "pipeline_version": PIPELINE_VERSION,
    }


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Compatibility chat stream for the linked Vivacity workspace UI."""
    conversation = "\n".join(
        f"{message.role}: {message.content}" for message in request.messages[-20:]
    )
    provider = get_llm_provider(ACTIVE_LLM_PROVIDER)
    response = provider.generate(
        system=(
            "You are Viva, a concise educational assistant for Vivacity. "
            "Explain math and science clearly and recommend /video prompts when the user wants an animation."
        ),
        user_message=conversation or "Introduce yourself and ask what the student wants to learn.",
        max_tokens=900,
        model=configured_llm_model(ACTIVE_LLM_PROVIDER),
    )

    def chunks():
        words = response.text.split(" ")
        for index in range(0, len(words), 8):
            token = " ".join(words[index:index + 8])
            if index + 8 < len(words):
                token += " "
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(chunks(), media_type="text/event-stream")


def duration_seconds_for_job(job: Job) -> float | None:
    rendered_duration = (job.request_payload or {}).get("rendered_duration_seconds")
    if job.status == JobStatus.complete and rendered_duration is not None:
        try:
            return float(rendered_duration)
        except (TypeError, ValueError):
            pass
    if not job.storyboard:
        requested = (job.request_payload or {}).get("duration_seconds")
        return float(requested) if requested is not None else None
    beats = parse_storyboard(job.storyboard)
    if not beats:
        return None
    return max(beat.end_sec for beat in beats)


def rendered_beat_windows_for_job(job: Job, beats: list[Any]) -> list[tuple[float, float]]:
    stored_windows = (job.request_payload or {}).get("rendered_beat_windows")
    if isinstance(stored_windows, list) and len(stored_windows) == len(beats):
        windows: list[tuple[float, float]] = []
        try:
            for beat, window in zip(beats, stored_windows):
                if not isinstance(window, dict) or int(window.get("beat_number")) != beat.index:
                    raise ValueError("beat mismatch")
                start = float(window["start"])
                end = float(window["end"])
                if start < 0 or end <= start:
                    raise ValueError("invalid beat window")
                windows.append((start, end))
        except (KeyError, TypeError, ValueError):
            windows = []
        if windows:
            return windows
    return [(beat.start_sec, beat.end_sec) for beat in beats]


def public_beats_for_job(job: Job) -> list[dict[str, Any]]:
    if not job.storyboard:
        return []
    beats = parse_storyboard(job.storyboard)
    return [
        {
            "beat_number": beat.index,
            "start": start,
            "end": end,
            "on_screen": beat.on_screen_text,
            "vo_text": beat.vo_text,
        }
        for beat, (start, end) in zip(beats, rendered_beat_windows_for_job(job, beats))
    ]


def public_progress_message(job: Job) -> str:
    attempt = job.attempt_number or 0
    max_attempts = job.max_attempts or MAX_RETRIES
    if job.status == JobStatus.queued:
        return "Queued."
    if job.status == JobStatus.generating_voiceover:
        return "Preparing voiceover audio."
    if job.status == JobStatus.generating_code:
        return f"Building animation plan (attempt {max(1, attempt)} of {max_attempts})."
    if job.status == JobStatus.rendering:
        return f"Rendering video (attempt {max(1, attempt)} of {max_attempts})."
    if job.status == JobStatus.retrying:
        return f"Refining animation timing (attempt {max(1, attempt)} of {max_attempts})."
    if job.status == JobStatus.muxing:
        return "Combining audio and video."
    if job.status == JobStatus.complete:
        return "Video generation complete."
    if job.status == JobStatus.failed:
        if public_failure_code(job) == "provider_capacity":
            return "Generation capacity is temporarily unavailable. Retry this request."
        return "Video generation failed."
    return "Processing."


def public_failure_code(job: Job) -> str | None:
    if job.status != JobStatus.failed:
        return None
    error = (job.error or "").lower()
    if any(
        marker in error
        for marker in ("429", "rate limit", "quota", "resource_exhausted", "resource exhausted")
    ):
        return "provider_capacity"
    if "cost budget" in error:
        return "cost_budget"
    if "render" in error or "manim" in error:
        return "render_failure"
    return "generation_failure"


def public_job_to_dict(job: Job) -> dict[str, Any]:
    budget_remaining = None
    if job.cost_budget_usd is not None:
        budget_remaining = max(0.0, float(job.cost_budget_usd) - float(job.estimated_cost_usd or 0.0))
    return {
        "id": job.id,
        "status": job.status.value,
        "progress_message": public_progress_message(job),
        "output_video_url": job.output_video_url,
        "orientation": job.orientation,
        "duration_seconds": duration_seconds_for_job(job),
        "estimated_cost_usd": job.estimated_cost_usd or 0.0,
        "cost_budget_usd": job.cost_budget_usd,
        "cost_budget_remaining_usd": budget_remaining,
        "pipeline_profile": job.pipeline_profile,
        "cache_hit": bool(job.cache_hit),
        "parent_job_id": job.parent_job_id,
        "edited_beat_number": job.edited_beat_number,
        "failure_code": public_failure_code(job),
        "error": job.error,
        "beats": public_beats_for_job(job),
        "practice_questions": job.practice_questions,
        "recall_question": (job.request_payload or {}).get("recall_question"),
    }


def internal_job_to_dict(job: Job) -> dict[str, Any]:
    scene_file = scene_file_for_job(job)
    raw_code = job.generated_code or (scene_file.read_text(encoding="utf-8") if scene_file is not None else None)
    return {
        "id": job.id,
        "status": job.status.value,
        "progress_message": job.progress_message,
        "attempt_number": job.attempt_number,
        "max_attempts": job.max_attempts,
        "error": job.error,
        "output_video_url": job.output_video_url,
        "storyboard": job.storyboard,
        "generated_storyboard": job.generated_storyboard,
        "raw_code": raw_code,
        "orientation": job.orientation,
        "duration_seconds": duration_seconds_for_job(job),
        "parent_job_id": job.parent_job_id,
        "edited_beat_number": job.edited_beat_number,
        "cost_breakdown": job.cost_breakdown or {},
        "quality_scores": job.quality_scores or [],
        "practice_questions": job.practice_questions,
        "estimated_cost_usd": job.estimated_cost_usd or 0.0,
        "estimated_compute_cost_usd": job.estimated_compute_cost_usd or 0.0,
        "render_seconds": job.render_seconds or 0.0,
        "cost_budget_usd": job.cost_budget_usd,
        "job_kind": job.job_kind,
        "request_payload": job.request_payload or {},
        "request_fingerprint": job.request_fingerprint,
        "idempotency_key": job.idempotency_key,
        "pipeline_profile": job.pipeline_profile,
        "pipeline_version": job.pipeline_version,
        "llm_provider": job.llm_provider,
        "llm_model": job.llm_model,
        "llm_fast_model": job.llm_fast_model,
        "first_attempt_llm_provider": job.first_attempt_llm_provider,
        "first_attempt_llm_model": job.first_attempt_llm_model,
        "tts_provider": job.tts_provider,
        "tts_model": job.tts_model,
        "priority": job.priority,
        "worker_id": job.worker_id,
        "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "cache_hit": bool(job.cache_hit),
        "cache_source_job_id": job.cache_source_job_id,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal API is not configured.")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


def generation_payload(request: GenerateRequest) -> tuple[str, dict[str, Any]]:
    common = {
        "scene_name": request.scene_name,
        "orientation": request.orientation,
    }
    if request.storyboard is not None:
        return "storyboard", {**common, "storyboard": request.storyboard}
    payload = {
        **common,
        "topic": request.topic or "",
        "duration_seconds": request.duration_seconds or 60,
        "audience": request.audience or "",
    }
    if request.exam_context:
        payload["exam_context"] = request.exam_context
    if request.student_signal:
        payload["student_signal"] = request.student_signal.model_dump()
    if request.assumed_prerequisites:
        payload["assumed_prerequisites"] = request.assumed_prerequisites
    return "topic", payload


def generation_fingerprint(request: GenerateRequest) -> str:
    job_kind, payload = generation_payload(request)
    fingerprint_payload = dict(payload)
    fingerprint_payload.pop("scene_name", None)
    canonical = {
        "job_kind": job_kind,
        "payload": fingerprint_payload,
        "pipeline_profile": request.pipeline_profile,
        "schema_version": 2,
        "pipeline_version": PIPELINE_VERSION,
        "llm_provider": ACTIVE_LLM_PROVIDER,
        "llm_model": configured_llm_model(ACTIVE_LLM_PROVIDER),
        "llm_fast_model": configured_fast_llm_model(ACTIVE_LLM_PROVIDER),
        "first_attempt_llm_provider": CHEAP_LLM_PROVIDER,
        "first_attempt_llm_model": configured_fast_llm_model(CHEAP_LLM_PROVIDER),
        "tts_provider": ACTIVE_TTS_PROVIDER,
        "tts_model": configured_tts_model(ACTIVE_TTS_PROVIDER),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_generate_request(request: GenerateRequest) -> None:
    safe_scene_name(request.scene_name)
    if request.pipeline_profile == "legacy" and not ALLOW_LEGACY_PIPELINE:
        raise ValueError("The legacy pipeline is disabled for this deployment.")
    if request.storyboard is not None:
        validate_storyboard_or_raise(request.storyboard)
        # A scene class is an implementation detail, not a lesson topic. Only
        # apply entity-coverage checks when a direct storyboard explicitly
        # supplies a topic/title header; generic integrity checks still run.
        topic_hint = storyboard_topic_hint(request.storyboard, "")
        validate_generated_storyboard_integrity(topic_hint, request.storyboard)


def reusable_job_for_request(
    db: Session,
    request: GenerateRequest,
    fingerprint: str,
    idempotency_key: str | None,
) -> Job | None:
    if idempotency_key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    if not (ENABLE_REQUEST_DEDUPLICATION and request.reuse_existing):
        return None
    candidates = list(
        db.scalars(
            select(Job)
            .where(Job.request_fingerprint == fingerprint, Job.status != JobStatus.failed)
            .order_by(Job.created_at.desc())
            .limit(10)
        )
    )
    for candidate in candidates:
        if candidate.status != JobStatus.complete:
            return candidate
        if not candidate.output_video_url:
            continue
        if not candidate.output_video_url.startswith("/outputs/") or output_video_path_for_job(candidate) is not None:
            return candidate
    return None


def new_generation_job(request: GenerateRequest, fingerprint: str, idempotency_key: str | None = None) -> Job:
    job_kind, payload = generation_payload(request)
    return Job(
        status=JobStatus.queued,
        progress_message="Queued.",
        # New requests should not wait behind legacy records left by an
        # earlier interrupted batch. Older jobs remain available for review.
        priority=10,
        attempt_number=0,
        max_attempts=2 if request.pipeline_profile == "template" else MAX_RETRIES,
        storyboard=request.storyboard,
        generated_storyboard=None,
        scene_name=request.scene_name,
        orientation=request.orientation,
        cost_breakdown=empty_cost_breakdown(),
        estimated_cost_usd=0.0,
        cost_budget_usd=JOB_COST_CEILING_USD if JOB_COST_CEILING_USD > 0 else None,
        job_kind=job_kind,
        request_payload=payload,
        request_fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        pipeline_profile=request.pipeline_profile,
        pipeline_version=PIPELINE_VERSION,
        llm_provider=ACTIVE_LLM_PROVIDER,
        llm_model=configured_llm_model(ACTIVE_LLM_PROVIDER),
        llm_fast_model=configured_fast_llm_model(ACTIVE_LLM_PROVIDER),
        first_attempt_llm_provider=CHEAP_LLM_PROVIDER,
        first_attempt_llm_model=configured_fast_llm_model(CHEAP_LLM_PROVIDER),
        tts_provider=ACTIVE_TTS_PROVIDER,
        tts_model=configured_tts_model(ACTIVE_TTS_PROVIDER),
    )


def create_generation_job(
    request: GenerateRequest,
    db: Session,
    idempotency_key: str | None = None,
    user_id: str = "local-student",
) -> tuple[Job, bool, bool]:
    validate_generate_request(request)
    # Check subscription quota before creating a job
    from app.subscription import check_and_increment_quota, clamp_request_to_plan
    quota = check_and_increment_quota(user_id, dry_run=True)
    if not quota.allowed:
        raise HTTPException(status_code=429, detail=quota.reason)
    # Clamp request params to plan limits (silently downgrade, don't error)
    clamped = clamp_request_to_plan(
        user_id,
        requested_duration=request.duration_seconds or 30,
    )
    if clamped.duration_seconds != (request.duration_seconds or 30):
        request.duration_seconds = clamped.duration_seconds
    check_and_increment_quota(user_id)  # actually increment after clamping
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 255:
            raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1-255 characters.")

    fingerprint = generation_fingerprint(request)
    reusable = reusable_job_for_request(db, request, fingerprint, idempotency_key)
    if reusable is not None:
        return reusable, True, False

    job = new_generation_job(request, fingerprint, idempotency_key)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if existing is not None:
                return existing, True, False
        raise
    db.refresh(job)
    return job, False, True


def create_generation_jobs_batch(
    requests: list[GenerateRequest],
    db: Session,
) -> list[tuple[Job, bool, bool]]:
    for request in requests:
        validate_generate_request(request)

    fingerprints = [generation_fingerprint(request) for request in requests]
    reusable_by_fingerprint: dict[str, Job] = {}
    if ENABLE_REQUEST_DEDUPLICATION:
        unique_fingerprints = list(dict.fromkeys(fingerprints))
        for offset in range(0, len(unique_fingerprints), 500):
            chunk = unique_fingerprints[offset : offset + 500]
            candidates = list(
                db.scalars(
                    select(Job)
                    .where(Job.request_fingerprint.in_(chunk), Job.status != JobStatus.failed)
                    .order_by(Job.created_at.desc())
                )
            )
            for candidate in candidates:
                fingerprint = candidate.request_fingerprint
                if not fingerprint or fingerprint in reusable_by_fingerprint:
                    continue
                if candidate.status != JobStatus.complete:
                    reusable_by_fingerprint[fingerprint] = candidate
                elif candidate.output_video_url and (
                    not candidate.output_video_url.startswith("/outputs/")
                    or output_video_path_for_job(candidate) is not None
                ):
                    reusable_by_fingerprint[fingerprint] = candidate

    results: list[tuple[Job, bool, bool]] = []
    new_jobs: list[Job] = []
    created_by_fingerprint: dict[str, Job] = {}
    for request, fingerprint in zip(requests, fingerprints, strict=True):
        reusable = reusable_by_fingerprint.get(fingerprint) if request.reuse_existing else None
        if reusable is None and request.reuse_existing:
            reusable = created_by_fingerprint.get(fingerprint)
        if reusable is not None:
            results.append((reusable, True, False))
            continue
        job = new_generation_job(request, fingerprint)
        new_jobs.append(job)
        if request.reuse_existing:
            created_by_fingerprint[fingerprint] = job
        results.append((job, False, True))

    if new_jobs:
        db.add_all(new_jobs)
        db.commit()
    return results


def schedule_generation_job(background_tasks: BackgroundTasks, job: Job) -> None:
    mode = execution_mode()
    if mode == "rq":
        from app.rq_queue import enqueue_job

        enqueue_job(job.id)
        return
    if mode == "worker":
        return
    payload = dict(job.request_payload or {})
    if job.job_kind == "beat_regeneration":
        background_tasks.add_task(
            run_beat_regeneration_for_job,
            job.id,
            payload["parent_job_id"],
            int(payload["beat_number"]),
            payload["on_screen"],
            payload["vo_text"],
        )
        return
    if job.job_kind == "beat_param_render":
        background_tasks.add_task(
            run_beat_param_render_for_job,
            job.id,
            payload["parent_job_id"],
            int(payload["beat_number"]),
            dict(payload["values"]),
        )
        return
    if job.job_kind == "topic":
        background_tasks.add_task(
            run_topic_pipeline_for_job,
            job.id,
            payload["topic"],
            int(payload["duration_seconds"]),
            payload["audience"],
            payload["scene_name"],
            payload.get("orientation", "portrait"),
            job.pipeline_profile,
        )
        return
    if job.pipeline_profile == "template":
        from app.template_pipeline import run_template_pipeline_for_job

        background_tasks.add_task(
            run_template_pipeline_for_job,
            job.id,
            payload["storyboard"],
            payload["scene_name"],
            payload.get("orientation", "portrait"),
        )
        return
    background_tasks.add_task(
        run_pipeline_for_job,
        job.id,
        payload["storyboard"],
        payload["scene_name"],
        payload.get("orientation", "portrait"),
    )


@app.post("/api/storyboard/draft", response_model=StoryboardDraftResponse)
def draft_storyboard(request: StoryboardDraftRequest):
    try:
        return generate_storyboard_draft(
            request.topic,
            request.duration_seconds,
            request.audience,
            exam_context=request.exam_context,
            student_signal=request.student_signal.model_dump() if request.student_signal else None,
            assumed_prerequisites=request.assumed_prerequisites,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/generate", response_model=GenerateResponse)
def generate_video(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    try:
        job, cache_hit, created = create_generation_job(request, db, idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        schedule_generation_job(background_tasks, job)
    return GenerateResponse(job_id=job.id, cache_hit=cache_hit)


def normalize_recall_answer(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def queue_recall_followup(video_id: str, student_id: str) -> str:
    """Load the optional queue integration only when an incorrect answer needs it."""
    from app.rq_queue import queue_recall_followup as schedule_recall_followup

    return schedule_recall_followup(video_id, student_id)


@app.post("/videos/{video_id}/recall-response", response_model=RecallResponseResult)
def record_recall_response(
    video_id: str,
    request: RecallResponse,
    db: Session = Depends(get_db),
):
    job = db.get(Job, video_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    if job.status != JobStatus.complete:
        raise HTTPException(status_code=422, detail="Video is not complete.")

    question = (job.request_payload or {}).get("recall_question") or {}
    if question.get("question_id") != request.question_id:
        raise HTTPException(status_code=404, detail="Recall question not found.")

    expected = normalize_recall_answer(str(question.get("answer", "")))
    given = normalize_recall_answer(request.answer_given)
    correct = bool(expected and given and (given == expected or given in expected or expected in given))
    db.add(
        RecallResponseRecord(
            video_id=video_id,
            student_id=request.student_id,
            question_id=request.question_id,
            answer_given=request.answer_given,
            correct=correct,
        )
    )
    db.commit()

    if not correct:
        try:
            queue_recall_followup(video_id, request.student_id)
        except Exception as exc:
            # The answer is already persisted and immediate feedback must not
            # become a 500 merely because the optional scheduler is offline.
            import logging

            logging.getLogger(__name__).warning(
                "Recall follow-up could not be queued for video_id=%s student_id=%s: %s",
                video_id,
                request.student_id,
                exc,
            )
    return RecallResponseResult(correct=correct)


@app.post("/videos/{video_id}/problem-report", response_model=ProblemReportResult)
def record_video_problem_report(
    video_id: str,
    request: ProblemReportRequest,
    db: Session = Depends(get_db),
):
    if db.get(Job, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found.")
    db.add(
        VideoProblemReport(
            video_id=video_id,
            student_id=request.student_id,
            category=request.category,
            details=request.details,
        )
    )
    db.commit()
    import logging

    logging.getLogger(__name__).warning(
        "VIDEO_PROBLEM_REPORT video_id=%s student_id=%s category=%s details=%s",
        video_id,
        request.student_id or "anonymous",
        request.category,
        request.details,
    )
    return ProblemReportResult(accepted=True)


@app.post("/api/generate/batch", response_model=BatchGenerateResponse)
def generate_video_batch(
    request: BatchGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    inline_limit = max(1, int(os.getenv("INLINE_BATCH_MAX_ITEMS", "10")))
    if execution_mode() == "inline" and len(request.requests) > inline_limit:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Inline execution accepts at most {inline_limit} batch items. "
                "Set JOB_EXECUTION_MODE=worker and start worker processes for larger batches."
            ),
        )

    try:
        jobs = create_generation_jobs_batch(request.requests, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    responses: list[GenerateResponse] = []
    scheduled_ids: set[str] = set()
    for job, cache_hit, created in jobs:
        if created and job.id not in scheduled_ids:
            schedule_generation_job(background_tasks, job)
            scheduled_ids.add(job.id)
        responses.append(GenerateResponse(job_id=job.id, cache_hit=cache_hit))
    return BatchGenerateResponse(jobs=responses)


@app.get("/api/jobs/{job_id}", response_model=PublicJobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return public_job_to_dict(job)


@app.get("/api/internal/jobs/{job_id}", response_model=InternalJobResponse)
def get_internal_job(job_id: str, _: None = Depends(require_admin_token), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return internal_job_to_dict(job)


ACTIVE_RECALL_PROMPT_TEMPLATE = """You are an educational assistant creating active recall questions based on a video explanation.
Your goal is to test the viewer's understanding of the specific concepts covered in the video, not just generic trivia.

Video Topic: {topic}
Video Storyboard (Explanation Content):
{storyboard}

Generate 2-3 short practice questions (can be short-answer or multiple-choice) testing recall of the core concepts explained in the storyboard.
Output your response as a JSON array of objects, where each object has the following keys:
- "question": The question text.
- "options": An optional array of strings for multiple choice options. Omit if it's a short-answer question.
- "correct_answer": The correct answer.
- "explanation": A brief explanation of why the answer is correct, so a wrong answer teaches something.

Return ONLY the raw JSON array, without markdown formatting or code blocks.
"""

class PracticeQuestionItem(BaseModel):
    question: str
    answer: str
    explanation: str

class PracticeQuestionsEndpointResponse(BaseModel):
    job_id: str
    questions: list[PracticeQuestionItem]
    cost_usd: float

@app.post("/api/jobs/{job_id}/practice-questions", response_model=PracticeQuestionsEndpointResponse)
def generate_practice_questions(job_id: str, regenerate: bool = False, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    storyboard_content = job.generated_storyboard or job.storyboard
    if job.status != JobStatus.complete or not storyboard_content:
        raise HTTPException(status_code=422, detail="Job is not complete or has no storyboard.")
        
    if job.practice_questions and not regenerate:
        pq_cost = (job.cost_breakdown or {}).get("practice_questions", {}).get("cost_usd", 0.0)
        return {
            "job_id": job.id,
            "questions": job.practice_questions,
            "cost_usd": pq_cost
        }

    from app.llm_provider import get_llm_provider
    from app.pipeline import storyboard_topic_hint, llm_cost_event, normalized_cost_breakdown
    import json
    import re
    import logging
    
    llm = get_llm_provider(job.llm_provider)
    payload = job.request_payload or {}
    topic = payload.get("topic")
    
    if not topic and storyboard_content:
        topic = storyboard_topic_hint(storyboard_content, job.scene_name or "")
        
    if not topic or not topic.strip():
        logging.getLogger(__name__).warning(f"Could not determine topic for job {job.id}")
        topic = "Unknown Topic"
        
    system_prompt = (
        "Based on this educational video's topic and content, generate exactly 3 active-recall "
        "practice questions that test genuine understanding of the core concept (not just fact recall). "
        "Include the correct answer and a brief explanation for each. Format as JSON: "
        '[{"question": "...", "answer": "...", "explanation": "..."}]'
    )
    user_prompt = f"Topic: {topic}\n\nStoryboard Content:\n{storyboard_content}"
    current_user_message = user_prompt
    
    questions = None
    parse_errors = []
    
    for attempt in range(1, 3):
        try:
            response = llm.generate(
                system=system_prompt,
                user_message=current_user_message,
                max_tokens=1500
            )
            
            # Resolve the model name
            model_name = response.model or job.llm_model
            if not model_name:
                model_name = configured_llm_model(job.llm_provider) or "unknown"
                
            event_cost = llm_cost_event(job.llm_provider, response.input_tokens, response.output_tokens, model_name)
            
            breakdown = normalized_cost_breakdown(job.cost_breakdown)
            pq_stats = breakdown.setdefault("practice_questions", {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "provider": job.llm_provider,
                "model": model_name,
            })
            pq_stats["calls"] = int(pq_stats.get("calls", 0)) + 1
            pq_stats["input_tokens"] = int(pq_stats.get("input_tokens", 0)) + response.input_tokens
            pq_stats["output_tokens"] = int(pq_stats.get("output_tokens", 0)) + response.output_tokens
            pq_stats["cost_usd"] = float(pq_stats.get("cost_usd", 0.0)) + event_cost
            pq_stats["model"] = model_name
            
            job.cost_breakdown = breakdown
            job.estimated_cost_usd = float(job.estimated_cost_usd or 0.0) + event_cost
            db.commit()
            
            text = response.text.strip()
            # Basic json block cleanup
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'\[.*\]', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError("Failed to locate a JSON array bracket block in response.")
                    
            if not isinstance(data, list):
                raise ValueError("Response structure is not a JSON list array.")
                
            validated = []
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    raise ValueError(f"Item at index {idx} is not a JSON object.")
                q = item.get("question")
                ans = item.get("answer") or item.get("correct_answer")
                exp = item.get("explanation")
                if not q or not ans or not exp:
                    raise ValueError(f"Item at index {idx} is missing one or more required keys ('question', 'answer', 'explanation').")
                validated.append({
                    "question": str(q).strip(),
                    "answer": str(ans).strip(),
                    "explanation": str(exp).strip()
                })
                
            if len(validated) != 3:
                raise ValueError(f"Expected exactly 3 practice questions, but got {len(validated)}.")
                
            questions = validated
            break
            
        except Exception as exc:
            parse_errors.append(str(exc))
            if attempt == 1:
                current_user_message = (
                    f"Topic: {topic}\n\n"
                    f"Storyboard Content:\n{storyboard_content}\n\n"
                    f"Your previous response failed validation with error:\n{exc}\n\n"
                    "Please respond with valid JSON only, no markdown fencing, and ensure it is a list of exactly 3 objects with "
                    '"question", "answer", and "explanation" keys.'
                )
            else:
                errors_str = " | ".join(parse_errors)
                raise HTTPException(status_code=500, detail=f"Failed to generate valid practice questions: {errors_str}")

    job.practice_questions = questions
    db.commit()
    
    pq_cost = job.cost_breakdown.get("practice_questions", {}).get("cost_usd", 0.0)
    return {
        "job_id": job.id,
        "questions": questions,
        "cost_usd": pq_cost
    }



@app.get("/api/internal/learning/summary", response_model=LearningSummaryResponse)
def get_learning_summary(_: None = Depends(require_admin_token)):
    return learning_summary()


@app.get("/api/internal/operations/summary")
def get_operations_summary(
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
):
    return production_summary(db)


@app.get("/api/internal/dead-letter")
def get_dead_letter_jobs(
    limit: int = 100,
    _: None = Depends(require_admin_token),
    db: Session = Depends(get_db),
):
    safe_limit = min(500, max(1, limit))
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.dead_lettered_at.is_not(None))
            .order_by(Job.dead_lettered_at.desc())
            .limit(safe_limit)
        )
    )
    return [
        {
            "id": job.id,
            "status": job.status.value,
            "scene_name": job.scene_name,
            "attempt_number": job.attempt_number,
            "estimated_cost_usd": job.estimated_cost_usd or 0.0,
            "dead_lettered_at": job.dead_lettered_at.isoformat() if job.dead_lettered_at else None,
            "reason": job.dead_letter_reason,
        }
        for job in jobs
    ]


@app.get("/api/jobs/{job_id}/beats", response_model=list[BeatResponse])
def get_job_beats(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.complete:
        raise HTTPException(status_code=409, detail="Beat timeline is available after the job is complete.")
    if not job.storyboard:
        raise HTTPException(status_code=404, detail="Storyboard metadata is not available for this job.")

    beats = parse_storyboard(job.storyboard)
    video_path = output_video_path_for_job(job)
    if video_path is None:
        raise HTTPException(status_code=404, detail="Output video file was not found for thumbnail extraction.")

    rendered_windows = rendered_beat_windows_for_job(job, beats)
    return [
        BeatResponse(
            beat_number=beat.index,
            start=start,
            end=end,
            on_screen=beat.on_screen_text,
            vo_text=beat.vo_text,
            thumbnail_url=beat_thumbnail_url(job.id, beat, video_path, start, end),
        )
        for beat, (start, end) in zip(beats, rendered_windows)
    ]


@app.post("/api/jobs/{job_id}/beats/{beat_number}/regenerate", response_model=GenerateResponse)
def regenerate_beat(
    job_id: str,
    beat_number: int,
    request: BeatRegenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    parent = db.get(Job, job_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if parent.status != JobStatus.complete:
        raise HTTPException(status_code=409, detail="Original job must be complete before regenerating a beat.")
    if not parent.storyboard or not parent.scene_name:
        raise HTTPException(status_code=404, detail="Original job is missing storyboard metadata.")

    try:
        edited_storyboard = replace_storyboard_beat(parent.storyboard, beat_number, request.on_screen, request.vo_text)
        validate_storyboard_or_raise(edited_storyboard)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    child = Job(
        status=JobStatus.queued,
        progress_message=f"Queued edited Beat {beat_number} regeneration.",
        attempt_number=0,
        max_attempts=MAX_RETRIES,
        storyboard=edited_storyboard,
        generated_storyboard=parent.generated_storyboard,
        scene_name=parent.scene_name,
        orientation=parent.orientation,
        parent_job_id=parent.id,
        edited_beat_number=beat_number,
        cost_breakdown=empty_cost_breakdown(),
        estimated_cost_usd=0.0,
        cost_budget_usd=JOB_COST_CEILING_USD if JOB_COST_CEILING_USD > 0 else None,
        job_kind="beat_regeneration",
        request_payload={
            "parent_job_id": parent.id,
            "beat_number": beat_number,
            "on_screen": request.on_screen,
            "vo_text": request.vo_text,
        },
        pipeline_profile=parent.pipeline_profile,
        pipeline_version=parent.pipeline_version,
        llm_provider=parent.llm_provider,
        llm_model=parent.llm_model,
        llm_fast_model=parent.llm_fast_model,
        first_attempt_llm_provider=parent.first_attempt_llm_provider,
        first_attempt_llm_model=parent.first_attempt_llm_model,
        tts_provider=parent.tts_provider,
        tts_model=parent.tts_model,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    schedule_generation_job(background_tasks, child)
    return GenerateResponse(job_id=child.id)


@app.get("/api/jobs/{job_id}/beats/{beat_number}/params", response_model=BeatParamsResponse)
def get_beat_params(job_id: str, beat_number: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.complete:
        raise HTTPException(status_code=409, detail="Beat parameters are available after the job is complete.")
    scene_file = scene_file_for_job(job)
    if scene_file is None:
        raise HTTPException(status_code=404, detail="Generated scene code was not found.")

    params = beat_params_from_code(scene_file.read_text(encoding="utf-8"), beat_number)
    if not params:
        raise HTTPException(status_code=404, detail="Beat parameters were not found in the generated code.")
    return BeatParamsResponse(
        scale=params.get("scale"),
        gap=params.get("gap"),
        speed=params.get("speed"),
    )


@app.patch("/api/jobs/{job_id}/beats/{beat_number}/params", response_model=GenerateResponse)
def patch_beat_params(
    job_id: str,
    beat_number: int,
    request: BeatParamsPatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    parent = db.get(Job, job_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if parent.status != JobStatus.complete:
        raise HTTPException(status_code=409, detail="Original job must be complete before editing beat parameters.")
    if not parent.storyboard or not parent.scene_name:
        raise HTTPException(status_code=404, detail="Original job is missing scene metadata.")

    scene_file = scene_file_for_job(parent)
    if scene_file is None:
        raise HTTPException(status_code=404, detail="Generated scene code was not found.")

    values = request.model_dump(exclude_none=True)
    try:
        patch_beat_params_in_code(scene_file.read_text(encoding="utf-8"), beat_number, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Patched code did not parse: {exc}") from exc

    child = Job(
        status=JobStatus.queued,
        progress_message=f"Queued Beat {beat_number} parameter edit.",
        attempt_number=0,
        max_attempts=1,
        storyboard=parent.storyboard,
        generated_storyboard=parent.generated_storyboard,
        scene_name=parent.scene_name,
        orientation=parent.orientation,
        parent_job_id=parent.id,
        edited_beat_number=beat_number,
        cost_breakdown=empty_cost_breakdown(),
        estimated_cost_usd=0.0,
        cost_budget_usd=JOB_COST_CEILING_USD if JOB_COST_CEILING_USD > 0 else None,
        job_kind="beat_param_render",
        request_payload={
            "parent_job_id": parent.id,
            "beat_number": beat_number,
            "values": values,
        },
        pipeline_profile=parent.pipeline_profile,
        pipeline_version=parent.pipeline_version,
        llm_provider=parent.llm_provider,
        llm_model=parent.llm_model,
        llm_fast_model=parent.llm_fast_model,
        first_attempt_llm_provider=parent.first_attempt_llm_provider,
        first_attempt_llm_model=parent.first_attempt_llm_model,
        tts_provider=parent.tts_provider,
        tts_model=parent.tts_model,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    schedule_generation_job(background_tasks, child)
    return GenerateResponse(job_id=child.id)


class AdvancedRenderRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    orientation: Literal["portrait", "landscape"] = "portrait"
    duration_seconds: int = Field(45, ge=20, le=120)


@app.post("/api/render-advanced")
def render_advanced_video(
    request: AdvancedRenderRequest,
    background_tasks: BackgroundTasks,
):
    """Generate and render a high-quality custom Manim scene from any topic."""
    from app.pipeline import WORK_ROOT
    
    job_id = str(uuid.uuid4())
    work_dir = WORK_ROOT / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # Use Gemini to generate a proper Manim scene
    provider = get_llm_provider()
    system = (
        "You are a Manim scene generator. Generate COMPLETE, runnable Manim Python code "
        "for a 720x1280 portrait educational video. "
        "Rules:\n"
        "- Use Text() for labels, MathTex() for equations, Axes/plot for graphs\n"
        "- Portrait frame: config.frame_height=16, config.frame_width=9\n"
        "- Always include from manim import * at top\n"
        "- Subclass Scene, create ONE class called AdvancedScene\n"
        "- Include 5-8 beats with Write/Create/FadeIn/FadeOut animations\n"
        "- Show equations, plotted graphs, and step-by-step explanation\n"
        "- End with an Active Recall question with 8-second countdown\n"
        "- Total duration roughly {request.duration_seconds} seconds of animation\n"
        "- Use color palette: #60a5fa (blue), #a78bfa (purple), #34d399 (green)\n"
        "- Background color: #0a0a0f\n"
        "- Return ONLY Python code in a ```python block"
    )
    user_msg = f"Generate a complete Manim scene explaining: {request.topic}\nOrientation: {request.orientation}"
    
    try:
        response = provider.generate(
            system=system,
            user_message=user_msg,
            max_tokens=8000,
        )
        raw = response.text
        # Extract code from ```python block
        code_match = re.search(r"```python\s*([\s\S]+?)```", raw)
        if code_match:
            code = code_match.group(1).strip()
        else:
            code = raw.strip()
        
        scene_file = work_dir / "advanced_scene.py"
        scene_file.write_text(code, encoding="utf-8")
        
        def render_task():
            import subprocess, sys as _sys
            media_dir = work_dir / "media"
            cmd = [
                _sys.executable, "-m", "manim",
                str(scene_file), "AdvancedScene",
                "--media_dir", str(media_dir),
                "-qh", "--format=mp4", "--fps", "30",
                "--resolution", "720,1280",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"Manim render failed: {result.stderr[-500:]}")
            
            # Find the video file
            videos = list(media_dir.rglob("*.mp4"))
            if not videos:
                raise FileNotFoundError("No video generated")
            
            video_path = max(videos, key=lambda p: p.stat().st_mtime)
            
            # Copy to outputs
            from app.storage import OUTPUT_DIR
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            final_path = OUTPUT_DIR / f"{job_id}_{request.topic[:20]}_ADVANCED.mp4"
            import shutil
            shutil.copy2(video_path, final_path)
            
            # Update the job record
            from app.models import SessionLocal, Job
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job:
                    job.status = JobStatus.complete
                    job.output_video_url = f"/outputs/{final_path.name}"
                    job.progress_message = "Video generation complete."
                    db.commit()
        
        # Create a job record
        db = SessionLocal()
        try:
            job = Job(
                id=job_id,
                status=JobStatus.queued,
                progress_message="Generating advanced scene...",
                scene_name="AdvancedScene",
                orientation=request.orientation,
                llm_provider=provider.name,
                llm_model="gemini-2.5-flash",
                job_kind="advanced_render",
                request_payload={"topic": request.topic},
            )
            db.add(job)
            db.commit()
        finally:
            db.close()
        
        background_tasks.add_task(render_task)
        return {"job_id": job_id}
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request):
    """Receive RevenueCat webhook events and update user subscriptions."""
    payload = await request.json()
    from app.subscription import handle_revenuecat_webhook
    result = handle_revenuecat_webhook(payload)
    return {"status": "processed", "event": result}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_generator():
        last_updated = None
        while True:
            payload = None
            terminal = False
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job is None:
                    payload = 'event: error\ndata: {"detail":"Job not found."}\n\n'
                    terminal = True
                elif (job.updated_at.isoformat(), job.status.value) != last_updated:
                    last_updated = (job.updated_at.isoformat(), job.status.value)
                    payload = f"event: job\ndata: {json.dumps(public_job_to_dict(job))}\n\n"
                    terminal = job.status in {JobStatus.complete, JobStatus.failed}
                else:
                    terminal = job.status in {JobStatus.complete, JobStatus.failed}

            if payload is not None:
                yield payload

            if terminal:
                return

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
