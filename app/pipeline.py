import ast
import email.utils
import hashlib
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Any

from sqlalchemy.orm import Session

from app.frame_check import extract_beat_quality_frames, extract_sample_frames, get_media_duration
from app.learning import (
    LearningBeat,
    approved_failure_instructions,
    approved_reference_context,
    infer_learning_category,
    record_job_category_events,
    stage_failure_fix,
    stage_verified_reference_examples,
)
from app.llm_provider import LLMProvider, ProviderUnavailableError, get_llm_provider, is_provider_capacity_exception
from app.models import Job, JobStatus, SessionLocal
from app.storage import OUTPUT_DIR, upload_video
MAX_RETRIES = 4
CODEGEN_PARSE_RETRIES = 2
OVERLAP_RETRY_LIMIT = 2
VISION_LABEL_COLLISION_MAX_FRAMES = int(os.getenv("VISION_LABEL_COLLISION_MAX_FRAMES", "6"))
VISION_QUALITY_CHECK_MODE = os.getenv("VISION_QUALITY_CHECK_MODE", "sample").strip().lower()
VISION_QUALITY_SAMPLE_RATE = float(os.getenv("VISION_QUALITY_SAMPLE_RATE", "0.10"))
ATTEMPT_WALL_CLOCK_LIMIT_SECONDS = int(os.getenv("ATTEMPT_WALL_CLOCK_LIMIT_SECONDS", "720"))
RATE_LIMIT_RETRY_LIMIT = int(os.getenv("RATE_LIMIT_RETRY_LIMIT", "3"))
RATE_LIMIT_DEFAULT_SLEEP_SECONDS = float(os.getenv("RATE_LIMIT_DEFAULT_SLEEP_SECONDS", "30"))
ALLOW_LOCAL_STORYBOARD_FALLBACK = os.getenv("ALLOW_LOCAL_STORYBOARD_FALLBACK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
MAX_ESTIMATED_COST_USD_PER_VIDEO = float(os.getenv("MAX_ESTIMATED_COST_USD_PER_VIDEO", "0.15"))
JOB_COST_CEILING_USD = float(os.getenv("JOB_COST_CEILING_USD", "0.50"))
COST_BUDGET_MODE = os.getenv("COST_BUDGET_MODE", "warn").strip().lower()
RENDER_COMPUTE_USD_PER_HOUR = float(os.getenv("RENDER_COMPUTE_USD_PER_HOUR", "0"))
RENDER_QUALITY = os.getenv("MANIM_RENDER_QUALITY", "h").strip().lower()
PORTRAIT_RESOLUTION = os.getenv("MANIM_PORTRAIT_RESOLUTION", "1080,1920")
LANDSCAPE_RESOLUTION = os.getenv("MANIM_LANDSCAPE_RESOLUTION", "1920,1080")


@dataclass(frozen=True)
class RenderTier:
    """Render quality tier for the tiered pipeline.

    Attributes:
        name:                Human-readable tier label (e.g. "draft").
        quality_flag:        Single-letter Manim quality flag (``l`` = low,
                             ``m`` = medium, ``h`` = high, ``k`` = 4K).
        portrait_resolution: ``"width,height"`` string for portrait renders.
        landscape_resolution: ``"width,height"`` string for landscape renders.
        fps:                 Target frame rate.
    """

    name: str
    quality_flag: str
    portrait_resolution: str
    landscape_resolution: str
    fps: int


# Pre-defined render tiers
# Tier 1 – rapid draft used by the automated pre-flight gate
RENDER_TIER_1_DRAFT = RenderTier(
    name="draft",
    quality_flag="l",
    portrait_resolution="480,854",
    landscape_resolution="854,480",
    fps=15,
)
# Tier 2 – high-quality draft (optional human review)
RENDER_TIER_2_HIGH_DRAFT = RenderTier(
    name="high_draft",
    quality_flag="m",
    portrait_resolution="720,1280",
    landscape_resolution="1280,720",
    fps=30,
)
# Tier 3 – production (default)
RENDER_TIER_3_PRODUCTION = RenderTier(
    name="production",
    quality_flag="h",
    portrait_resolution=PORTRAIT_RESOLUTION,
    landscape_resolution=LANDSCAPE_RESOLUTION,
    fps=60,
)
# Tier 4 – flagship / 4K (opt-in via request_payload render_tier=4)
RENDER_TIER_4_FLAGSHIP = RenderTier(
    name="flagship",
    quality_flag="k",
    portrait_resolution="1440,2560",
    landscape_resolution="2560,1440",
    fps=60,
)

_TIER_NUMBER_MAP: dict[int, RenderTier] = {
    1: RENDER_TIER_1_DRAFT,
    2: RENDER_TIER_2_HIGH_DRAFT,
    3: RENDER_TIER_3_PRODUCTION,
    4: RENDER_TIER_4_FLAGSHIP,
}


def render_tier_by_number(tier: int) -> RenderTier:
    """Return the :class:`RenderTier` for a numeric tier (1-4)."""
    if tier not in _TIER_NUMBER_MAP:
        raise ValueError(f"Unknown render tier {tier!r}; valid values: 1, 2, 3, 4")
    return _TIER_NUMBER_MAP[tier]
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("ANTHROPIC_MAX_TOKENS", "12000")))
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "onyx")
OPENAI_TTS_SPEED = min(4.0, max(0.25, float(os.getenv("OPENAI_TTS_SPEED", "0.92"))))
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai").strip().lower()
ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS = float(os.getenv("ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS", "1.0"))
ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS = float(os.getenv("ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS", "5.0"))
OPENAI_INPUT_USD_PER_MILLION_TOKENS = float(os.getenv("OPENAI_INPUT_USD_PER_MILLION_TOKENS", "5.0"))
OPENAI_OUTPUT_USD_PER_MILLION_TOKENS = float(os.getenv("OPENAI_OUTPUT_USD_PER_MILLION_TOKENS", "30.0"))
GEMINI_INPUT_USD_PER_MILLION_TOKENS = float(os.getenv("GEMINI_INPUT_USD_PER_MILLION_TOKENS", "0.3"))
GEMINI_OUTPUT_USD_PER_MILLION_TOKENS = float(os.getenv("GEMINI_OUTPUT_USD_PER_MILLION_TOKENS", "2.5"))
LLM_TOKEN_PRICING_USD_PER_MILLION = {
    "anthropic": {
        "input": ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS,
        "output": ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS,
    },
    "openai": {
        "input": OPENAI_INPUT_USD_PER_MILLION_TOKENS,
        "output": OPENAI_OUTPUT_USD_PER_MILLION_TOKENS,
    },
    "gemini": {
        "input": GEMINI_INPUT_USD_PER_MILLION_TOKENS,
        "output": GEMINI_OUTPUT_USD_PER_MILLION_TOKENS,
    },
}
LLM_MODEL_PRICING_USD_PER_MILLION = {
    "anthropic": {
        "claude-haiku-4-5": {
            "input": float(os.getenv("ANTHROPIC_HAIKU_4_5_INPUT_USD_PER_MILLION_TOKENS", "1.0")),
            "output": float(os.getenv("ANTHROPIC_HAIKU_4_5_OUTPUT_USD_PER_MILLION_TOKENS", "5.0")),
        },
        "claude-sonnet-4-6": {
            "input": float(os.getenv("ANTHROPIC_SONNET_4_6_INPUT_USD_PER_MILLION_TOKENS", "3.0")),
            "output": float(os.getenv("ANTHROPIC_SONNET_4_6_OUTPUT_USD_PER_MILLION_TOKENS", "15.0")),
        },
        "claude-sonnet-4-5": {
            "input": float(os.getenv("ANTHROPIC_SONNET_4_5_INPUT_USD_PER_MILLION_TOKENS", "3.0")),
            "output": float(os.getenv("ANTHROPIC_SONNET_4_5_OUTPUT_USD_PER_MILLION_TOKENS", "15.0")),
        },
    },
    "openai": {
        "gpt-5.5": {
            "input": float(os.getenv("OPENAI_GPT_5_5_INPUT_USD_PER_MILLION_TOKENS", "5.0")),
            "output": float(os.getenv("OPENAI_GPT_5_5_OUTPUT_USD_PER_MILLION_TOKENS", "30.0")),
        },
        "gpt-5.4-mini": {
            "input": float(os.getenv("OPENAI_GPT_5_4_MINI_INPUT_USD_PER_MILLION_TOKENS", "0.75")),
            "output": float(os.getenv("OPENAI_GPT_5_4_MINI_OUTPUT_USD_PER_MILLION_TOKENS", "4.5")),
        },
        "gpt-5.4": {
            "input": float(os.getenv("OPENAI_GPT_5_4_INPUT_USD_PER_MILLION_TOKENS", "2.5")),
            "output": float(os.getenv("OPENAI_GPT_5_4_OUTPUT_USD_PER_MILLION_TOKENS", "15.0")),
        },
    },
    "gemini": {
        "gemini-2.5-flash-lite": {
            "input": float(os.getenv("GEMINI_2_5_FLASH_LITE_INPUT_USD_PER_MILLION_TOKENS", "0.1")),
            "output": float(os.getenv("GEMINI_2_5_FLASH_LITE_OUTPUT_USD_PER_MILLION_TOKENS", "0.4")),
        },
        "gemini-2.5-flash": {
            "input": float(os.getenv("GEMINI_2_5_FLASH_INPUT_USD_PER_MILLION_TOKENS", "0.3")),
            "output": float(os.getenv("GEMINI_2_5_FLASH_OUTPUT_USD_PER_MILLION_TOKENS", "2.5")),
        },
    },
}
OPENAI_TTS_USD_PER_MILLION_CHARS = {
    "tts-1": float(os.getenv("OPENAI_TTS_1_USD_PER_MILLION_CHARS", "15.0")),
    "tts-1-hd": float(os.getenv("OPENAI_TTS_1_HD_USD_PER_MILLION_CHARS", "30.0")),
}
MAX_TARGET_SECONDS = 180
TOPIC_MAX_TARGET_SECONDS = int(os.getenv("TOPIC_MAX_TARGET_SECONDS", "240"))
DRIFT_FAILURE_RATIO = 0.15
PURE_PYTHON_FEEDBACK = (
    "Your previous response contained explanation text instead of pure Python code. "
    "Respond with ONLY the code, no analysis, no reasoning, no text before or after the code."
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_WORK_ROOT = PROJECT_DIR.parent / "vivacity_job_runs"
LEGACY_WORK_ROOT = PROJECT_DIR / "job_runs"
WORK_ROOT = Path(os.getenv("VIVACITY_WORK_ROOT", str(DEFAULT_WORK_ROOT))).resolve()
CACHE_ROOT = Path(os.getenv("VIVACITY_CACHE_ROOT", str(PROJECT_DIR.parent / "vivacity_cache"))).resolve()
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", str(CACHE_ROOT / "tts"))).resolve()
TTS_CACHE_ENABLED = os.getenv("TTS_CACHE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
TTS_CACHE_WAIT_SECONDS = max(1.0, float(os.getenv("TTS_CACHE_WAIT_SECONDS", "90")))
TTS_CACHE_STALE_LOCK_SECONDS = max(30.0, float(os.getenv("TTS_CACHE_STALE_LOCK_SECONDS", "600")))
ANTHROPIC_MODEL_FAST = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5")
OPENAI_CODE_MODEL_FAST = os.getenv("OPENAI_CODE_MODEL_FAST", "gpt-5.4-mini")
GEMINI_MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "gemini-2.5-flash-lite")
REFERENCE_SCENES_PATH = PROJECT_DIR / "reference_scenes.py"
REFERENCE_SCENES = REFERENCE_SCENES_PATH.read_text(encoding="utf-8") if REFERENCE_SCENES_PATH.exists() else ""
REFERENCE_SCENE_CATEGORIES = ("force-diagrams", "curve-plotting", "algebraic-stepwise", "geometric-proof")
QUALITY_SCORE_THRESHOLD = int(os.getenv("QUALITY_SCORE_THRESHOLD", "4"))
_UNSET = object()
Orientation = Literal["portrait", "landscape"]
MOJIBAKE_MARKERS = ("Ã", "Â", "â", "Î", "Ï")
PROHIBITED_MANIM_COLOR_NAMES = {
    "YELLOW_GREEN",
    "GREEN_YELLOW",
    "LIGHT_BLUE",
    "LIGHT_GREEN",
    "DARK_BLUE",
    "DARK_GREEN",
}
DEFAULT_VIDEO_SEMANTIC_PALETTE = {
    "TITLE_COLOR": "TEAL_C",
    "PRIMARY_COLOR": "BLUE_C",
    "SECONDARY_COLOR": "WHITE",
    "STRUCTURE_COLOR": "GREY_B",
    "RELATION_COLOR": "YELLOW_C",
    "HIGHLIGHT_COLOR": "ORANGE",
    "SPECIAL_COLOR": "PURPLE_C",
    "POSITIVE_COLOR": "GREEN_C",
    "NEGATIVE_COLOR": "RED_C",
    "REFERENCE_CURVE_COLOR": "WHITE",
    "PRIMARY_CURVE_COLOR": "BLUE_C",
    "SECONDARY_CURVE_COLOR": "GOLD_A",
    "CENTRAL_ATOM_COLOR": "PRIMARY_COLOR",
    "SURROUNDING_ATOM_COLOR": "SECONDARY_COLOR",
    "BOND_COLOR": "RELATION_COLOR",
    "LONE_PAIR_COLOR": "SPECIAL_COLOR",
    "ANGLE_COLOR": "HIGHLIGHT_COLOR",
    "FORCE_COLOR": "PRIMARY_COLOR",
}
SEMANTIC_COLOR_ASSIGNMENT_PATTERN = re.compile(
    r"(?m)^\s*([A-Z][A-Z0-9_]*COLOR)\s*=\s*([A-Z][A-Z0-9_]*)\s*(?:#.*)?$"
)

# Provider responses occasionally lose LaTeX backslashes and turn an
# expression into a caption such as "Displaystyle I Big x cos x".  That is
# never valid rendered content and must be rejected before Manim starts.
MALFORMED_MATH_CAPTION_PATTERN = re.compile(
    r"\b(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle)\b"
    r"|\b(?:big|bigg)\s+[A-Za-z]\s+(?:int|sum|frac|sin|cos|tan|pi)\b"
    r"|\b(?:int|integral)\s+o\s+(?:pi|\\pi)\b",
    re.IGNORECASE,
)
BARE_LATEX_COMMAND_PATTERN = re.compile(
    r"(?<!\\)\b(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle|"
    r"big|bigg|int|sum|frac|sqrt|sin|cos|tan|pi|theta|cdot)\b",
    re.IGNORECASE,
)
INTEGRAL_BOUND_LETTER_O_PATTERN = re.compile(
    r"\\int\s*(?:_\s*\{\s*|_\s*|\{\s*)?o(?=\s*(?:\}|\^|\\pi\b|pi\b))",
    re.IGNORECASE,
)
DEBUG_BUTTON_LABELS = frozenset({"start", "change", "result"})
APPROVED_MANIM_COLOR_PATTERN = re.compile(
    r"^(?:WHITE|BLACK|RED|GREEN|BLUE|YELLOW|ORANGE|PURPLE|PINK|TEAL|GRAY|GREY|MAROON|GOLD)(?:_[A-E])?$"
)
STRICT_TEXT_MATH_PATTERN = re.compile(r"[$\\]|(?:\^|_)\s*[\{\(]")
DUPLICATE_CONSECUTIVE_WORD_PATTERN = re.compile(
    r"\b([A-Za-z]{2,})\b(?:\s|[,;:.!-])+\1\b",
    re.IGNORECASE,
)
MACLAURIN_ZERO_TYPO_PATTERN = re.compile(
    r"\bf\s*\^\s*(?:\{\s*)?\(?\s*n\s*\)?(?:\s*\})?\s*\(\s*o\s*\)|\b(?:x|a)\s*=\s*o\b",
    re.IGNORECASE,
)
MATH_COMPLEXITY_PATTERN = re.compile(r"\\[A-Za-z]+|(?:\^|_)(?:\{|\(|[A-Za-z0-9])|=")
MATH_PHYSICS_TOPIC_PATTERN = re.compile(
    r"\b(?:math(?:ematics)?|algebra|calculus|geometry|trigonometry|theorem|proof|series|limit|derivative|"
    r"integral|equation|function|graph|vector|physics|mechanics?|force|motion|velocity|acceleration|"
    r"tension|pulley|atwood|momentum|energy|electric|magnetic|optics?|wave)\b",
    re.IGNORECASE,
)
EARLY_SYMBOL_REQUIRED_TOPIC_PATTERN = re.compile(
    r"\b(?:atwood|pulley|deriv(?:ation|e)?|proof|series|limit|equation|calculate|calculation|function|"
    r"force|velocity|acceleration|tension|momentum|energy|integral)\b",
    re.IGNORECASE,
)
EARLY_SYMBOLIC_EVIDENCE_PATTERN = re.compile(
    r"=|\\(?:frac|sum|int|sqrt|theta|alpha|beta|gamma)\b|(?:\^|_)\s*[\{\(A-Za-z0-9]|"
    r"\bm\s*_?\s*[12]\b|\b(?:T|F|v|a|g)\s*(?:=|[-+*/])",
)
GRAPH_CONTENT_PATTERN = re.compile(r"\b(?:graph|axes?|plot|curve)\b", re.IGNORECASE)
GRAPH_TITLE_NAME_PATTERN = re.compile(r"(?:title|heading|caption)", re.IGNORECASE)
EXPLANATION_STOP_WORDS = {
    "add",
    "display",
    "equation",
    "expression",
    "highlight",
    "label",
    "show",
    "term",
    "terms",
    "then",
    "transform",
    "write",
}


class AttemptFailed(Exception):
    """Raised when one outer render attempt is exhausted but the job can keep retrying."""


class TruncatedCodeResponse(Exception):
    """Raised when a provider reports that its generated code hit the output-token limit."""


class RateLimitExhausted(Exception):
    """Raised when repeated provider 429s exceed the separate backoff budget."""


class CostBudgetExceeded(Exception):
    """Raised before another paid stage starts after a job reaches its configured budget."""


class SceneIsolationError(RuntimeError):
    """Raised before rendering when a scene file is not isolated to one job and class."""


MANIM_SCENE_BASE_NAMES = {
    "Scene",
    "ThreeDScene",
    "MovingCameraScene",
    "ZoomedScene",
    "VectorScene",
    "LinearTransformationScene",
    "SampleSpaceScene",
}


@dataclass(frozen=True)
class StoryboardBeat:
    index: int
    start_sec: float
    end_sec: float
    on_screen_text: str
    vo_text: str | None

    @property
    def storyboard_duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


@dataclass(frozen=True)
class TimedBeat:
    beat: StoryboardBeat
    audio_path: Path | None
    target_duration: float
    gap_before: float


@dataclass(frozen=True)
class FrameQualityScore:
    timestamp: float
    frame_path: Path
    beat_index: int
    accuracy: int
    depth: int
    logical_flow: int
    visual_relevance: int
    element_layout: int
    summary: str

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "frame_path": str(self.frame_path),
            "beat_index": self.beat_index,
            "accuracy": self.accuracy,
            "depth": self.depth,
            "logical_flow": self.logical_flow,
            "visual_relevance": self.visual_relevance,
            "element_layout": self.element_layout,
            "summary": self.summary,
        }


def update_job(
    db: Session,
    job_id: str,
    status: JobStatus | None = None,
    progress_message: str | None = None,
    attempt_number: int | None = None,
    error: str | None | object = _UNSET,
    output_video_url: str | None = None,
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    if status is not None:
        job.status = status
        if status not in {JobStatus.queued, JobStatus.complete, JobStatus.failed} and job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        if status in {JobStatus.complete, JobStatus.failed}:
            job.completed_at = datetime.now(timezone.utc)
    if progress_message is not None:
        job.progress_message = with_cost_suffix(progress_message, job.estimated_cost_usd or 0.0)
    if attempt_number is not None:
        job.attempt_number = attempt_number
    if error is not _UNSET:
        job.error = error
    if output_video_url is not None:
        job.output_video_url = output_video_url
    db.commit()


def with_cost_suffix(message: str, estimated_cost_usd: float) -> str:
    base_message = re.sub(r"\s+\(\$[0-9.]+ so far\)$", "", message)
    return f"{base_message} (${estimated_cost_usd:.4f} so far)"


def refresh_progress_cost(db: Session, job_id: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.progress_message = with_cost_suffix(job.progress_message, job.estimated_cost_usd or 0.0)
    db.commit()


def empty_cost_breakdown() -> dict:
    return {
        "anthropic": {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "input_usd_per_million_tokens": ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS,
            "output_usd_per_million_tokens": ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS,
        },
        "openai": {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "input_usd_per_million_tokens": OPENAI_INPUT_USD_PER_MILLION_TOKENS,
            "output_usd_per_million_tokens": OPENAI_OUTPUT_USD_PER_MILLION_TOKENS,
        },
        "gemini": {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "input_usd_per_million_tokens": GEMINI_INPUT_USD_PER_MILLION_TOKENS,
            "output_usd_per_million_tokens": GEMINI_OUTPUT_USD_PER_MILLION_TOKENS,
        },
        "openai_tts": {
            "calls": 0,
            "cache_hits": 0,
            "characters": 0,
            "cost_usd": 0.0,
            "usd_per_million_chars_by_model": OPENAI_TTS_USD_PER_MILLION_CHARS,
        },
        "render_only": {
            "calls": 0,
            "cost_usd": 0.0,
            "note": "Render-only beat parameter edits do not call an LLM provider.",
        },
        "render_compute": {
            "calls": 0,
            "seconds": 0.0,
            "cost_usd": 0.0,
            "usd_per_hour": RENDER_COMPUTE_USD_PER_HOUR,
        },
    }


def llm_token_rates(provider_name: str, model: str | None = None) -> dict[str, float]:
    normalized_model = (model or "").strip().lower()
    model_rates = LLM_MODEL_PRICING_USD_PER_MILLION.get(provider_name, {})
    for model_prefix in sorted(model_rates, key=len, reverse=True):
        if normalized_model == model_prefix or normalized_model.startswith(f"{model_prefix}-"):
            return model_rates[model_prefix]
    return LLM_TOKEN_PRICING_USD_PER_MILLION.get(
        provider_name,
        LLM_TOKEN_PRICING_USD_PER_MILLION["anthropic"],
    )


def llm_cost_event(provider_name: str, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    rates = llm_token_rates(provider_name, model)
    input_cost = (input_tokens / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return input_cost + output_cost


def anthropic_cost_event(input_tokens: int, output_tokens: int) -> float:
    return llm_cost_event("anthropic", input_tokens, output_tokens, os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"))


def normalized_cost_breakdown(value: dict | None) -> dict:
    breakdown = empty_cost_breakdown()
    if not value:
        return breakdown
    for provider, provider_data in value.items():
        if isinstance(provider_data, dict):
            breakdown.setdefault(provider, {})
            breakdown[provider].update(provider_data)
    return breakdown


def add_llm_cost(
    db: Session,
    job_id: str,
    provider_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    event_cost = llm_cost_event(provider_name, input_tokens, output_tokens, model)
    job = db.get(Job, job_id)
    if job is None:
        return event_cost
    breakdown = normalized_cost_breakdown(job.cost_breakdown)
    provider_cost = breakdown.setdefault(provider_name, {})
    rates = llm_token_rates(provider_name, model)
    provider_cost["calls"] = int(provider_cost.get("calls", 0)) + 1
    provider_cost["input_tokens"] = int(provider_cost.get("input_tokens", 0)) + input_tokens
    provider_cost["output_tokens"] = int(provider_cost.get("output_tokens", 0)) + output_tokens
    provider_cost["cost_usd"] = float(provider_cost.get("cost_usd", 0.0)) + event_cost
    provider_cost["model"] = model
    provider_cost["input_usd_per_million_tokens"] = rates["input"]
    provider_cost["output_usd_per_million_tokens"] = rates["output"]
    model_cost = provider_cost.setdefault("models", {}).setdefault(
        model,
        {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "input_usd_per_million_tokens": rates["input"],
            "output_usd_per_million_tokens": rates["output"],
        },
    )
    model_cost["calls"] = int(model_cost.get("calls", 0)) + 1
    model_cost["input_tokens"] = int(model_cost.get("input_tokens", 0)) + input_tokens
    model_cost["output_tokens"] = int(model_cost.get("output_tokens", 0)) + output_tokens
    model_cost["cost_usd"] = float(model_cost.get("cost_usd", 0.0)) + event_cost
    job.cost_breakdown = breakdown
    job.estimated_cost_usd = float(job.estimated_cost_usd or 0.0) + event_cost
    db.commit()
    refresh_progress_cost(db, job_id)
    enforce_job_cost_budget(db, job_id)
    return event_cost


def provider_for_job(db: Session, job_id: str, attempt_number: int = 1) -> LLMProvider:
    job = db.get(Job, job_id)
    use_first_attempt_provider = (
        job is not None
        and attempt_number == 1
        and bool(job.first_attempt_llm_provider)
    )
    provider_name = (
        job.first_attempt_llm_provider
        if use_first_attempt_provider
        else (job.llm_provider if job is not None and job.llm_provider else None)
    )
    provider = get_llm_provider(provider_name)
    selected_model = job.first_attempt_llm_model if use_first_attempt_provider else (job.llm_model if job else None)
    if selected_model:
        provider.model = selected_model
        provider.fast_model = selected_model
    elif job is not None and job.llm_fast_model:
        provider.fast_model = job.llm_fast_model
    return provider


def llm_response_identity(response, provider: LLMProvider, requested_model: str) -> tuple[str, str]:
    return (
        getattr(response, "provider_name", None) or provider.name,
        getattr(response, "model", None) or requested_model,
    )


def persist_generated_code(db: Session, job_id: str, code: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.generated_code = code
    db.commit()


def add_anthropic_cost(db: Session, job_id: str, model: str, input_tokens: int, output_tokens: int) -> float:
    return add_llm_cost(db, job_id, "anthropic", model, input_tokens, output_tokens)


def tts_rate_for_model(model: str) -> float:
    return OPENAI_TTS_USD_PER_MILLION_CHARS.get(model, OPENAI_TTS_USD_PER_MILLION_CHARS["tts-1-hd"])


def add_openai_tts_cost(db: Session, job_id: str, model: str, characters: int) -> float:
    rate = tts_rate_for_model(model)
    event_cost = (characters / 1_000_000) * rate
    job = db.get(Job, job_id)
    if job is None:
        return event_cost
    breakdown = normalized_cost_breakdown(job.cost_breakdown)
    tts_cost = breakdown["openai_tts"]
    tts_cost["calls"] = int(tts_cost.get("calls", 0)) + 1
    tts_cost["characters"] = int(tts_cost.get("characters", 0)) + characters
    tts_cost["cost_usd"] = float(tts_cost.get("cost_usd", 0.0)) + event_cost
    tts_cost["model"] = model
    tts_cost["usd_per_million_chars"] = rate
    job.cost_breakdown = breakdown
    job.estimated_cost_usd = float(job.estimated_cost_usd or 0.0) + event_cost
    db.commit()
    refresh_progress_cost(db, job_id)
    enforce_job_cost_budget(db, job_id)
    return event_cost


def record_openai_tts_cache_hit(db: Session | None, job_id: str | None) -> None:
    if db is None or job_id is None:
        return
    job = db.get(Job, job_id)
    if job is None:
        return
    breakdown = normalized_cost_breakdown(job.cost_breakdown)
    tts_cost = breakdown["openai_tts"]
    tts_cost["cache_hits"] = int(tts_cost.get("cache_hits", 0)) + 1
    job.cost_breakdown = breakdown
    db.commit()


def record_render_only_edit(db: Session, job_id: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    breakdown = normalized_cost_breakdown(job.cost_breakdown)
    render_only = breakdown["render_only"]
    render_only["calls"] = int(render_only.get("calls", 0)) + 1
    render_only["cost_usd"] = float(render_only.get("cost_usd", 0.0))
    job.cost_breakdown = breakdown
    db.commit()
    refresh_progress_cost(db, job_id)


def record_render_compute_cost(db: Session, job_id: str, duration_seconds: float) -> float:
    duration_seconds = max(0.0, float(duration_seconds))
    event_cost = duration_seconds / 3600.0 * RENDER_COMPUTE_USD_PER_HOUR
    job = db.get(Job, job_id)
    if job is None:
        return event_cost
    breakdown = normalized_cost_breakdown(job.cost_breakdown)
    compute = breakdown["render_compute"]
    compute["calls"] = int(compute.get("calls", 0)) + 1
    compute["seconds"] = float(compute.get("seconds", 0.0)) + duration_seconds
    compute["cost_usd"] = float(compute.get("cost_usd", 0.0)) + event_cost
    compute["usd_per_hour"] = RENDER_COMPUTE_USD_PER_HOUR
    job.cost_breakdown = breakdown
    job.render_seconds = float(job.render_seconds or 0.0) + duration_seconds
    job.estimated_compute_cost_usd = float(job.estimated_compute_cost_usd or 0.0) + event_cost
    job.estimated_cost_usd = float(job.estimated_cost_usd or 0.0) + event_cost
    db.commit()
    refresh_progress_cost(db, job_id)
    enforce_job_cost_budget(db, job_id)
    return event_cost


def enforce_job_cost_budget(db: Session, job_id: str, projected_additional_cost_usd: float = 0.0) -> None:
    if COST_BUDGET_MODE != "enforce":
        return
    job = db.get(Job, job_id)
    if job is None or job.cost_budget_usd is None:
        return
    projected_total = float(job.estimated_cost_usd or 0.0) + max(0.0, projected_additional_cost_usd)
    if projected_total > float(job.cost_budget_usd):
        raise CostBudgetExceeded(
            f"The next stage would exceed the job cost budget: ${projected_total:.4f} projected against "
            f"a ${job.cost_budget_usd:.4f} budget."
        )


def projected_llm_call_cost(
    provider_name: str,
    model: str,
    system: str,
    user_message: str,
    max_output_tokens: int,
) -> float:
    estimated_input_tokens = max(1, (len(system) + len(user_message) + 3) // 4)
    return llm_cost_event(provider_name, estimated_input_tokens, max_output_tokens, model)


def log_debug_timing(log_path: Path | None, message: str) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def parse_reference_scene_library(source: str) -> dict[str, str]:
    library: dict[str, list[str]] = {}
    current_category: str | None = None
    current_lines: list[str] = []
    for line in source.splitlines():
        match = re.match(r"#\s*CATEGORY:\s*(?P<category>[a-z-]+)\s*$", line)
        if match:
            if current_category and current_lines:
                library.setdefault(current_category, []).append("\n".join(current_lines).strip())
            current_category = match.group("category")
            current_lines = [line]
            continue
        if current_category:
            current_lines.append(line)
    if current_category and current_lines:
        library.setdefault(current_category, []).append("\n".join(current_lines).strip())
    return {category: "\n\n".join(snippets).strip() for category, snippets in library.items()}


def storyboard_reference_categories(storyboard: str, max_categories: int = 2) -> list[str]:
    text = storyboard.lower()
    keyword_map = {
        "force-diagrams": (
            "force", "friction", "normal", "incline", "inclined", "block", "mg", "acceleration",
            "free body", "fbd", "tension", "weight",
        ),
        "curve-plotting": (
            "curve", "graph", "plot", "axis", "axes", "parabola", "sine", "cosine", "function",
            "tangent", "slope",
        ),
        "algebraic-stepwise": (
            "derive", "equation", "solve", "substitute", "simplify", "therefore", "step", "formula",
            "series", "limit", "expansion",
        ),
        "geometric-proof": (
            "triangle", "circle", "angle", "proof", "similar", "chord", "radius", "perpendicular",
            "theorem", "geometry",
        ),
    }
    scored = []
    for category, keywords in keyword_map.items():
        score = sum(text.count(keyword) for keyword in keywords)
        if score:
            scored.append((score, category))
    if not scored:
        return ["algebraic-stepwise"]
    scored.sort(key=lambda item: (-item[0], REFERENCE_SCENE_CATEGORIES.index(item[1])))
    return [category for _, category in scored[:max_categories]]


def selected_reference_scenes(storyboard: str) -> str:
    library = parse_reference_scene_library(REFERENCE_SCENES)
    categories = storyboard_reference_categories(storyboard)
    selected = [library[category] for category in categories if category in library]
    learned_categories = learning_categories_for_storyboard(storyboard)
    learned_context = approved_reference_context(learned_categories)
    if learned_context:
        selected.append(learned_context)
    if selected:
        return "\n\n".join(selected)
    return REFERENCE_SCENES


def learning_categories_for_storyboard(storyboard: str) -> list[str]:
    categories: list[str] = []
    for beat in parse_storyboard(storyboard):
        category = infer_learning_category(beat.on_screen_text)
        if category not in categories:
            categories.append(category)
    return categories or ["general-animation"]


def beat_number_from_feedback(feedback: str | None) -> int | None:
    if not feedback:
        return None
    match = re.search(r"\bBeat\s+(\d+)\b", feedback, re.IGNORECASE)
    return int(match.group(1)) if match else None


def learning_beats_from_storyboard(beats: list[StoryboardBeat]) -> list[LearningBeat]:
    return [LearningBeat(index=beat.index, on_screen_text=beat.on_screen_text) for beat in beats]


def record_quality_score(db: Session | None, job_id: str | None, score: FrameQualityScore) -> None:
    if db is None or job_id is None:
        return
    job = db.get(Job, job_id)
    if job is None:
        return
    scores = list(job.quality_scores or [])
    scores.append(score.as_dict())
    job.quality_scores = scores
    db.commit()


@contextmanager
def timed_stage(log_path: Path | None, label: str):
    start = time.monotonic()
    log_debug_timing(log_path, f"START stage={label}")
    try:
        yield
    except Exception as exc:
        elapsed = time.monotonic() - start
        log_debug_timing(log_path, f"END stage={label} status=error duration_sec={elapsed:.3f} error={type(exc).__name__}: {exc}")
        raise
    else:
        elapsed = time.monotonic() - start
        log_debug_timing(log_path, f"END stage={label} status=ok duration_sec={elapsed:.3f}")


def validate_storyboard_or_raise(storyboard: str, max_target_seconds: int = MAX_TARGET_SECONDS) -> list[StoryboardBeat]:
    if not storyboard or not storyboard.strip():
        raise ValueError("Storyboard is required.")

    placeholder_markers = [
        "<one line concept name",
        "<seconds, e.g.",
        "<e.g. JEE aspirants",
        "<what appears/animates>",
        "<exact voiceover line>",
    ]
    if any(marker in storyboard for marker in placeholder_markers):
        raise ValueError("Storyboard still looks like the unedited template.")

    beats = parse_storyboard(storyboard)
    if not beats:
        raise ValueError("Storyboard must include beat lines with [start-end] ON SCREEN: ... | VO: ...")

    if any(beat.end_sec <= beat.start_sec for beat in beats):
        raise ValueError("Each storyboard beat must have an end time greater than its start time.")

    if any(beat.start_sec < 0 for beat in beats):
        raise ValueError("Storyboard beat times cannot be negative.")

    for prev, current in zip(beats, beats[1:]):
        if current.start_sec < prev.end_sec:
            raise ValueError("Storyboard beat ranges must not overlap.")

    implied_duration = max(beat.end_sec for beat in beats)
    if implied_duration > max_target_seconds:
        raise ValueError(f"Storyboard target length is {implied_duration:.1f}s; configured limit is {max_target_seconds}s.")

    return beats


def parse_storyboard(storyboard: str) -> list[StoryboardBeat]:
    pattern = re.compile(
        r"^\s*\[\s*(?P<start>\d+(?:\.\d+)?)\s*s?\s*-\s*(?P<end>\d+(?:\.\d+)?)\s*s?\s*\]\s*"
        r"ON SCREEN:\s*(?P<screen>.*?)\s*\|\s*VO:\s*(?P<vo>.*)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    beats: list[StoryboardBeat] = []
    for match in pattern.finditer(storyboard):
        vo_text = normalize_vo_text(match.group("vo"))
        beats.append(
            StoryboardBeat(
                index=len(beats) + 1,
                start_sec=float(match.group("start")),
                end_sec=float(match.group("end")),
                on_screen_text=match.group("screen").strip(),
                vo_text=vo_text,
            )
        )
    return beats


def normalize_vo_text(raw_vo: str) -> str | None:
    text = re.sub(r"<!--.*?-->", "", raw_vo).strip()
    quoted = re.match(r'^"(?P<text>.*)"$', text)
    if quoted:
        text = quoted.group("text").strip()
    normalized = re.sub(r"[\s._-]+", " ", text.strip().lower()).strip()
    normalized = normalized.strip("()[]{} ")
    if normalized in {"", "silent", "silence", "no vo", "no voiceover", "no voice over", "none"}:
        return None
    return text or None


def dense_beat_score(on_screen_text: str) -> int:
    text = on_screen_text.lower()
    label_terms = len(re.findall(r"\b(label|labels|equation|equations|curve|curves|arrow|arrows|force|forces|vector|vectors|component|components|point|points|annotation|annotations)\b", text))
    listed_items = max(0, text.count(",") + len(re.findall(r"\b(?:and|plus|alongside|simultaneously|together)\b", text)) - 1)
    explicit_counts = {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
    }
    count_score = max((value for word, value in explicit_counts.items() if re.search(rf"\b{word}\b", text)), default=0)
    digit_score = max((int(match) for match in re.findall(r"\b([2-9])\b", text)), default=0)
    shrink_markers = 3 if re.search(r"\b(tiny|small font|fit all|all at once|simultaneous|simultaneously|crowded|dense)\b", text) else 0
    return max(label_terms + listed_items + shrink_markers, count_score, digit_score)


def split_dense_beat_line(match: re.Match, next_start: float | None = None) -> list[str]:
    start = float(match.group("start"))
    end = float(match.group("end"))
    screen = match.group("screen").strip()
    vo = match.group("vo").strip()
    duration = end - start
    if duration < 6:
        return [match.group(0)]
    midpoint = round(start + duration / 2, 2)
    if next_start is not None and midpoint >= next_start:
        return [match.group(0)]
    first_vo = vo
    second_vo = '"Now we connect the remaining pieces without crowding the frame."'
    if vo.startswith('"') and vo.endswith('"') and len(vo) > 18:
        inner = vo[1:-1]
        split_at = inner.find(". ")
        if split_at > 10:
            first_vo = f'"{inner[: split_at + 1].strip()}"'
            second_vo = f'"{inner[split_at + 2 :].strip()}"'
    return [
        f"[{start:g}-{midpoint:g}] ON SCREEN: {screen}. Establish the first relationship with a clear pause. | VO: {first_vo}",
        f"[{midpoint:g}-{end:g}] ON SCREEN: {screen}. Add the remaining relationship after the pause. | VO: {second_vo}",
    ]


def paginate_dense_storyboard_beats(storyboard: str) -> str:
    pattern = re.compile(
        r"^\s*\[(?P<start>\d+(?:\.\d+)?)-(?P<end>\d+(?:\.\d+)?)\]\s*"
        r"ON SCREEN:\s*(?P<screen>.*?)\s*\|\s*VO:\s*(?P<vo>.*)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(pattern.finditer(storyboard))
    if not matches:
        return storyboard
    output: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        output.append(storyboard[cursor : match.start()])
        next_start = float(matches[index + 1].group("start")) if index + 1 < len(matches) else None
        if dense_beat_score(match.group("screen")) >= 4:
            output.append("\n".join(split_dense_beat_line(match, next_start)))
        else:
            output.append(match.group(0))
        cursor = match.end()
    output.append(storyboard[cursor:])
    return "".join(output)


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:python|py)?\s*\n(?P<code>.*?)\n```", stripped, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group("code").strip()
    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def normalize_generated_text(text: str) -> str:
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return unicodedata.normalize("NFC", text)

    def repair_segment(segment: str) -> str:
        if not segment or not any(marker in segment for marker in MOJIBAKE_MARKERS):
            return segment
        try:
            repaired = segment.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return segment
        if sum(marker in repaired for marker in MOJIBAKE_MARKERS) < sum(marker in segment for marker in MOJIBAKE_MARKERS):
            return repaired
        return segment

    output: list[str] = []
    segment: list[str] = []
    for char in text:
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            output.append(repair_segment("".join(segment)))
            segment = []
            output.append(char)
        else:
            segment.append(char)
    output.append(repair_segment("".join(segment)))
    return unicodedata.normalize("NFC", "".join(output))


def beat_block_marker_pattern(beat_number: int) -> re.Pattern[str]:
    return re.compile(rf"(?ms)^[ \t]*#\s*---\s*Beat\s+{beat_number}\s+params\s*---\s*.*?(?=^[ \t]*#\s*---\s*Beat\s+\d+\s+params\s*---\s*$|\Z)")


def extract_beat_block(code: str, beat_number: int) -> str | None:
    match = beat_block_marker_pattern(beat_number).search(code)
    return match.group(0).rstrip() if match else None


def replace_beat_block(code: str, beat_number: int, replacement_block: str) -> str:
    pattern = beat_block_marker_pattern(beat_number)
    if not pattern.search(code):
        raise ValueError(f"Could not find Beat {beat_number} block in existing code.")
    if not re.search(rf"(?m)^[ \t]*#\s*---\s*Beat\s+{beat_number}\s+params\s*---\s*$", replacement_block):
        raise ValueError(f"Replacement block must include Beat {beat_number} params marker.")
    if not re.search(rf"(?m)^[ \t]*#\s*---\s*Beat\s+{beat_number}\s*---\s*$", replacement_block):
        raise ValueError(f"Replacement block must include Beat {beat_number} section marker.")
    return pattern.sub(replacement_block.rstrip() + "\n", code, count=1)


def render_scope_for_retry(beat_number: int | None) -> str:
    return "beat" if beat_number is not None else "full"


def codegen_model_for_attempt(provider: LLMProvider, attempt: int) -> str:
    if attempt == 1:
        return getattr(provider, "fast_model", provider.model)
    return provider.model


def parse_retry_after_seconds(retry_after: object) -> float:
    if retry_after is None:
        return RATE_LIMIT_DEFAULT_SLEEP_SECONDS
    if isinstance(retry_after, (int, float)):
        return max(0.0, float(retry_after))
    text = str(retry_after).strip()
    if not text:
        return RATE_LIMIT_DEFAULT_SLEEP_SECONDS
    try:
        return max(0.0, float(text))
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return RATE_LIMIT_DEFAULT_SLEEP_SECONDS
        now = datetime.now(timezone.utc)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - now).total_seconds())


def rate_limit_retry_after_seconds(exc: Exception) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "headers", None) or {}
    header_value = None
    if isinstance(headers, dict):
        header_value = headers.get("retry-after") or headers.get("Retry-After")
    else:
        getter = getattr(headers, "get", None)
        if callable(getter):
            header_value = getter("retry-after") or getter("Retry-After")
    if header_value is None:
        header_value = getattr(exc, "retry_after", None)
    return parse_retry_after_seconds(header_value)


def is_rate_limit_exception(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    code = getattr(exc, "code", None)
    if code == 429:
        return True
    message = str(exc).lower()
    return (
        "429" in message
        or "rate limit" in message
        or "too many requests" in message
        or "resource_exhausted" in message
        or "resource exhausted" in message
        or "quota" in message
    )


def beat_section_line_map(code: str) -> list[tuple[int, int, int]]:
    lines = code.splitlines()
    markers: list[tuple[int, int]] = []
    pattern = re.compile(r"^\s*#\s*---\s*Beat\s+(\d+)(?:\s+params)?\s*---\s*$")
    for idx, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if match:
            markers.append((int(match.group(1)), idx))
    sections: list[tuple[int, int, int]] = []
    for index, (beat_number, start_line) in enumerate(markers):
        end_line = markers[index + 1][1] - 1 if index + 1 < len(markers) else len(lines)
        sections.append((beat_number, start_line, end_line))
    return sections


def beat_number_from_traceback(code: str | None, feedback: str | None) -> int | None:
    if not code or not feedback:
        return None
    match = re.search(r"\bline\s+(\d+)\b", feedback, re.IGNORECASE)
    if not match:
        return None
    line_number = int(match.group(1))
    for beat_number, start_line, end_line in beat_section_line_map(code):
        if start_line <= line_number <= end_line:
            return beat_number
    return None


def write_generated_storyboard_audit(job_id: str, storyboard: str) -> None:
    audit_dir = WORK_ROOT / job_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "generated_storyboard.txt").write_text(storyboard, encoding="utf-8")


def reset_job_render_workspace(work_dir: Path, job_id: str | None = None) -> None:
    """Clear render artifacts while retaining topic-generation audit evidence."""
    if job_id is not None:
        validate_job_workspace(job_id, work_dir)
    preserved: dict[str, bytes] = {}
    if work_dir.exists():
        for pattern in ("generated_storyboard.txt", "storyboard_*"):
            for path in work_dir.glob(pattern):
                if path.is_file() and path.resolve().parent == work_dir.resolve():
                    preserved[path.name] = path.read_bytes()
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    for name, content in preserved.items():
        (work_dir / name).write_bytes(content)


def write_storyboard_response_audit(job_id: str | None, raw_text: str, normalized_text: str) -> None:
    if not job_id:
        return
    audit_dir = WORK_ROOT / job_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    raw_bytes = raw_text.encode("utf-8")
    (audit_dir / "storyboard_llm_raw_response_utf8.bin").write_bytes(raw_bytes)
    (audit_dir / "storyboard_llm_raw_response_utf8.hex").write_text(raw_bytes.hex(), encoding="utf-8")
    (audit_dir / "storyboard_llm_raw_response_text.txt").write_text(raw_text, encoding="utf-8")
    (audit_dir / "storyboard_llm_normalized_text.txt").write_text(normalized_text, encoding="utf-8")


STORYBOARD_INTEGRITY_RETRIES = max(1, int(os.getenv("STORYBOARD_INTEGRITY_RETRIES", "3")))
TOPIC_TERM_COVERAGE_THRESHOLD = min(
    1.0,
    max(0.0, float(os.getenv("TOPIC_TERM_COVERAGE_THRESHOLD", "0.70"))),
)
TOPIC_TERM_MAX_TERMS = max(3, int(os.getenv("TOPIC_TERM_MAX_TERMS", "12")))
GENERIC_SCAFFOLD_PATTERNS = (
    re.compile(r"\bknown information\b", re.IGNORECASE),
    re.compile(r"\btarget quantity\b", re.IGNORECASE),
    re.compile(r"\bcause[-\s]+and[-\s]+effect(?:\s+map)?\b", re.IGNORECASE),
    re.compile(r"\bidentify\s*,?\s*relate\s*,?\s*(?:and\s+)?solve\b", re.IGNORECASE),
    re.compile(r"\bsymbolic example\b", re.IGNORECASE),
    re.compile(r"\bthree[-\s]+step process\b", re.IGNORECASE),
)
TOPIC_TERM_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "demonstrate",
    "demonstrating",
    "degree",
    "degrees",
    "describe",
    "example",
    "examples",
    "explain",
    "explaining",
    "for",
    "from",
    "how",
    "illustrate",
    "illustrating",
    "in",
    "include",
    "including",
    "into",
    "lesson",
    "of",
    "on",
    "overview",
    "show",
    "showing",
    "the",
    "theory",
    "to",
    "using",
    "video",
    "with",
    "visually",
    "visual",
    "step",
    "steps",
    "step-by-step",
    "followed",
    "following",
    "overlay",
    "overlays",
    "overlaying",
    "add",
    "added",
    "adding",
    "transition",
    "transitions",
    "breathing",
    "window",
    "pacing",
    "cadence",
    "timing",
    "viewer",
    "student",
    "aspirant",
    "aspirants",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sharp",
    "smooth",
    "fluid",
    "perfect",
    "perfectly",
    "consistent",
    "new",
    "formula",
    "equation",
    "summation",
    "sequence",
    "complexity",
    "detail",
    "detailed",
    "approximates",
    "finally",
    "each",
    "mathematical",
    "update",
    "ensure",
    "between",
}
SCENE_NAME_META_WORDS = {
    "animation",
    "clearance",
    "draft",
    "final",
    "integrity",
    "precise",
    "regression",
    "render",
    "scene",
    "first",
    "second",
    "third",
    "test",
    "video",
}
TOPIC_TERM_TOKEN_PATTERN = re.compile(r"\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*")
TOPIC_TERM_SURFACE_ALIASES = {
    "ch4": ("methane",),
    "nh3": ("ammonia",),
    "greek": ("theta", "sigma", "pi", "θ", "Σ", "π"),
}


@dataclass(frozen=True)
class TopicTermCoverage:
    topic: str
    terms: tuple[str, ...]
    matched_terms: tuple[str, ...]
    missing_terms: tuple[str, ...]
    ratio: float
    required_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "terms": list(self.terms),
            "matched_terms": list(self.matched_terms),
            "missing_terms": list(self.missing_terms),
            "ratio": self.ratio,
            "required_count": self.required_count,
            "threshold": TOPIC_TERM_COVERAGE_THRESHOLD,
        }


def _is_symbolic_topic_token(token: str) -> bool:
    return token[0].isdigit() or any(character.isdigit() for character in token) or (
        len(token) >= 2 and token.isupper()
    )


def _append_unique_term(terms: list[str], term: str) -> None:
    normalized = term.casefold()
    if normalized and all(existing.casefold() != normalized for existing in terms):
        terms.append(term)


def extract_topic_key_terms(topic: str) -> list[str]:
    """Extract request-owned entities without maintaining per-domain vocabularies."""
    normalized_topic = unicodedata.normalize("NFKC", topic)
    terms: list[str] = []
    word_run: list[str] = []

    def flush_word_run() -> None:
        if not word_run:
            return
        if word_run[0][:1].isupper():
            _append_unique_term(terms, word_run[0])
            remainder = word_run[1:]
            if remainder:
                _append_unique_term(terms, " ".join(remainder[:3]))
        else:
            _append_unique_term(terms, " ".join(word_run[:3]))
        word_run.clear()

    previous_end = 0
    for token_match in TOPIC_TERM_TOKEN_PATTERN.finditer(normalized_topic):
        if re.search(r"[,;:/()]", normalized_topic[previous_end : token_match.start()]):
            flush_word_run()
        token = token_match.group(0)
        previous_end = token_match.end()
        lowered = token.casefold().strip("-' ")
        if not lowered or lowered in TOPIC_TERM_STOP_WORDS or re.fullmatch(r"v\d+", lowered):
            flush_word_run()
            continue
        if _is_symbolic_topic_token(token):
            flush_word_run()
            _append_unique_term(terms, token)
            continue
        if len(lowered) < 3:
            flush_word_run()
            continue
        word_run.append(token)
    flush_word_run()
    return terms[:TOPIC_TERM_MAX_TERMS]


def _term_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\\(?:mathrm|mathbf|text|operatorname)\s*", "", normalized)
    normalized = normalized.replace("_", "").replace("{", "").replace("}", "")
    return TOPIC_TERM_TOKEN_PATTERN.findall(normalized)


def _word_stem(value: str) -> str:
    word = value.casefold()
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def topic_term_is_present(term: str, content: str) -> bool:
    expected = _term_tokens(term)
    actual = _term_tokens(content)
    if not expected:
        return False
    expected_stems = [_word_stem(token) for token in expected]
    actual_stems = [_word_stem(token) for token in actual]
    compact_term = "".join(expected_stems)
    for alias in TOPIC_TERM_SURFACE_ALIASES.get(compact_term, ()):
        if _word_stem(alias) in actual_stems or alias.casefold() in content.casefold():
            return True
    width = len(expected_stems)
    return any(actual_stems[index : index + width] == expected_stems for index in range(len(actual_stems) - width + 1))


def topic_term_coverage(topic: str, storyboard: str) -> TopicTermCoverage:
    beats = parse_storyboard(storyboard)
    content = "\n".join(f"{beat.on_screen_text}\n{beat.vo_text or ''}" for beat in beats)
    terms = extract_topic_key_terms(topic)
    matched = [term for term in terms if topic_term_is_present(term, content)]
    missing = [term for term in terms if term not in matched]
    required_count = math.ceil(len(terms) * TOPIC_TERM_COVERAGE_THRESHOLD) if terms else 0
    ratio = len(matched) / len(terms) if terms else 1.0
    return TopicTermCoverage(
        topic=topic,
        terms=tuple(terms),
        matched_terms=tuple(matched),
        missing_terms=tuple(missing),
        ratio=ratio,
        required_count=required_count,
    )


def validate_early_topic_content(topic: str, beats: list[StoryboardBeat]) -> None:
    """Require concrete topic evidence in the opening beats of math/physics lessons."""
    if len(beats) < 3 or not MATH_PHYSICS_TOPIC_PATTERN.search(topic):
        return

    early_beats = beats[:4]
    early_content = "\n".join(
        f"{beat.on_screen_text}\n{beat.vo_text or ''}"
        for beat in early_beats
    )
    non_title_content = "\n".join(
        f"{beat.on_screen_text}\n{beat.vo_text or ''}"
        for beat in early_beats[1:]
    )
    terms = extract_topic_key_terms(topic)
    matched_after_title = [term for term in terms if topic_term_is_present(term, non_title_content)]
    has_symbolic_evidence = bool(EARLY_SYMBOLIC_EVIDENCE_PATTERN.search(early_content))

    if not matched_after_title and not has_symbolic_evidence:
        raise ValueError(
            "Storyboard integrity check rejected the opening beats: by Beat 4 a math/physics lesson must "
            "develop a topic-specific entity, named quantity, variable, or equation beyond merely repeating the title."
        )
    if EARLY_SYMBOL_REQUIRED_TOPIC_PATTERN.search(topic) and not has_symbolic_evidence:
        raise ValueError(
            "Storyboard integrity check rejected the opening beats: this derivation-oriented topic needs an actual "
            "equation or named symbolic quantity by Beat 4."
        )


def validate_vector_dot_product_storyboard(topic: str, beats: list[StoryboardBeat]) -> None:
    """Require the complete derivation for tetrahedral methane angle requests."""
    normalized_topic = topic.casefold()
    is_target = (
        ("methane" in normalized_topic or "ch4" in normalized_topic)
        and any(marker in normalized_topic for marker in ("vector", "dot product", "spatial coordinate"))
    )
    if not is_target:
        return

    content = "\n".join(f"{beat.on_screen_text}\n{beat.vo_text or ''}" for beat in beats)
    required_stages = {
        "coordinates": bool(re.search(r"coordinate|\(\s*[-+]?\d", content, re.IGNORECASE)),
        "vectors": bool(re.search(r"vector|\\vec|v[_₁₂]", content, re.IGNORECASE)),
        "dot_product": "dot product" in content.casefold() or "\\cdot" in content,
        "magnitudes": bool(re.search(r"magnitude|\\sqrt|\\lvert|\|v", content, re.IGNORECASE)),
        "final_angle": bool(re.search(r"arccos|109\.47|cos\s*theta.*-?1/3|\\theta.*-?1/3", content, re.IGNORECASE)),
    }
    missing = [name for name, present in required_stages.items() if not present]
    if len(beats) < 5 or missing:
        raise ValueError(
            "Storyboard integrity check rejected an incomplete methane vector-angle derivation: "
            f"requires at least five beats covering coordinates, vectors, dot product, magnitudes, and the final angle; "
            f"missing {', '.join(missing) or 'a complete beat sequence'}."
        )
    if re.search(r"\(\s*part\s+[a-z]\s*:\s*(?:introduce|add|remaining|first|next)", content, re.IGNORECASE):
        raise ValueError(
            "Storyboard integrity check rejected pagination instructions as visible content. "
            "Describe the mathematical object or equation directly in each beat."
        )


def storyboard_topic_hint(storyboard: str, scene_name: str = "") -> str:
    for line in storyboard.splitlines():
        match = re.match(r"^\s*#?\s*(?:topic|title)\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if match:
            return match.group(1)
    beats = parse_storyboard(storyboard)
    if beats:
        match = re.match(r"^\s*title\s*:\s*(.+?)\s*$", beats[0].on_screen_text, re.IGNORECASE)
        if match:
            return match.group(1)
    humanized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", scene_name)
    humanized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", humanized)
    humanized = re.sub(r"[_-]+", " ", humanized)
    words = [
        word
        for word in TOPIC_TERM_TOKEN_PATTERN.findall(humanized)
        if word.casefold() not in SCENE_NAME_META_WORDS and not re.fullmatch(r"v\d+", word, re.IGNORECASE)
    ]
    return " ".join(words)


def explanatory_word_count(value: str) -> int:
    prose = re.sub(r"`[^`]*`|\$[^$]*\$", " ", value)
    prose = re.sub(r"\\[A-Za-z]+", " ", prose)
    prose = re.sub(r"[A-Za-z0-9]+\s*(?:\^|_)[A-Za-z0-9{}()]*", " ", prose)
    prose = re.sub(r"[=+*/^_{}()]", " ", prose)
    return sum(
        1
        for word in re.findall(r"[A-Za-z]{2,}", prose.lower())
        if word not in EXPLANATION_STOP_WORDS
    )


def validate_generated_storyboard_integrity(topic: str, storyboard: str) -> TopicTermCoverage:
    """Reject scaffold leakage and drafts that omit the user's topic entities."""
    beats = parse_storyboard(storyboard)
    if not beats:
        raise ValueError("Storyboard integrity check could not find any beats.")

    for beat in beats:
        beat_text = f"{beat.on_screen_text}\n{beat.vo_text or ''}"
        for pattern in GENERIC_SCAFFOLD_PATTERNS:
            match = pattern.search(beat_text)
            if match:
                raise ValueError(
                    f"Storyboard integrity check rejected generic scaffold phrase {match.group(0)!r} in Beat {beat.index}."
                )
        duplicate = DUPLICATE_CONSECUTIVE_WORD_PATTERN.search(beat_text)
        if duplicate:
            raise ValueError(
                f"Storyboard integrity check rejected duplicate connector text {duplicate.group(0)!r} in Beat {beat.index}."
            )
        if MACLAURIN_ZERO_TYPO_PATTERN.search(beat_text):
            raise ValueError(
                f"Storyboard integrity check rejected a likely letter-o substitution for numeric zero in Beat {beat.index}."
            )
        math_complexity = len(MATH_COMPLEXITY_PATTERN.findall(beat_text))
        if math_complexity >= 2 and explanatory_word_count(beat_text) < 5:
            raise ValueError(
                f"Storyboard integrity check rejected Beat {beat.index}: dense mathematical content needs at least "
                "five words of topic-specific explanation."
            )

    normalized_topic_phrase = " ".join(token.casefold() for token in _term_tokens(topic))
    if normalized_topic_phrase and len(beats) >= 3:
        exact_topic_echoes = sum(
            normalized_topic_phrase
            in " ".join(
                token.casefold()
                for token in _term_tokens(f"{beat.on_screen_text} {beat.vo_text or ''}")
            )
            for beat in beats
        )
        echo_limit = max(3, math.ceil(len(beats) * 0.60))
        if exact_topic_echoes >= echo_limit:
            raise ValueError(
                "Storyboard integrity check rejected repeated full-topic echoing: "
                f"the request text appears verbatim in {exact_topic_echoes}/{len(beats)} beats. "
                "Develop the extracted entities and relationships instead of reusing the topic as placeholder content."
            )

    coverage = topic_term_coverage(topic, storyboard)
    if len(coverage.matched_terms) < coverage.required_count:
        matched = ", ".join(coverage.matched_terms) or "none"
        missing = ", ".join(coverage.missing_terms) or "none"
        raise ValueError(
            "Storyboard integrity check rejected insufficient topic-term coverage: "
            f"matched {len(coverage.matched_terms)}/{len(coverage.terms)} ({coverage.ratio:.0%}); "
            f"required at least {coverage.required_count}/{len(coverage.terms)} "
            f"({TOPIC_TERM_COVERAGE_THRESHOLD:.0%}). Matched: {matched}. Missing: {missing}."
        )
    validate_early_topic_content(topic, beats)
    validate_vector_dot_product_storyboard(topic, beats)
    return coverage


def write_storyboard_topic_coverage_audit(
    job_id: str | None,
    attempt: int,
    coverage: TopicTermCoverage,
) -> None:
    if not job_id:
        return
    audit_dir = WORK_ROOT / job_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    payload = {"attempt": attempt, **coverage.as_dict()}
    with (audit_dir / "storyboard_topic_coverage.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def write_storyboard_integrity_rejection(
    job_id: str | None,
    attempt: int,
    reason: str,
    storyboard: str,
    *,
    provider_name: str | None = None,
    model: str | None = None,
) -> None:
    if not job_id:
        return
    audit_dir = WORK_ROOT / job_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    with (audit_dir / "storyboard_integrity_rejections.log").open("a", encoding="utf-8") as log:
        log.write(
            f"attempt={attempt} provider={provider_name or 'unknown'} model={model or 'unknown'} "
            f"reason={reason}\n{storyboard}\n\n"
        )
    event = {
        "attempt": attempt,
        "provider": provider_name or "unknown",
        "model": model or "unknown",
        "reason": reason,
    }
    with (audit_dir / "storyboard_integrity_rejections.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def write_codegen_validation_rejection(
    job_id: str | None,
    *,
    render_attempt: int,
    validation_attempt: int,
    provider_name: str,
    model: str,
    reason: str,
    target_beat_number: int | None,
) -> None:
    if not job_id:
        return
    audit_dir = WORK_ROOT / job_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "render_attempt": render_attempt,
        "validation_attempt": validation_attempt,
        "provider": provider_name,
        "model": model,
        "target_beat_number": target_beat_number,
        "reason": reason,
    }
    with (audit_dir / "codegen_validation_rejections.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def build_local_storyboard_draft(topic: str, duration_seconds: int, audience: str) -> str:
    safe_topic = re.sub(r"\s+", " ", topic).strip().replace("|", "-").replace('"', "'")
    safe_audience = re.sub(r"\s+", " ", audience).strip().replace("|", "-").replace('"', "'")
    normalized_topic = safe_topic.lower()

    if (
        ("methane" in normalized_topic or "ch4" in normalized_topic)
        and any(marker in normalized_topic for marker in ("vector", "dot product", "spatial coordinate"))
    ):
        approach = "tetrahedral geometry, coordinate vectors, dot product, magnitudes, and the exact angle"
        content = [
            (
                "Title: CH4 tetrahedral geometry with two C-H bonds highlighted",
                "We calculate the exact value of the angle theta between any two C-H bonds. Methane places four hydrogen atoms at the vertices of a tetrahedron around central carbon.",
            ),
            (
                "Place C at (0,0,0), H1 at (1,1,1), and H2 at (1,-1,-1)",
                "Using spatial coordinates, choose two carbon-hydrogen bond endpoints with symmetric tetrahedral coordinates.",
            ),
            (
                "Define `\\vec{v}_1=\\langle1,1,1\\rangle` and `\\vec{v}_2=\\langle1,-1,-1\\rangle`",
                "The position vectors from carbon to the two hydrogen atoms are the two C-H bond vectors.",
            ),
            (
                "Compute `\\vec{v}_1\\cdot\\vec{v}_2=(1)(1)+(1)(-1)+(1)(-1)=-1`",
                "The vector dot product is related to the angle by v1 dot v2 equals the product of magnitudes times cos theta.",
            ),
            (
                "Show `|\\vec{v}_1|=|\\vec{v}_2|=\\sqrt{3}` and substitute to get `\\cos\\theta=-1/3`",
                "Both bond vectors have magnitude square root of three, so substitution gives cos theta equal to negative one third.",
            ),
            (
                "Display `\\theta=\\arccos(-1/3)\\approx109.47^\\circ`",
                "Therefore every pair of C-H bonds in tetrahedral methane makes an angle of approximately 109.47 degrees.",
            ),
        ]
    elif "vsepr" in normalized_topic or ("nh3" in normalized_topic and "ch4" in normalized_topic):
        approach = "compare CH4 tetrahedral bonding with NH3 trigonal-pyramidal bonding using electron-pair repulsion"
        content = [
            (
                "Title: VSEPR comparison of CH4 and NH3",
                "VSEPR predicts molecular geometry by arranging bonding pairs and lone pairs to reduce electron-pair repulsion.",
            ),
            (
                "Place a central atom and show electron domains spreading apart",
                "Electron domains around a central atom repel and adopt a geometry that keeps them separated.",
            ),
            (
                "Construct CH4 with C at the center and four H atoms using two planar bonds, one solid wedge, and one dashed bond",
                "Methane, CH4, has four bonding pairs around carbon and no lone pair on the central atom.",
            ),
            (
                "Add an angle arc labeled `109.5^\\circ` between two CH4 bonds",
                "Four equivalent bonding pairs produce a tetrahedral bond angle of 109.5 degrees.",
            ),
            (
                "Mark the four CH4 bonding pairs around C",
                "Each carbon-hydrogen bond occupies one electron domain, so all four directions are equivalent.",
            ),
            (
                "Construct NH3 with N at the center, three H atoms, and one distinct lone pair using wedge-dash bonds",
                "Ammonia, NH3, has three bonding pairs and one lone pair around nitrogen.",
            ),
            (
                "Add an angle arc labeled `107^\\circ` between two NH3 bonds",
                "The lone pair repels more strongly and compresses the hydrogen-nitrogen-hydrogen bond angle to 107 degrees.",
            ),
            (
                "Compare CH4 at 109.5 degrees with NH3 at 107 degrees",
                "CH4 is tetrahedral, while NH3 is trigonal pyramidal because one tetrahedral electron-domain position holds a lone pair.",
            ),
            (
                "Highlight the NH3 lone pair separately from its three bonding pairs",
                "Distinguishing lone pairs from bonding pairs explains why electron geometry and molecular geometry can differ.",
            ),
            (
                "Recap VSEPR: CH4 has four bonding pairs; NH3 has three bonding pairs and one lone pair",
                "Count every electron domain, arrange the domains, then name the molecular geometry from the atom positions.",
            ),
        ]
    elif "atwood" in normalized_topic:
        approach = "draw the two masses, write Newton's laws, eliminate tension, then interpret acceleration"
        content = [
            ("Title: Atwood machine", "An Atwood machine connects two masses, m1 and m2, over a light pulley."),
            ("Draw a pulley with m1 on the left and m2 on the right", "Assume m2 is larger, so m2 moves down while m1 moves up with acceleration a."),
            ("Label tension T and weight m1g, then write `T-m_1g=m_1a`", "For the rising mass m1, upward tension minus downward weight equals m1 times a."),
            ("Write `m_2g-T=m_2a` for the descending mass m2", "For m2, downward weight minus upward tension equals m2 times a."),
            ("Add the two equations so T cancels", "Adding the equations removes tension and leaves the net driving force."),
            ("Write `a=\\frac{(m_2-m_1)g}{m_1+m_2}`", "Acceleration depends on the mass difference divided by the total mass."),
            ("State that m2 greater than m1 makes m2 move downward", "The heavier side determines the direction of motion."),
            ("Write `T=\\frac{2m_1m_2g}{m_1+m_2}`", "Substitution gives the common string tension."),
            ("Compare equal masses m1=m2 with unequal masses", "Equal masses give zero acceleration; a larger mass difference increases acceleration."),
            ("Show the pulley, m1, m2, T, and a together", "The diagram and both Newton equations describe the complete system."),
            ("Recap the Atwood acceleration formula", "Write one equation for each mass, add them, and then solve for acceleration."),
        ]
    elif "taylor" in normalized_topic or "maclaurin" in normalized_topic:
        approach = "definition, coefficient pattern, worked sine expansion, then approximation limits"
        content = [
            (f"Title: {safe_topic}", f"Let us build {safe_topic} step by step for {safe_audience}."),
            ("A smooth curve is compared with a polynomial near x = a", "A Taylor polynomial approximates a smooth function near a chosen point a."),
            (
                "Write `f(x)=\\sum_{n=0}^{\\infty}\\frac{f^{(n)}(a)}{n!}(x-a)^n`",
                "Each coefficient comes from a derivative of the function evaluated at a.",
            ),
            ("Highlight the constant, linear, and quadratic terms one at a time", "The first terms match the value, slope, and curvature at the expansion point."),
            (
                "Set a = 0 and write `f(x)=\\sum_{n=0}^{\\infty}\\frac{f^{(n)}(0)}{n!}x^n` as the Maclaurin series",
                "Choosing a equal to numeral zero evaluates every derivative at zero and gives the Maclaurin form.",
            ),
            ("Show the derivative cycle of sin x", "For sine, repeated derivatives cycle through sine, cosine, negative sine, and negative cosine."),
            (
                "Write `\\sin x=x-\\frac{x^3}{3!}+\\frac{x^5}{5!}-\\cdots` term by term",
                "Substituting those derivative values produces the alternating odd-power series for sine.",
            ),
            ("Compare sin x with its first one, two, and three nonzero terms on axes", "Adding more terms improves the approximation near zero."),
            ("Shade the gap between the curve and a truncated polynomial", "The remaining gap is truncation error, which usually grows farther from the expansion point."),
            ("Show a checklist: choose a, compute derivatives, substitute, truncate", "The method is choose a point, compute derivatives, substitute the coefficients, and keep the required terms."),
            ("Show uses: limits, approximations, differential equations", "Taylor series turn difficult functions into polynomials that are easier to analyze."),
            ("Recap the series formula and the sine example", "Match derivatives at one point, then use the resulting polynomial within a suitable neighborhood."),
        ]
    else:
        approach = "state the topic, show its specific terms, connect its governing relationship, then recap"
        content = [
            (f"Title: {safe_topic}", f"Let us study {safe_topic} step by step for {safe_audience}."),
            (f"Define the central quantity or process in {safe_topic}", f"Name the physical or mathematical object that {safe_topic} studies."),
            (f"Label the specific terms used in {safe_topic}", "Keep each label attached to the object or expression it describes."),
            (f"Show the governing relationship for {safe_topic}", "Connect the named quantities using the relation required by this topic."),
            (f"Trace how one quantity changes in {safe_topic}", "Follow the direction, sign, or dependence that the topic requires."),
            (f"Apply the relationship to a concrete {safe_topic} setup", "Use the displayed terms consistently from the diagram to the result."),
            (f"Check the units and direction in {safe_topic}", "The result must match the dimensions and physical direction of the setup."),
            (f"Contrast two cases of {safe_topic}", "A changed condition reveals which quantity controls the outcome."),
            (f"Return to the main relation for {safe_topic}", "The relation connects every displayed term in the lesson."),
            (f"Recap the specific terms in {safe_topic}", "Keep the definition, relation, and interpretation together."),
            (f"Final view: {safe_topic}", "Use the topic's own entities and governing relationship in each problem."),
        ]

    if (
        ("methane" in normalized_topic or "ch4" in normalized_topic)
        and any(marker in normalized_topic for marker in ("vector", "dot product", "spatial coordinate"))
    ):
        beat_count = min(len(content), max(5, math.ceil(duration_seconds / 5)))
    else:
        beat_count = max(2, (duration_seconds + 7) // 8)
    lines = [f"# Approach: {approach}"]
    for index in range(beat_count):
        start = duration_seconds * index / beat_count
        end = duration_seconds * (index + 1) / beat_count
        on_screen, vo = content[index % len(content)]
        if index >= len(content):
            on_screen = f"Continue: {on_screen}"
        lines.append(f"[{start:g}-{end:g}] ON SCREEN: {on_screen} | VO: \"{vo}\"")
    return "\n".join(lines)


def extract_main_instance(storyboard: str) -> str:
    """Extract the first concrete storyboard beat used as the recall source."""
    for line in storyboard.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "ON SCREEN:" not in stripped:
            continue
        return stripped
    return storyboard.strip()


def recall_numeric_tokens(value: str) -> set[str]:
    return {token.rstrip(".") for token in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", value)}


def deterministic_recall_instance(main_instance: str, topic: str) -> dict[str, str]:
    """Keep local/provider-failure paths usable while guaranteeing a new numeric instance."""
    existing = recall_numeric_tokens(main_instance)
    first = 2
    while str(first) in existing:
        first += 1
    second = first + 2
    return {
        "instance_description": f"Apply {topic} to a new case using values {first} and {second}.",
        "solution_outline": f"Use the same method with {first} and {second}, then simplify the resulting relation.",
    }


def build_recall_question(topic: str, recall_instance: dict[str, str]) -> dict[str, str]:
    question_id = "recall-" + hashlib.sha256(
        f"{topic}|{recall_instance.get('instance_description', '')}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "question_id": question_id,
        "question": f"Apply the method to this new instance: {recall_instance.get('instance_description', '')}",
        "answer": recall_instance.get("solution_outline", "").strip(),
    }


def generate_recall_instance(
    *,
    provider: LLMProvider,
    topic: str,
    main_instance: str,
    model: str | None,
    db: Session | None,
    job_id: str | None,
    cost_breakdown: dict[str, Any],
) -> tuple[dict[str, str], float]:
    """Make the required second LLM call and assert its instance is numerically new."""
    from app.vivacity_prompts import build_in_video_recall_prompt

    system, user_message = build_in_video_recall_prompt(topic=topic, step1_example=main_instance)
    fallback = deterministic_recall_instance(main_instance, topic)
    try:
        response = provider.generate(system=system, user_message=user_message, max_tokens=1200, model=model)
    except Exception as exc:
        if not (isinstance(exc, ProviderUnavailableError) or isinstance(exc, StopIteration)):
            raise
        return fallback, 0.0

    actual_provider, actual_model = llm_response_identity(response, provider, model)
    event_cost = llm_cost_event(actual_provider, response.input_tokens, response.output_tokens, actual_model)
    if db is not None and job_id is not None:
        add_llm_cost(db, job_id, actual_provider, actual_model, response.input_tokens, response.output_tokens)
    provider_breakdown = cost_breakdown.setdefault(actual_provider, {})
    rates = llm_token_rates(actual_provider, actual_model)
    provider_breakdown["calls"] = int(provider_breakdown.get("calls", 0)) + 1
    provider_breakdown["input_tokens"] = int(provider_breakdown.get("input_tokens", 0)) + response.input_tokens
    provider_breakdown["output_tokens"] = int(provider_breakdown.get("output_tokens", 0)) + response.output_tokens
    provider_breakdown["cost_usd"] = float(provider_breakdown.get("cost_usd", 0.0)) + event_cost
    provider_breakdown["model"] = actual_model
    provider_breakdown["input_usd_per_million_tokens"] = rates["input"]
    provider_breakdown["output_usd_per_million_tokens"] = rates["output"]

    try:
        raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0) if match else raw)
        recall = {
            "instance_description": str(parsed["instance_description"]).strip(),
            "solution_outline": str(parsed["solution_outline"]).strip(),
        }
        main_numbers = recall_numeric_tokens(main_instance)
        recall_numbers = recall_numeric_tokens(recall["instance_description"] + " " + recall["solution_outline"])
        if not recall_numbers or recall_numbers == main_numbers:
            raise ValueError("Recall instance did not contain a distinct numeric set.")
        return recall, event_cost
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return fallback, event_cost


def generate_storyboard_draft(
    topic: str,
    duration_seconds: int,
    audience: str,
    db: Session | None = None,
    job_id: str | None = None,
    provider: LLMProvider | None = None,
    exam_context: str | None = None,
    student_signal: dict[str, Any] | None = None,
    assumed_prerequisites: list[str] | None = None,
) -> dict:
    topic = topic.strip()
    audience = audience.strip()
    if not topic:
        raise ValueError("Topic is required.")
    if not audience:
        raise ValueError("Audience is required.")
    if duration_seconds < 10 or duration_seconds > TOPIC_MAX_TARGET_SECONDS:
        raise ValueError(f"duration_seconds must be between 10 and {TOPIC_MAX_TARGET_SECONDS}.")

    # Load parameters from DB job request if present
    if db is not None and job_id is not None:
        job = db.get(Job, job_id)
        if job is not None and job.request_payload:
            payload = job.request_payload
            exam_context = exam_context or payload.get("exam_context")
            student_signal = student_signal or payload.get("student_signal")
            assumed_prerequisites = assumed_prerequisites or payload.get("assumed_prerequisites")

    # Resolve authored prerequisite data before the script-generation call.
    from app.prerequisite_gate import (
        StudentSignal,
        load_topic_prerequisites,
        resolve_prerequisite_gate,
        resolve_prerequisite_gate_result,
    )

    signal = StudentSignal.model_validate(
        student_signal
        or {"self_rated_confidence": 3, "flagged_as_weak_topic": False}
    )
    topic_prereqs = load_topic_prerequisites(topic)
    matched_prerequisites = resolve_prerequisite_gate(signal, topic_prereqs)
    # Keep the older assumed_prerequisites request field working for authored
    # clients while new clients use StudentSignal.unconfirmed_prerequisites.
    if not matched_prerequisites and assumed_prerequisites and not signal.unconfirmed_prerequisites:
        matched_prerequisites = list(assumed_prerequisites)
    gate_res = resolve_prerequisite_gate_result(
        topic=topic,
        exam_context=exam_context,
        audience=audience,
        flagged_as_weak_topic=signal.flagged_as_weak_topic,
        prior_attempt_count=signal.prior_attempt_count,
        self_rated_confidence=signal.self_rated_confidence,
        explicit_unconfirmed=matched_prerequisites,
    )

    provider = provider or get_llm_provider()
    required_topic_terms = extract_topic_key_terms(topic)
    required_topic_terms_text = ", ".join(required_topic_terms) or topic

    from app.vivacity_prompts import build_script_generation_system_prompt
    system = build_script_generation_system_prompt(
        topic=topic,
        exam_context=gate_res.exam_context,
        flagged_as_weak_topic=gate_res.flagged_as_weak_topic,
        unconfirmed_prerequisites=gate_res.unconfirmed_prerequisites,
    )
    base_user_msg = (
        f"Topic: {topic}\n"
        f"Required topic terms to preserve: {required_topic_terms_text}\n"
        f"Audience: {audience}\n"
        f"Target duration: {duration_seconds} seconds\n\n"
        "Draft the storyboard now. Keep math claims conservative and teachable."
    )
    active_model = codegen_model_for_attempt(provider, 1)
    max_output_tokens = min(MAX_TOKENS, 4000)
    cost_breakdown = empty_cost_breakdown()
    estimated_cost = 0.0
    user_msg = base_user_msg
    last_integrity_error: ValueError | None = None

    for draft_attempt in range(1, STORYBOARD_INTEGRITY_RETRIES + 1):
        if db is not None and job_id is not None:
            enforce_job_cost_budget(
                db,
                job_id,
                projected_llm_call_cost(provider.name, active_model, system, user_msg, max_output_tokens),
            )
        try:
            response = provider.generate(
                system=system,
                user_message=user_msg,
                max_tokens=max_output_tokens,
                model=active_model,
            )
        except Exception as exc:
            provider_unavailable = isinstance(exc, ProviderUnavailableError) or is_provider_capacity_exception(exc)
            if not ALLOW_LOCAL_STORYBOARD_FALLBACK or not provider_unavailable:
                raise
            text = paginate_dense_storyboard_beats(build_local_storyboard_draft(topic, duration_seconds, audience))
            validate_storyboard_or_raise(text, max_target_seconds=TOPIC_MAX_TARGET_SECONDS)
            try:
                coverage = validate_generated_storyboard_integrity(topic, text)
            except ValueError as fallback_exc:
                write_storyboard_integrity_rejection(
                    job_id,
                    draft_attempt,
                    str(fallback_exc),
                    text,
                    provider_name="local_fallback",
                    model="deterministic-storyboard-v1",
                )
                raise
            write_storyboard_topic_coverage_audit(job_id, draft_attempt, coverage)
            write_storyboard_response_audit(job_id, text, text)
            if job_id:
                audit_dir = WORK_ROOT / job_id
                audit_dir.mkdir(parents=True, exist_ok=True)
                (audit_dir / "storyboard_provider_fallback.log").write_text(
                    f"{type(exc).__name__}: {exc}",
                    encoding="utf-8",
                )
            if db is not None and job_id is not None:
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code,
                    progress_message="Building a topic-specific local storyboard while external generation capacity is unavailable.",
                    error=None,
                )
            main_instance = extract_main_instance(text)
            recall_instance = deterministic_recall_instance(main_instance, topic)
            return {
                "storyboard": text,
                "main_instance": main_instance,
                "recall_instance": recall_instance,
                "recall_question": build_recall_question(topic, recall_instance),
                "estimated_cost_usd": 0.0,
                "cost_breakdown": cost_breakdown,
            }

        raw_text = response.text.strip()
        text = paginate_dense_storyboard_beats(normalize_generated_text(raw_text))
        write_storyboard_response_audit(job_id, raw_text, text)
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        actual_provider, actual_model = llm_response_identity(response, provider, active_model)
        event_cost = llm_cost_event(actual_provider, input_tokens, output_tokens, actual_model)
        estimated_cost += event_cost
        if db is not None and job_id is not None:
            add_llm_cost(db, job_id, actual_provider, actual_model, input_tokens, output_tokens)
        provider_breakdown = cost_breakdown.setdefault(actual_provider, {})
        rates = llm_token_rates(actual_provider, actual_model)
        provider_breakdown["calls"] = int(provider_breakdown.get("calls", 0)) + 1
        provider_breakdown["input_tokens"] = int(provider_breakdown.get("input_tokens", 0)) + input_tokens
        provider_breakdown["output_tokens"] = int(provider_breakdown.get("output_tokens", 0)) + output_tokens
        provider_breakdown["cost_usd"] = float(provider_breakdown.get("cost_usd", 0.0)) + event_cost
        provider_breakdown["model"] = actual_model
        provider_breakdown["input_usd_per_million_tokens"] = rates["input"]
        provider_breakdown["output_usd_per_million_tokens"] = rates["output"]
        model_breakdown = provider_breakdown.setdefault("models", {}).setdefault(
            actual_model,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "input_usd_per_million_tokens": rates["input"], "output_usd_per_million_tokens": rates["output"]},
        )
        model_breakdown["calls"] += 1
        model_breakdown["input_tokens"] += input_tokens
        model_breakdown["output_tokens"] += output_tokens
        model_breakdown["cost_usd"] += event_cost

        try:
            validate_storyboard_or_raise(text, max_target_seconds=TOPIC_MAX_TARGET_SECONDS)
            coverage = validate_generated_storyboard_integrity(topic, text)
            write_storyboard_topic_coverage_audit(job_id, draft_attempt, coverage)
        except ValueError as exc:
            last_integrity_error = exc
            write_storyboard_integrity_rejection(
                job_id,
                draft_attempt,
                str(exc),
                text,
                provider_name=actual_provider,
                model=actual_model,
            )
            if draft_attempt >= STORYBOARD_INTEGRITY_RETRIES:
                vector_topic = (
                    ("methane" in topic.casefold() or "ch4" in topic.casefold())
                    and any(marker in topic.casefold() for marker in ("vector", "dot product", "spatial coordinate"))
                )
                if vector_topic:
                    local_text = paginate_dense_storyboard_beats(
                        build_local_storyboard_draft(topic, duration_seconds, audience)
                    )
                    validate_storyboard_or_raise(local_text, max_target_seconds=TOPIC_MAX_TARGET_SECONDS)
                    local_coverage = validate_generated_storyboard_integrity(topic, local_text)
                    write_storyboard_topic_coverage_audit(job_id, draft_attempt, local_coverage)
                    write_storyboard_response_audit(job_id, local_text, local_text)
                    if job_id:
                        audit_dir = WORK_ROOT / job_id
                        audit_dir.mkdir(parents=True, exist_ok=True)
                        (audit_dir / "storyboard_provider_fallback.log").write_text(
                            "deterministic vector-angle storyboard used after provider drafts failed integrity checks",
                            encoding="utf-8",
                        )
                    main_instance = extract_main_instance(local_text)
                    recall_instance = deterministic_recall_instance(main_instance, topic)
                    return {
                        "storyboard": local_text,
                        "main_instance": main_instance,
                        "recall_instance": recall_instance,
                        "recall_question": build_recall_question(topic, recall_instance),
                        "estimated_cost_usd": estimated_cost,
                        "cost_breakdown": cost_breakdown,
                    }
                raise ValueError(
                    f"Storyboard generation failed its content-integrity gate after {draft_attempt} attempts: {exc}"
                ) from exc
            user_msg = (
                f"{base_user_msg}\n\nYour previous storyboard was rejected before rendering: {exc}. "
                "Regenerate the entire storyboard with concrete topic-specific entities, variables, equations, and diagrams."
            )
            continue

        main_instance = extract_main_instance(text)
        recall_instance, recall_cost = generate_recall_instance(
            provider=provider,
            topic=topic,
            main_instance=main_instance,
            model=active_model,
            db=db,
            job_id=job_id,
            cost_breakdown=cost_breakdown,
        )
        estimated_cost += recall_cost
        return {
            "storyboard": text,
            "main_instance": main_instance,
            "recall_instance": recall_instance,
            "recall_question": build_recall_question(topic, recall_instance),
            "estimated_cost_usd": estimated_cost,
            "cost_breakdown": cost_breakdown,
        }

    raise RuntimeError(f"Storyboard integrity generation exhausted unexpectedly: {last_integrity_error}")


def minimum_text_reveal_runtime(value: str) -> float:
    return max(1.5, len(value) * 0.05)


def normalized_word_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", value.lower())


def rendered_spec_word_overlap(rendered_text: str, on_screen_spec: str) -> float:
    rendered_words = set(normalized_word_tokens(rendered_text))
    if not rendered_words:
        return 0.0
    spec_words = set(normalized_word_tokens(on_screen_spec))
    return len(rendered_words & spec_words) / len(rendered_words)


def validate_generated_python(
    code: str,
    storyboard: str | list[StoryboardBeat] | None = None,
) -> None:
    if not code.strip():
        raise SyntaxError("Generated response was empty.")
    tree = ast.parse(code)
    scene_class_names = scene_subclass_names_from_code(code)
    if len(scene_class_names) != 1:
        raise SyntaxError(
            "Generated code must define exactly one Manim Scene subclass; "
            f"found {len(scene_class_names)}: {scene_class_names}."
        )
    stage_direction = re.compile(
        r"^\s*(?:draw|label|show|illustrate|add|highlight|display|construct|place|mark|write)\b",
        re.IGNORECASE,
    )
    rendered_constructor_names = {"Text", "Tex", "MathTex", "fitted_text", "safe_math"}
    text_constructor_names = {"Text", "fitted_text"}
    latex_constructor_names = {"MathTex", "Tex", "safe_math"}
    numeric_assignments: dict[str, float] = {}
    rendered_assignments: dict[str, str] = {}
    rendered_group_members: dict[str, list[str]] = {}
    variable_aliases: dict[str, str] = {}
    rendered_assignment_locations: dict[str, tuple[int, int | None]] = {}
    rendered_call_locations: list[tuple[int, int | None, str]] = []
    overlap_checked_names: dict[int, set[str]] = {}
    invalid_overlap_checks: list[tuple[int, int | None, str]] = []
    reveal_calls_by_beat: dict[int, dict[str, list[tuple[int, str]]]] = {}
    play_calls_by_beat: dict[int, list[tuple[int, bool, tuple[str, ...]]]] = {}
    wait_calls_by_beat: dict[int, list[int]] = {}
    graph_title_clearance_names: dict[int, set[str]] = {}
    graph_title_next_to_names: dict[int, set[str]] = {}
    attached_label_pairs_by_beat: dict[int, list[tuple[str, str, int]]] = {}
    attached_transition_calls_by_beat: dict[int, list[tuple[int, set[str]]]] = {}
    function_definitions: dict[str, ast.FunctionDef] = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    safe_scale_call_count = 0
    rendered_literal_values: set[str] = set()
    beat_markers: list[tuple[int, int]] = []
    storyboard_beats = (
        parse_storyboard(storyboard)
        if isinstance(storyboard, str)
        else list(storyboard or [])
    )
    storyboard_by_number = {beat.index: beat for beat in storyboard_beats}

    for line_number, line in enumerate(code.splitlines(), start=1):
        marker = re.match(r"^\s*#\s*---\s*Beat\s+(\d+)\s*---\s*$", line)
        if marker:
            beat_markers.append((line_number, int(marker.group(1))))

    def beat_number_for_line(line_number: int) -> int | None:
        current: int | None = None
        for marker_line, beat_number in beat_markers:
            if marker_line > line_number:
                break
            current = beat_number
        return current

    def function_name(call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            return call.func.id
        return call.func.attr if isinstance(call.func, ast.Attribute) else None

    def rendered_constructor_from_expression(node: ast.AST) -> ast.Call | None:
        if isinstance(node, ast.Call):
            if function_name(node) in rendered_constructor_names:
                return node
            if isinstance(node.func, ast.Attribute):
                return rendered_constructor_from_expression(node.func.value)
        if isinstance(node, ast.Attribute):
            return rendered_constructor_from_expression(node.value)
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
            numeric_assignments[target_name] = float(node.value.value)
        if isinstance(node.value, ast.Call) and function_name(node.value) in {"VGroup", "Group"}:
            rendered_group_members[target_name] = [
                argument.id for argument in node.value.args if isinstance(argument, ast.Name)
            ]
        elif isinstance(node.value, ast.Name):
            variable_aliases[target_name] = node.value.id
        elif isinstance(node.value, ast.Subscript) and isinstance(node.value.value, ast.Name):
            variable_aliases[target_name] = node.value.value.id
        constructor = rendered_constructor_from_expression(node.value)
        direct_literals = (
            [
                argument.value
                for argument in constructor.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            ]
            if constructor is not None
            else []
        )
        nested_literals = [
            argument.value
            for candidate in ast.walk(node.value)
            if isinstance(candidate, ast.Call) and function_name(candidate) in rendered_constructor_names
            for argument in candidate.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        ]
        if nested_literals:
            rendered_assignments[target_name] = max(nested_literals, key=len)
        if direct_literals:
            rendered_assignment_locations[target_name] = (node.lineno, beat_number_for_line(node.lineno))

    for _ in range(len(rendered_group_members) + 1):
        changed = False
        for group_name, member_names in rendered_group_members.items():
            member_texts = [rendered_assignments[name] for name in member_names if name in rendered_assignments]
            if member_texts and group_name not in rendered_assignments:
                rendered_assignments[group_name] = max(member_texts, key=len)
                changed = True
        if not changed:
            break

    def numeric_value(node: ast.AST | None) -> float | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            return numeric_assignments.get(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = numeric_value(node.operand)
            if operand is None:
                return None
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BinOp):
            left = numeric_value(node.left)
            right = numeric_value(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div) and right != 0:
                return left / right
        return None

    def literal_text_from_animation_target(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Name):
            return rendered_assignments.get(node.id)
        if isinstance(node, ast.Call) and function_name(node) in rendered_constructor_names:
            return next(
                (
                    argument.value
                    for argument in node.args
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                ),
                None,
            )
        return None

    def transitive_group_members(group_name: str) -> set[str]:
        """Resolve VGroup membership and simple aliases for lifecycle checks."""
        resolved: set[str] = set()
        pending = [group_name]
        while pending:
            current = pending.pop()
            if current in resolved:
                continue
            resolved.add(current)
            pending.extend(rendered_group_members.get(current, []))
            pending.extend(
                alias_name
                for alias_name, source_name in variable_aliases.items()
                if source_name == current
            )
        return resolved

    def common_enclosing_group(label_name: str, target_name: str, names: set[str]) -> bool:
        return any(
            group_name in names
            and label_name in transitive_group_members(group_name)
            and target_name in transitive_group_members(group_name)
            for group_name in rendered_group_members
        )

    def unbalanced_math_delimiter(value: str) -> str | None:
        opening_to_closing = {"{": "}", "(": ")"}
        closing_to_opening = {closing: opening for opening, closing in opening_to_closing.items()}
        stack: list[tuple[str, int]] = []

        for index, character in enumerate(value):
            if character not in opening_to_closing and character not in closing_to_opening:
                continue

            preceding_backslashes = 0
            cursor = index - 1
            while cursor >= 0 and value[cursor] == "\\":
                preceding_backslashes += 1
                cursor -= 1
            if preceding_backslashes % 2 == 1:
                continue

            if character in opening_to_closing:
                stack.append((character, index))
                continue

            expected_opening = closing_to_opening[character]
            if not stack or stack[-1][0] != expected_opening:
                return f"unmatched {character!r} at character {index + 1}"
            stack.pop()

        if stack:
            opening, index = stack[-1]
            return f"unmatched {opening!r} at character {index + 1}"
        return None

    class GeneratedCodeVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.current_function: str | None = None

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            previous = self.current_function
            self.current_function = node.name
            self.generic_visit(node)
            self.current_function = previous

        def visit_Call(self, node: ast.Call) -> None:
            nonlocal safe_scale_call_count
            for keyword in node.keywords:
                if keyword.arg == "font_family":
                    raise SyntaxError(
                        "Generated code used unsupported Manim keyword font_family. "
                        "Use font_size for MathTex/Tex, and use Text(..., font='...') only when a text font is required."
                    )

            call_name = function_name(node)
            if call_name == "safe_scale":
                safe_scale_call_count += 1
            if call_name == "place_graph_title" and node.args and isinstance(node.args[0], ast.Name):
                beat_number = beat_number_for_line(node.lineno)
                if beat_number is not None:
                    graph_title_clearance_names.setdefault(beat_number, set()).add(node.args[0].id)
            is_next_to = isinstance(node.func, ast.Attribute) and node.func.attr == "next_to"
            if is_next_to and isinstance(node.func.value, ast.Name) and len(node.args) >= 2:
                target = node.args[0]
                if isinstance(target, ast.Name):
                    beat_number = beat_number_for_line(node.lineno)
                    if beat_number is not None:
                        receiver_name = node.func.value.id
                        attached_label_pairs_by_beat.setdefault(beat_number, []).append(
                            (receiver_name, target.id, node.lineno)
                        )
                direction = node.args[1]
                buff_value = numeric_value(
                    next((keyword.value for keyword in node.keywords if keyword.arg == "buff"), None)
                )
                if isinstance(direction, ast.Name) and direction.id == "UP" and buff_value is not None and buff_value >= 0.4:
                    beat_number = beat_number_for_line(node.lineno)
                    if beat_number is not None:
                        graph_title_next_to_names.setdefault(beat_number, set()).add(node.func.value.id)
            rendered_text_type = call_name in rendered_constructor_names
            if rendered_text_type:
                rendered_call_locations.append((node.lineno, beat_number_for_line(node.lineno), call_name or "text"))
                candidate = node.args[0] if node.args else next(
                    (keyword.value for keyword in node.keywords if keyword.arg in {"text", "value"}),
                    None,
                )
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                    rendered_literal_values.add(candidate.value.strip().casefold())
                    malformed_math = MALFORMED_MATH_CAPTION_PATTERN.search(candidate.value)
                    if malformed_math:
                        raise SyntaxError(
                            f"Line {node.lineno} renders malformed math caption text containing "
                            f"{malformed_math.group(0)!r}. Put the complete expression in MathTex(r\"...\") "
                            "and use a short prose heading separately."
                        )
                    match = STRICT_TEXT_MATH_PATTERN.search(candidate.value) if call_name in text_constructor_names else None
                    if match is not None:
                        constructor_label = "Text() with LaTeX syntax" if call_name == "Text" else f"{call_name}() with math syntax"
                        raise SyntaxError(
                            f"Line {node.lineno} uses {constructor_label} ({match.group(0)!r}). "
                            "Use MathTex(r\"...\") for this expression."
                        )
                    if stage_direction.match(candidate.value):
                        raise SyntaxError(
                            f"Line {node.lineno} renders an imperative construction instruction with {call_name}(): "
                            f"{candidate.value!r}. Construct the described Manim objects instead of displaying the instruction."
                        )
                    beat_number = beat_number_for_line(node.lineno)
                    beat = storyboard_by_number.get(beat_number) if beat_number is not None else None
                    word_count = len(normalized_word_tokens(candidate.value))
                    normalized_candidate = " ".join(normalized_word_tokens(candidate.value))
                    normalized_spec = " ".join(normalized_word_tokens(beat.on_screen_text)) if beat is not None else ""
                    is_plain_caption = call_name in {"Text", "Tex", "fitted_text"} or not re.search(
                        r"[\\=^_{}]", candidate.value
                    )
                    if normalized_candidate and normalized_candidate == normalized_spec and is_plain_caption:
                        raise SyntaxError(
                            f"Beat {beat_number} line {node.lineno} copies its operational ON SCREEN spec verbatim "
                            f"into {call_name}() (100% word overlap). Construct the requested visual and author a "
                            "separate short label."
                        )
                    if beat is not None and word_count > 8 and is_plain_caption:
                        overlap_ratio = rendered_spec_word_overlap(candidate.value, beat.on_screen_text)
                        if overlap_ratio > 0.60:
                            raise SyntaxError(
                                f"Beat {beat_number} line {node.lineno} copies its operational ON SCREEN spec into "
                                f"{call_name}() as a {word_count}-word caption ({overlap_ratio:.0%} word overlap). "
                                "Construct the described visual and use only a separately authored short label."
                            )

            literal_arguments = [
                argument.value
                for argument in node.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            ]
            if call_name in rendered_constructor_names:
                for literal in literal_arguments:
                    duplicate = DUPLICATE_CONSECUTIVE_WORD_PATTERN.search(literal)
                    if duplicate:
                        raise SyntaxError(
                            f"Line {node.lineno} renders duplicate connector text {duplicate.group(0)!r}. "
                            "Replace it with complete topic-specific content."
                        )

            is_latex_mobject = call_name in latex_constructor_names
            if is_latex_mobject:
                literal_arguments.extend(
                    keyword.value.value
                    for keyword in node.keywords
                    if keyword.arg in {"tex_string", "text", "value"}
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                )
                for literal in literal_arguments:
                    bare_command = BARE_LATEX_COMMAND_PATTERN.search(literal)
                    if bare_command:
                        raise SyntaxError(
                            f"Line {node.lineno} sends an unescaped LaTeX command "
                            f"({bare_command.group(0)!r}) to {call_name}(). Use a complete backslash command "
                            "such as \\int, \\pi, or \\cos before rendering."
                        )
                    if INTEGRAL_BOUND_LETTER_O_PATTERN.search(literal):
                        raise SyntaxError(
                            f"Line {node.lineno} uses the letter o as an integral bound (found: {literal!r}). "
                            "Use the numeral 0 before rendering."
                        )
                    if MACLAURIN_ZERO_TYPO_PATTERN.search(literal):
                        raise SyntaxError(
                            f"Line {node.lineno} appears to use the letter o where the Maclaurin center requires "
                            f"the numeral 0 (found: {literal!r})."
                        )
                    delimiter_error = unbalanced_math_delimiter(literal)
                    if delimiter_error:
                        raise SyntaxError(
                            "Your previous response was truncated mid-string, resulting in incomplete LaTeX "
                            f"on line {node.lineno} ({delimiter_error}; found: {literal!r}). Ensure your response "
                            "completes fully within the token budget; if a string is very long, use a shorter "
                            "equivalent form."
                        )

            is_self_play = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "play"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            )
            if is_self_play:
                beat_number = beat_number_for_line(node.lineno)
                animation_calls = [argument for argument in node.args if isinstance(argument, ast.Call)]
                only_fadeouts = bool(animation_calls) and len(animation_calls) == len(node.args) and all(
                    function_name(animation) == "FadeOut" for animation in animation_calls
                )
                fadeout_targets = tuple(
                    animation.args[0].id
                    for animation in animation_calls
                    if function_name(animation) == "FadeOut"
                    and animation.args
                    and isinstance(animation.args[0], ast.Name)
                )
                if beat_number is not None:
                    play_calls_by_beat.setdefault(beat_number, []).append(
                        (node.lineno, only_fadeouts, fadeout_targets)
                    )
                    transition_names = {"FadeOut", "Create", "Transform", "ReplacementTransform"}
                    transitioned_names: set[str] = set()
                    for animation in ast.walk(node):
                        if not isinstance(animation, ast.Call) or function_name(animation) not in transition_names:
                            continue
                        for target_node in animation.args:
                            for name_node in ast.walk(target_node):
                                if isinstance(name_node, ast.Name):
                                    transitioned_names.add(name_node.id)
                    if transitioned_names:
                        attached_transition_calls_by_beat.setdefault(beat_number, []).append(
                            (node.lineno, transitioned_names)
                        )

                play_runtime = numeric_value(
                    next((keyword.value for keyword in node.keywords if keyword.arg == "run_time"), None)
                )
                for argument in node.args:
                    for animation in ast.walk(argument):
                        if not isinstance(animation, ast.Call) or function_name(animation) not in {"Write", "Create"}:
                            continue
                        target_text = literal_text_from_animation_target(animation.args[0] if animation.args else None)
                        if target_text is None:
                            continue
                        animation_runtime = numeric_value(
                            next((keyword.value for keyword in animation.keywords if keyword.arg == "run_time"), None)
                        )
                        effective_runtime = play_runtime if play_runtime is not None else animation_runtime
                        required_runtime = minimum_text_reveal_runtime(target_text)
                        beat_label = f"Beat {beat_number} " if beat_number is not None else ""
                        if effective_runtime is None:
                            raise SyntaxError(
                                f"{beat_label}line {node.lineno} animates {target_text!r} with {function_name(animation)}() "
                                f"without an explicit run_time. Use at least {required_runtime:.2f}s or use FadeIn()."
                            )
                        if effective_runtime + 1e-6 < required_runtime:
                            raise SyntaxError(
                                f"{beat_label}line {node.lineno} gives {function_name(animation)}({target_text!r}) "
                                f"only {effective_runtime:.2f}s; use at least {required_runtime:.2f}s (0.05s per character, "
                                "1.5s minimum) or use FadeIn() when the beat is too short."
                            )

            if call_name == "avoid_overlap" and node.args and isinstance(node.args[0], ast.Name):
                beat_number = beat_number_for_line(node.lineno)
                has_obstacle_source = len(node.args) >= 2 and not (
                    isinstance(node.args[1], (ast.List, ast.Tuple)) and not node.args[1].elts
                )
                if beat_number is not None and has_obstacle_source:
                    overlap_checked_names.setdefault(beat_number, set()).add(node.args[0].id)
                elif beat_number is not None:
                    invalid_overlap_checks.append((node.lineno, beat_number, node.args[0].id))

            if call_name in {"Write", "Create", "FadeIn", "GrowFromCenter"} and node.args:
                target = node.args[0]
                if isinstance(target, ast.Name):
                    beat_number = beat_number_for_line(node.lineno)
                    if beat_number is not None:
                        reveal_calls_by_beat.setdefault(beat_number, {}).setdefault(target.id, []).append(
                            (node.lineno, call_name)
                        )

            is_self_wait = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            )
            if is_self_wait:
                beat_number = beat_number_for_line(node.lineno)
                if beat_number is not None:
                    wait_calls_by_beat.setdefault(beat_number, []).append(node.lineno)

            is_animated_scale = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "scale"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "animate"
            )
            if is_animated_scale and self.current_function != "safe_scale":
                raise SyntaxError(
                    f"Line {node.lineno} calls .animate.scale() directly. "
                    "Use safe_scale(mobj, factor) so emphasis animations stay inside the frame."
                )
            self.generic_visit(node)

    GeneratedCodeVisitor().visit(tree)
    leaked_debug_controls = sorted(DEBUG_BUTTON_LABELS & rendered_literal_values)
    if leaked_debug_controls:
        raise SyntaxError(
            "Generated scene contains prohibited debug-button / interactive test-control label(s): "
            + ", ".join(leaked_debug_controls)
            + ". Remove UI controls from renderable Manim content."
        )
    for beat_number, attached_pairs in attached_label_pairs_by_beat.items():
        for label_name, target_name, line_number in attached_pairs:
            # Graph titles are positioned relative to axes for numeric
            # clearance, but they are not annotations owned by the axes. A
            # continuity handoff may intentionally fade the title while the
            # graph remains on screen for the next beat.
            if label_name in graph_title_clearance_names.get(beat_number, set()):
                continue
            for transition_line, transitioned_names in attached_transition_calls_by_beat.get(beat_number, []):
                if not ({label_name, target_name} & transitioned_names):
                    continue
                if common_enclosing_group(label_name, target_name, transitioned_names):
                    continue
                raise SyntaxError(
                    f"Beat {beat_number} line {line_number} attaches {label_name!r} to {target_name!r} with "
                    f"next_to(), but transition line {transition_line} does not animate a shared VGroup. "
                    "Place the label and its diagram parent in one VGroup and animate that group together."
                )
    if safe_scale_call_count and "safe_scale" not in function_definitions:
        raise SyntaxError("Generated code calls safe_scale() without defining the frame-clamping helper.")
    if graph_title_clearance_names:
        helper = function_definitions.get("place_graph_title")
        helper_source = ast.unparse(helper) if helper is not None else ""
        required_fragments = ("next_to", "get_bottom", "x_axis", "get_center")
        helper_constants = (
            {
                float(node.value)
                for node in ast.walk(helper)
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            }
            if helper is not None
            else set()
        )
        if helper is None or any(fragment not in helper_source for fragment in required_fragments) or not (
            any(value >= 0.4 for value in helper_constants) and any(value >= 0.3 for value in helper_constants)
        ):
            raise SyntaxError(
                "place_graph_title() must position titles above axes with at least 0.4 units of buffer and verify "
                "title.get_bottom()[1] is at least 0.3 units above the x-axis."
            )
    ordered_beats = [beat_number for _, beat_number in beat_markers]
    for beat_number in ordered_beats[:-1]:
        beat_play_calls = play_calls_by_beat.get(beat_number, [])
        for play_index, (line_number, only_fadeouts, fadeout_targets) in enumerate(beat_play_calls):
            if not only_fadeouts:
                continue
            is_final_play = play_index == len(beat_play_calls) - 1
            removes_primary_visual = any(
                re.search(r"(?:diagram|visual|graph|axes|curve|scene|group)", target, re.IGNORECASE)
                for target in fadeout_targets
            )
            if not is_final_play and not removes_primary_visual:
                continue
            next_play_line = (
                beat_play_calls[play_index + 1][0]
                if play_index + 1 < len(beat_play_calls)
                else None
            )
            waits_after_fade = [
                wait_line
                for wait_line in wait_calls_by_beat.get(beat_number, [])
                if wait_line > line_number
                and (next_play_line is None or wait_line < next_play_line)
            ]
            if waits_after_fade:
                raise SyntaxError(
                    f"Beat {beat_number} removes all visible content on line {line_number}, then waits on line "
                    f"{waits_after_fade[0]}, leaving a blank frame. Start the next beat immediately after the FadeOut."
                )
    if storyboard_by_number:
        for beat_number, beat in storyboard_by_number.items():
            if not GRAPH_CONTENT_PATTERN.search(beat.on_screen_text):
                continue
            section = code_section_for_beat(code, beat_number)
            # Coordinate axes in a vector/dot-product diagram are not an
            # Axes graph. Apply the title clearance contract only when this
            # beat actually constructs a graph axes object or uses the graph
            # title helper.
            has_graph_visual = (
                re.search(rf"\\bbeat{beat_number}_axes\\s*=", section) is not None
                or "place_graph_title(" in section
            )
            if not has_graph_visual:
                continue
            title_names = {
                name
                for name, (_, assigned_beat_number) in rendered_assignment_locations.items()
                if assigned_beat_number == beat_number and GRAPH_TITLE_NAME_PATTERN.search(name)
            }
            for title_name in title_names:
                if title_name in graph_title_clearance_names.get(beat_number, set()):
                    continue
                has_inline_numeric_check = (
                    title_name in graph_title_next_to_names.get(beat_number, set())
                    and f"{title_name}.get_bottom()[1]" in section
                    and ".x_axis.get_center()[1]" in section
                    and re.search(r"\+\s*0\.3(?:0+)?\b", section) is not None
                )
                if not has_inline_numeric_check:
                    raise SyntaxError(
                        f"Beat {beat_number} graph title {title_name!r} lacks the numeric axis-clearance contract. "
                        "Call place_graph_title(title, axes), or use next_to(axes, UP, buff>=0.4) and verify the "
                        "title bottom remains more than 0.3 units above the x-axis."
                    )
        if invalid_overlap_checks:
            line_number, beat_number, name = invalid_overlap_checks[0]
            raise SyntaxError(
                f"Beat {beat_number} line {line_number} calls avoid_overlap({name}, ...) without a beat-local "
                "obstacle collection. Pass the collection containing every existing visible mobject, including "
                "the current graph or diagram."
            )
        assigned_text_locations = {
            (line_number, beat_number)
            for line_number, beat_number in rendered_assignment_locations.values()
        }
        for line_number, beat_number, constructor_name in rendered_call_locations:
            if beat_number is None or beat_number not in storyboard_by_number:
                continue
            if (line_number, beat_number) not in assigned_text_locations:
                raise SyntaxError(
                    f"Beat {beat_number} line {line_number} creates {constructor_name}() inline. Assign every rendered "
                    "text or equation mobject to a named variable, then call avoid_overlap() on that variable before "
                    "animation."
                )
        for name, (line_number, beat_number) in rendered_assignment_locations.items():
            if beat_number is None or beat_number not in storyboard_by_number:
                continue
            if name not in overlap_checked_names.get(beat_number, set()):
                raise SyntaxError(
                    f"Beat {beat_number} line {line_number} creates text mobject {name!r} without calling "
                    f"avoid_overlap({name}, ...). Check it against every existing visible mobject, including "
                    "axes, curves, diagrams, arrows, equations, and earlier text, before animation."
                )
        seen_rendered_content: dict[tuple[int, str], tuple[str, int]] = {}
        for name, (line_number, beat_number) in rendered_assignment_locations.items():
            if beat_number is None or beat_number not in storyboard_by_number:
                continue
            literal = rendered_assignments.get(name, "")
            normalized_literal = re.sub(r"\s+", "", literal).lower()
            if len(normalized_literal) < 12:
                continue
            key = (beat_number, normalized_literal)
            previous = seen_rendered_content.get(key)
            if previous is not None:
                previous_name, previous_line = previous
                raise SyntaxError(
                    f"Beat {beat_number} recreates the same substantial on-screen content as {previous_name!r} "
                    f"(lines {previous_line} and {line_number}, variables {previous_name!r} and {name!r}). Build one "
                    "mobject and animate it through one continuous reveal sequence."
                )
            seen_rendered_content[key] = (name, line_number)
    for beat_number, targets in reveal_calls_by_beat.items():
        for target_name, calls in targets.items():
            if len(calls) <= 1:
                continue
            call_description = ", ".join(f"{animation} line {line}" for line, animation in calls)
            raise SyntaxError(
                f"Beat {beat_number} reveals mobject {target_name!r} more than once ({call_description}). Use one "
                "continuous creation animation instead of resetting or recreating it."
            )
    if "def avoid_overlap(" not in code:
        raise SyntaxError("Generated code must include the required avoid_overlap(mobj, others, min_gap=0.3) helper.")
    if not re.search(r"\.scale_to_fit_height\(\s*config\.frame_height\s*\*\s*0\.55\s*\)", code):
        raise SyntaxError("Generated code must scale each beat's main diagram VGroup to config.frame_height * 0.55.")
    if not re.search(r"\.move_to\(\s*ORIGIN\s*\)", code):
        raise SyntaxError("Generated code must center each beat's main diagram VGroup at ORIGIN before animation.")
    if re.search(r"\b(?:ReplacementTransform|Transform)\s*\([^,\n]+\.copy\(\)\s*,", code):
        raise SyntaxError(
            "Generated code must not Transform or ReplacementTransform a copied equation into the next equation. "
            "Transform the existing on-screen mobject, or FadeOut it before writing the replacement."
        )
    for color_name in PROHIBITED_MANIM_COLOR_NAMES:
        if re.search(rf"\b{re.escape(color_name)}\b", code):
            raise SyntaxError(
                f"Generated code used unsupported Manim color constant {color_name}. "
                "Use the approved color whitelist, interpolate_color(), or a hex string."
            )


def run_command(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
        timeout=timeout_seconds,
    )


def subprocess_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def generate_silence(duration: float, out_path: Path) -> None:
    duration = max(0.05, duration)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=44100",
            "-t",
            f"{duration:.3f}",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(out_path),
        ]
    )


def _tts_cache_path(text: str, model: str, voice: str, speed: float) -> Path:
    canonical = json.dumps(
        {
            "provider": "openai",
            "model": model,
            "voice": voice,
            "speed": speed,
            "text": unicodedata.normalize("NFC", text),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return TTS_CACHE_DIR / f"{hashlib.sha256(canonical).hexdigest()}.mp3"


def _valid_cached_audio(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _acquire_tts_cache_lock(cache_path: Path) -> tuple[bool, Path]:
    lock_path = cache_path.with_suffix(".lock")
    deadline = time.monotonic() + TTS_CACHE_WAIT_SECONDS
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(descriptor, f"pid={os.getpid()} created={time.time()}".encode("ascii"))
            finally:
                os.close(descriptor)
            return True, lock_path
        except FileExistsError:
            if _valid_cached_audio(cache_path):
                return False, lock_path
            try:
                stale = time.time() - lock_path.stat().st_mtime > TTS_CACHE_STALE_LOCK_SECONDS
            except FileNotFoundError:
                stale = False
            if stale:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                return False, lock_path
            time.sleep(0.2)


def _synthesize_openai_tts(text: str, out_path: Path, model: str, voice: str, speed: float) -> None:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI SDK is not installed. Run: pip install openai") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
    ) as response:
        response.stream_to_file(out_path)


def generate_tts_audio(
    text: str,
    out_path: Path,
    db: Session | None = None,
    job_id: str | None = None,
    model: str | None = None,
    voice: str | None = None,
    speed: float | None = None,
) -> None:
    model = model or OPENAI_TTS_MODEL
    voice = voice or OPENAI_TTS_VOICE
    speed = OPENAI_TTS_SPEED if speed is None else min(4.0, max(0.25, speed))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path = _tts_cache_path(text, model, voice, speed)

    if TTS_CACHE_ENABLED:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if _valid_cached_audio(cache_path):
            shutil.copy2(cache_path, out_path)
            record_openai_tts_cache_hit(db, job_id)
            return

        acquired, lock_path = _acquire_tts_cache_lock(cache_path)
        if not acquired and _valid_cached_audio(cache_path):
            shutil.copy2(cache_path, out_path)
            record_openai_tts_cache_hit(db, job_id)
            return
        if acquired:
            temp_path = cache_path.with_name(f"{cache_path.stem}.{uuid.uuid4().hex}.mp3")
            try:
                if db is not None and job_id is not None:
                    enforce_job_cost_budget(
                        db,
                        job_id,
                        (len(text) / 1_000_000) * tts_rate_for_model(model),
                    )
                _synthesize_openai_tts(text, temp_path, model, voice, speed)
                os.replace(temp_path, cache_path)
                shutil.copy2(cache_path, out_path)
                if db is not None and job_id is not None:
                    add_openai_tts_cost(db, job_id, model, len(text))
                return
            finally:
                temp_path.unlink(missing_ok=True)
                lock_path.unlink(missing_ok=True)

    if db is not None and job_id is not None:
        enforce_job_cost_budget(
            db,
            job_id,
            (len(text) / 1_000_000) * tts_rate_for_model(model),
        )
    _synthesize_openai_tts(text, out_path, model, voice, speed)
    if db is not None and job_id is not None:
        add_openai_tts_cost(db, job_id, model, len(text))


def tts_settings_for_job(db: Session | None, job_id: str | None) -> tuple[str, str]:
    if db is None or job_id is None:
        return TTS_PROVIDER, OPENAI_TTS_MODEL
    job = db.get(Job, job_id)
    if job is None:
        return TTS_PROVIDER, OPENAI_TTS_MODEL
    return job.tts_provider or TTS_PROVIDER, job.tts_model or OPENAI_TTS_MODEL


def timed_beat_duration(beat: StoryboardBeat, audio_duration: float | None = None) -> float:
    """Keep the authored pacing unless a natural voice clip needs more room.

    A storyboard's beat window is the teaching pace. Using only the TTS clip
    duration silently accelerates a lesson whenever narration is concise.
    Short clips therefore receive a post-voice hold; longer clips can expand
    the beat rather than being forced through an aggressive time stretch.
    """
    authored_duration = max(0.1, beat.storyboard_duration)
    if audio_duration is None:
        return authored_duration
    return max(authored_duration, float(audio_duration))


def generate_timed_beat_audio(
    beats: list[StoryboardBeat],
    audio_dir: Path,
    debug_log_path: Path | None = None,
    db: Session | None = None,
    job_id: str | None = None,
) -> list[TimedBeat]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    timed_beats: list[TimedBeat] = []
    previous_end = 0.0
    tts_provider, tts_model = tts_settings_for_job(db, job_id)

    for beat in beats:
        gap_before = max(0.0, beat.start_sec - previous_end)
        audio_path: Path | None = None
        if beat.vo_text and tts_provider != "silent":
            if tts_provider != "openai":
                raise RuntimeError(f"Unsupported TTS provider: {tts_provider}")
            audio_path = audio_dir / f"beat_{beat.index:02d}.mp3"
            with timed_stage(debug_log_path, f"tts_beat_{beat.index}"):
                generate_tts_audio(beat.vo_text, audio_path, db, job_id, tts_model, OPENAI_TTS_VOICE)
            target_duration = timed_beat_duration(beat, get_media_duration(audio_path))
        else:
            reason = "tts_provider_silent" if beat.vo_text else "silent"
            log_debug_timing(debug_log_path, f"SKIP stage=tts_beat_{beat.index} reason={reason}")
            target_duration = timed_beat_duration(beat)

        timed_beats.append(
            TimedBeat(
                beat=beat,
                audio_path=audio_path,
                target_duration=target_duration,
                gap_before=gap_before,
            )
        )
        previous_end = beat.end_sec

    return timed_beats


def generate_timed_beat_audio_for_edit(
    beats: list[StoryboardBeat],
    parent_work_dir: Path,
    audio_dir: Path,
    edited_beat_number: int,
    vo_changed: bool,
    debug_log_path: Path | None = None,
    db: Session | None = None,
    job_id: str | None = None,
) -> list[TimedBeat]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    timed_beats: list[TimedBeat] = []
    previous_end = 0.0
    tts_provider, tts_model = tts_settings_for_job(db, job_id)

    for beat in beats:
        gap_before = max(0.0, beat.start_sec - previous_end)
        audio_path: Path | None = None
        must_regenerate = beat.index == edited_beat_number and vo_changed
        if beat.vo_text and tts_provider != "silent":
            if tts_provider != "openai":
                raise RuntimeError(f"Unsupported TTS provider: {tts_provider}")
            audio_path = audio_dir / f"beat_{beat.index:02d}.mp3"
            parent_audio = parent_work_dir / "audio" / f"beat_{beat.index:02d}.mp3"
            if not must_regenerate and parent_audio.exists():
                shutil.copy2(parent_audio, audio_path)
            else:
                with timed_stage(debug_log_path, f"tts_beat_{beat.index}"):
                    generate_tts_audio(beat.vo_text, audio_path, db, job_id, tts_model, OPENAI_TTS_VOICE)
            target_duration = timed_beat_duration(beat, get_media_duration(audio_path))
        else:
            reason = "tts_provider_silent" if beat.vo_text else "silent"
            log_debug_timing(debug_log_path, f"SKIP stage=tts_beat_{beat.index} reason={reason}")
            target_duration = timed_beat_duration(beat)

        timed_beats.append(
            TimedBeat(
                beat=beat,
                audio_path=audio_path,
                target_duration=target_duration,
                gap_before=gap_before,
            )
        )
        previous_end = beat.end_sec

    return timed_beats


def concatenate_audio(timed_beats: list[TimedBeat], audio_dir: Path, out_path: Path) -> None:
    parts: list[Path] = []
    for timed in timed_beats:
        if timed.gap_before > 0:
            gap_path = audio_dir / f"gap_before_{timed.beat.index:02d}.mp3"
            generate_silence(timed.gap_before, gap_path)
            parts.append(gap_path)

        if timed.audio_path:
            parts.append(timed.audio_path)
            spoken_duration = get_media_duration(timed.audio_path)
            post_voice_hold = timed.target_duration - spoken_duration
            if post_voice_hold > 0.03:
                hold_path = audio_dir / f"beat_{timed.beat.index:02d}_hold.mp3"
                generate_silence(post_voice_hold, hold_path)
                parts.append(hold_path)
        else:
            silence_path = audio_dir / f"beat_{timed.beat.index:02d}_silent.mp3"
            generate_silence(timed.target_duration, silence_path)
            parts.append(silence_path)

    concat_file = audio_dir / "concat.txt"
    concat_lines = [f"file '{path.as_posix()}'" for path in parts]
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:a",
            "libmp3lame",
            str(out_path),
        ]
    )


def timing_table(timed_beats: list[TimedBeat]) -> str:
    rows: list[str] = []
    for timed in timed_beats:
        if timed.gap_before > 0:
            rows.append(f"Gap before Beat {timed.beat.index}: wait {timed.gap_before:.2f} seconds.")
        rows.append(
            "Beat "
            f"{timed.beat.index}: {timed.beat.on_screen_text} | "
            f"target animation duration {timed.target_duration:.2f} seconds"
        )
    return "\n".join(rows)


def storyboard_line_for_beat(beat: StoryboardBeat) -> str:
    vo = "(silent)" if beat.vo_text is None else f"\"{beat.vo_text}\""
    return f"[{beat.start_sec:g}-{beat.end_sec:g}] ON SCREEN: {beat.on_screen_text} | VO: {vo}"


def replace_storyboard_beat(storyboard: str, beat_number: int, on_screen: str, vo_text: str) -> str:
    beats = parse_storyboard(storyboard)
    if beat_number < 1 or beat_number > len(beats):
        raise ValueError("Beat number is out of range.")
    normalized_vo = normalize_vo_text(vo_text)
    updated = [
        StoryboardBeat(
            index=beat.index,
            start_sec=beat.start_sec,
            end_sec=beat.end_sec,
            on_screen_text=on_screen.strip() if beat.index == beat_number else beat.on_screen_text,
            vo_text=normalized_vo if beat.index == beat_number else beat.vo_text,
        )
        for beat in beats
    ]

    beat_line_pattern = re.compile(
        r"^\s*\[\d+(?:\.\d+)?-\d+(?:\.\d+)?\]\s*ON SCREEN:.*?\|\s*VO:.*$",
        re.IGNORECASE | re.MULTILINE,
    )
    lines = storyboard.splitlines()
    beat_index = 0
    new_lines: list[str] = []
    for line in lines:
        if beat_line_pattern.match(line):
            new_lines.append(storyboard_line_for_beat(updated[beat_index]))
            beat_index += 1
        else:
            new_lines.append(line)
    return "\n".join(new_lines)


def planned_total_duration(timed_beats: list[TimedBeat]) -> float:
    return sum(timed.target_duration + timed.gap_before for timed in timed_beats)


def timed_beat_windows(timed_beats: list[TimedBeat], rendered_duration: float | None = None) -> list[dict[str, float | int]]:
    """Return the actual render timeline implied by timed narration clips."""
    cursor = 0.0
    windows: list[dict[str, float | int]] = []
    for timed in timed_beats:
        cursor += timed.gap_before
        start = cursor
        cursor += timed.target_duration
        windows.append({"beat_number": timed.beat.index, "start": start, "end": cursor})

    if rendered_duration is not None and cursor > 0:
        scale = max(0.0, float(rendered_duration)) / cursor
        for window in windows:
            window["start"] = float(window["start"]) * scale
            window["end"] = float(window["end"]) * scale
    return windows


def orientation_resolution(orientation: Orientation) -> str:
    return LANDSCAPE_RESOLUTION if orientation == "landscape" else PORTRAIT_RESOLUTION


def orientation_frame_dimensions(orientation: Orientation) -> tuple[float, float]:
    """Match Manim's logical frame to the per-job pixel aspect ratio."""
    resolution = orientation_resolution(orientation)
    try:
        pixel_width, pixel_height = (int(part.strip()) for part in resolution.split(",", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {orientation} render resolution: {resolution!r}") from exc
    if pixel_width <= 0 or pixel_height <= 0:
        raise ValueError(f"Invalid {orientation} render resolution: {resolution!r}")
    frame_height = 8.0
    return frame_height * pixel_width / pixel_height, frame_height


def write_orientation_render_config(work_dir: Path, orientation: Orientation, fps: int = 30) -> Path:
    """Create a job-local Manim config so portrait renders do not use landscape coordinates."""
    frame_width, frame_height = orientation_frame_dimensions(orientation)
    pixel_width, pixel_height = orientation_resolution(orientation).split(",", 1)
    config_path = work_dir / "manim_render.cfg"
    config_path.write_text(
        "[CLI]\n"
        f"pixel_width = {pixel_width.strip()}\n"
        f"pixel_height = {pixel_height.strip()}\n"
        f"frame_width = {frame_width:.8f}\n"
        f"frame_height = {frame_height:.8f}\n"
        f"frame_rate = {fps}\n"
        "background_color = BLACK\n",
        encoding="utf-8",
    )
    return config_path


def write_tier_render_config(work_dir: Path, orientation: Orientation, tier: RenderTier) -> Path:
    """Create a job-local Manim config scoped to a specific :class:`RenderTier`.

    The resulting file is written to ``work_dir/manim_render_<tier.name>.cfg``
    so multiple tier configs can coexist in the same work directory.
    """
    resolution = (
        tier.landscape_resolution if orientation == "landscape" else tier.portrait_resolution
    )
    pixel_width_str, pixel_height_str = resolution.split(",", 1)
    pixel_width = int(pixel_width_str.strip())
    pixel_height = int(pixel_height_str.strip())
    frame_height = 8.0
    frame_width = frame_height * pixel_width / pixel_height
    config_path = work_dir / f"manim_render_{tier.name}.cfg"
    config_path.write_text(
        "[CLI]\n"
        f"pixel_width = {pixel_width}\n"
        f"pixel_height = {pixel_height}\n"
        f"frame_width = {frame_width:.8f}\n"
        f"frame_height = {frame_height:.8f}\n"
        f"frame_rate = {tier.fps}\n"
        "background_color = BLACK\n",
        encoding="utf-8",
    )
    return config_path


def frame_constraint_for_orientation(orientation: Orientation) -> str:
    if orientation == "landscape":
        return (
            "FRAME CONSTRAINT: this renders at 1920x1080, a horizontal 16:9 frame. "
            "Side-by-side horizontal arrangement is allowed and often preferred when comparing ideas. "
            "Do not stack too many objects vertically because landscape has limited vertical space. "
            "Every group of objects must be scaled to fit within config.frame_width * 0.85 and "
            "config.frame_height * 0.75 before placement."
        )
    return (
        "FRAME CONSTRAINT: this renders at 1080x1920, a vertical 9:16 frame. "
        "Do not arrange multiple objects side by side across the full width. "
        "Stack objects vertically, show one comparison at a time, or use Transform/FadeOut between beats. "
        "Every group of objects must be scaled to fit within config.frame_width * 0.85 and "
        "config.frame_height * 0.75 before placement."
    )


def beat_for_timestamp(beats: list[StoryboardBeat], timestamp: float) -> StoryboardBeat | None:
    if not beats:
        return None
    for beat in beats:
        if beat.start_sec <= timestamp <= beat.end_sec:
            return beat
    return min(beats, key=lambda beat: min(abs(timestamp - beat.start_sec), abs(timestamp - beat.end_sec)))


def text_lifecycle_feedback(beats: list[StoryboardBeat], code: str) -> str | None:
    for beat in beats:
        if not re.search(r"\b(morphs?\s+into|becomes?|transforms?\s+into)\b", beat.on_screen_text, re.IGNORECASE):
            continue
        section = code_section_for_beat(code, beat.index)
        if "ReplacementTransform" not in section and "Transform(" not in section:
            return (
                f"Beat {beat.index} says one element changes into another, but the generated code does not "
                "use ReplacementTransform or Transform in that beat section. Use ReplacementTransform, "
                "Transform, or explicitly FadeOut the previous text/equation before introducing the next "
                "one at a nearby position."
            )
    return None


def code_section_for_beat(code: str, beat_index: int) -> str:
    start_pattern = re.compile(rf"#\s*-+\s*Beat\s+{beat_index}\s*-+", re.IGNORECASE)
    next_pattern = re.compile(rf"#\s*-+\s*Beat\s+{beat_index + 1}\s*-+", re.IGNORECASE)
    start = start_pattern.search(code)
    if not start:
        return code
    next_match = next_pattern.search(code, start.end())
    end = next_match.start() if next_match else len(code)
    return code[start.start() : end]


BEAT_PARAM_KEYS = {"scale", "gap", "speed"}
BEAT_PARAM_RANGES = {
    "scale": (0.5, 2.0),
    "gap": (-6.0, 6.0),
    "speed": (0.3, 3.0),
}


def beat_params_from_code(code: str, beat_index: int) -> dict[str, float]:
    prefix = f"beat{beat_index}_"
    params: dict[str, float] = {}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return params
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, (int, float)):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.startswith(prefix):
                continue
            key = target.id.removeprefix(prefix)
            if key in BEAT_PARAM_KEYS:
                params[key] = float(node.value.value)
    return params


def validate_beat_param_values(values: dict[str, float]) -> None:
    for key, value in values.items():
        if key not in BEAT_PARAM_KEYS:
            raise ValueError(f"Unsupported beat parameter: {key}.")
        low, high = BEAT_PARAM_RANGES[key]
        if value < low or value > high:
            raise ValueError(f"{key} must be between {low} and {high}.")


def patch_beat_params_in_code(code: str, beat_index: int, values: dict[str, float]) -> str:
    validate_beat_param_values(values)
    patched = code
    for key, value in values.items():
        pattern = re.compile(
            rf"(^\s*beat{beat_index}_{key}\s*=\s*)([-+]?(?:\d+(?:\.\d*)?|\.\d+))(.*$)",
            re.MULTILINE,
        )
        replacement = rf"\g<1>{value:g}\g<3>"
        patched, count = pattern.subn(replacement, patched, count=1)
        if count != 1:
            raise ValueError(f"beat{beat_index}_{key} was not found in the generated code.")
    validate_generated_python(patched)
    return patched


def clamp_quality_score(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, number))


def parse_frame_quality_response(text: str, timestamp: float, frame_path: Path, beat: StoryboardBeat) -> FrameQualityScore:
    payload_text = text.strip()
    match = re.search(r"\{.*\}", payload_text, re.DOTALL)
    if match:
        payload_text = match.group(0)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {}
    return FrameQualityScore(
        timestamp=timestamp,
        frame_path=frame_path,
        beat_index=beat.index,
        accuracy=clamp_quality_score(payload.get("accuracy")),
        depth=clamp_quality_score(payload.get("depth")),
        logical_flow=clamp_quality_score(payload.get("logical_flow")),
        visual_relevance=clamp_quality_score(payload.get("visual_relevance")),
        element_layout=clamp_quality_score(payload.get("element_layout")),
        summary=str(payload.get("summary") or text).strip()[:700],
    )


def assess_frame_quality(
    provider: LLMProvider,
    frame_path: Path,
    beat: StoryboardBeat,
    timestamp: float,
    db: Session | None = None,
    job_id: str | None = None,
) -> FrameQualityScore:
    prompt = (
        "Assess this rendered Manim frame against the storyboard beat. Score each dimension from 1 to 5, "
        "where 5 is strong and 1 is poor. Dimensions:\n"
        "- accuracy: does the math shown match the storyboard's stated equations or claims?\n"
        "- depth: does the frame carry enough explanatory substance for this beat?\n"
        "- logical_flow: does this frame fit the surrounding derivation or explanation sequence?\n"
        "- visual_relevance: are the visuals relevant to the beat rather than decorative or unrelated?\n"
        "- element_layout: are all labels/equations/diagrams inside the visible frame, non-overlapping, readable, "
        "and not cramped?\n\n"
        f"Frame timestamp: {timestamp:.2f}s\n"
        f"Beat {beat.index}: [{beat.start_sec:.2f}-{beat.end_sec:.2f}] ON SCREEN: {beat.on_screen_text} | "
        f"VO: {beat.vo_text or '(silent)'}\n\n"
        "Respond with compact JSON only using exactly these keys: "
        "{\"accuracy\": 1-5, \"depth\": 1-5, \"logical_flow\": 1-5, "
        "\"visual_relevance\": 1-5, \"element_layout\": 1-5, \"summary\": \"short reason\"}."
    )
    if db is not None and job_id is not None:
        enforce_job_cost_budget(db, job_id, float(os.getenv("VISION_COST_RESERVATION_USD", "0.01")))
    response = provider.inspect_image(frame_path=frame_path, prompt=prompt, max_tokens=320)
    if db is not None and job_id is not None:
        actual_provider, actual_model = llm_response_identity(response, provider, provider.model)
        add_llm_cost(db, job_id, actual_provider, actual_model, response.input_tokens, response.output_tokens)
    score = parse_frame_quality_response(response.text, timestamp, frame_path, beat)
    record_quality_score(db, job_id, score)
    return score


def assess_video_quality(
    provider: LLMProvider,
    video_path: Path,
    beats: list[StoryboardBeat],
    out_dir: Path,
    db: Session | None = None,
    job_id: str | None = None,
) -> list[FrameQualityScore]:
    findings: list[FrameQualityScore] = []
    beat_windows = [(beat.start_sec, beat.end_sec) for beat in beats]
    for timestamp, frame_path in extract_beat_quality_frames(video_path, out_dir, beat_windows, sample_count=8):
        beat = beat_for_timestamp(beats, timestamp) or beats[-1]
        score = assess_frame_quality(provider, frame_path, beat, timestamp, db, job_id)
        if score.accuracy < QUALITY_SCORE_THRESHOLD or score.element_layout < QUALITY_SCORE_THRESHOLD:
            findings.append(score)
    return findings


def should_run_vision_quality_check(job_id: str | None, manual_requested: bool = False) -> bool:
    mode = VISION_QUALITY_CHECK_MODE
    if manual_requested or mode == "manual":
        return manual_requested
    if mode in {"off", "disabled", "none"}:
        return False
    if mode in {"always", "all"}:
        return True
    if mode in {"sample", "spot", "spot-check"}:
        if not job_id:
            return False
        digest = hashlib.sha256(job_id.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        return bucket < max(0.0, min(1.0, VISION_QUALITY_SAMPLE_RATE))
    return False


def build_quality_feedback(finding: FrameQualityScore) -> str:
    failed = []
    if finding.accuracy < QUALITY_SCORE_THRESHOLD:
        failed.append(f"accuracy={finding.accuracy}/5")
    if finding.element_layout < QUALITY_SCORE_THRESHOLD:
        failed.append(f"element_layout={finding.element_layout}/5")
    failed_text = ", ".join(failed) or "quality score below threshold"
    return (
        f"Frame at timestamp {finding.timestamp:.2f}s maps to Beat {finding.beat_index}. "
        f"The defect is in the Beat {finding.beat_index} section. Patch only that section and leave other beats untouched. "
        f"Failed scored checks: {failed_text}. For accuracy issues, correct the displayed equations or claims to match "
        "the storyboard. For layout issues, keep all elements inside the frame with readable spacing and no overlap. "
        f"Vision summary: {finding.summary}"
    )


def build_overlap_feedback(beats: list[StoryboardBeat], timestamp: float, summary: str) -> str:
    beat = beat_for_timestamp(beats, timestamp)
    if beat is None:
        return (
            f"Frame at timestamp {timestamp:.2f}s appears to contain overlapping text or equation regions. "
            f"{summary}"
        )

    return (
        f"Frame at timestamp {timestamp:.2f}s maps to Beat {beat.index}. The defect is in the Beat {beat.index} "
        f"section. Patch only that section's Transform/FadeOut logic, leave other beats untouched. {summary}"
    )


def attempt_deadline(start_time: float) -> float:
    return start_time + ATTEMPT_WALL_CLOCK_LIMIT_SECONDS


def attempt_timed_out(start_time: float) -> bool:
    return time.monotonic() >= attempt_deadline(start_time)


def ensure_attempt_time_remaining(start_time: float, attempt: int) -> None:
    if attempt_timed_out(start_time):
        raise TimeoutError(
            f"Attempt {attempt} exceeded the {ATTEMPT_WALL_CLOCK_LIMIT_SECONDS // 60} minute wall-clock limit."
        )


def remaining_attempt_seconds(start_time: float, attempt: int) -> float:
    ensure_attempt_time_remaining(start_time, attempt)
    return max(1.0, attempt_deadline(start_time) - time.monotonic())


def established_semantic_color_assignments(previous_code: str | None = None) -> dict[str, str]:
    assignments = dict(DEFAULT_VIDEO_SEMANTIC_PALETTE)
    if not previous_code:
        return assignments
    for role, color in SEMANTIC_COLOR_ASSIGNMENT_PATTERN.findall(previous_code):
        if APPROVED_MANIM_COLOR_PATTERN.fullmatch(color) or color.endswith("_COLOR"):
            assignments[role] = color
    return assignments


def semantic_color_assignments_in_code(code: str | None) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    if not code:
        return assignments
    for role, color in SEMANTIC_COLOR_ASSIGNMENT_PATTERN.findall(code):
        assignments.setdefault(role, []).append(color)
    return assignments


def validate_video_semantic_palette(
    code: str,
    expected: dict[str, str] | None = None,
) -> None:
    expected = expected or DEFAULT_VIDEO_SEMANTIC_PALETTE
    actual = semantic_color_assignments_in_code(code)
    missing = [role for role in expected if role not in actual]
    duplicates = [role for role, values in actual.items() if len(values) != 1]
    changed = [
        role
        for role, expected_color in expected.items()
        if role in actual and actual[role][0] != expected_color
    ]
    scene_match = re.search(r"(?m)^class\s+\w+\s*\([^)]*Scene[^)]*\)\s*:", code)
    late_assignments: list[str] = []
    if scene_match:
        scene_line = code.count("\n", 0, scene_match.start()) + 1
        for match in SEMANTIC_COLOR_ASSIGNMENT_PATTERN.finditer(code):
            line_number = code.count("\n", 0, match.start()) + 1
            if line_number >= scene_line:
                late_assignments.append(match.group(1))
    if missing or duplicates or changed or late_assignments:
        details: list[str] = []
        if missing:
            details.append(f"missing roles: {', '.join(missing)}")
        if duplicates:
            details.append(f"roles assigned more than once: {', '.join(duplicates)}")
        if changed:
            details.append(
                "changed roles: "
                + ", ".join(f"{role}={actual[role][0]} (expected {expected[role]})" for role in changed)
            )
        if late_assignments:
            details.append(f"roles assigned inside the Scene: {', '.join(late_assignments)}")
        raise SyntaxError(
            "Generated code violated the video-level semantic color palette; " + "; ".join(details) + "."
        )


def semantic_color_palette_context(previous_code: str | None = None) -> str:
    assignments = established_semantic_color_assignments(previous_code)
    source = "ESTABLISHED COLOR ASSIGNMENTS FROM THE PREVIOUS SCENE" if previous_code else "VIDEO-LEVEL SEMANTIC COLOR PALETTE"
    return source + " (hard constraints):\n" + "\n".join(
        f"{role} = {color}" for role, color in assignments.items()
    )


def generate_manim_code(
    provider: LLMProvider,
    storyboard: str,
    scene_name: str,
    timed_beats: list[TimedBeat],
    attempt_number: int = 1,
    orientation: Orientation = "portrait",
    error_feedback: str | None = None,
    previous_code: str | None = None,
    target_beat_number: int | None = None,
    db: Session | None = None,
    job_id: str | None = None,
) -> str:
    storyboard = normalize_generated_text(storyboard)
    learned_failure_context = approved_failure_instructions(storyboard, learning_categories_for_storyboard(storyboard))
    learned_failure_block = f"\n\n{learned_failure_context}" if learned_failure_context else ""
    color_palette_context = semantic_color_palette_context(previous_code)
    patch_scope = render_scope_for_retry(target_beat_number)
    if patch_scope == "beat":
        block_instruction = (
            f"RETRY SCOPE: Return just the Python code between # --- Beat {target_beat_number} params --- "
            f"and the next beat marker, nothing else. Do not rewrite the full file."
        )
    else:
        block_instruction = "Output ONLY a single Python code block, no explanation text before or after."
    system = (
        "You write Manim Community Edition v0.20.1 code ONLY. "
        "Anchor strictly to the syntax patterns in the reference examples below. "
        f"{block_instruction}\n\n"
        f"{frame_constraint_for_orientation(orientation)}\n\n"
        "PERSISTENT SPLIT-SCREEN LAYOUT CONSTRAINT: For any topic where a graph or diagram is introduced "
        "and equations will be derived from or about that graph/diagram in subsequent beats, do NOT FadeOut "
        "the graph/diagram to make room for equations. Instead, partition the frame: define two persistent "
        "regions/zones at the start of the beat sequence (e.g., graph_zone in the upper 55-60% of the frame "
        "using UP*1.2 or similar, and equation_zone in the remaining lower portion using DOWN*1.5 or similar, "
        "or left/right half if landscape). Keep the graph/diagram visible in the graph_zone, and confine all "
        "equation work and captions strictly to the equation_zone. The graph should only leave the screen "
        "when transitioning to a completely different section/topic. Equations must morph, transform, and "
        "update via ReplacementTransform in the equation_zone while the graph remains visible and updates "
        "in sync (e.g. highlighting points on the graph as they are manipulated below).\n\n"
        "PORTRAIT PADDING CONSTRAINT: For portrait (1080x1920) orientation specifically, headers/titles must "
        "have a minimum buff of 0.5 units from the top edge via .to_edge(UP, buff=0.5), and at least 0.4 units "
        "of clearance from whatever content follows below them. Do not rely on default buff values - portrait's "
        "narrower width relative to height makes tight spacing more visually cramped than in landscape, so apply "
        "slightly more generous padding for portrait specifically.\n\n"
        "ACTION-TITLE CAPTION CLEARANCE CONSTRAINT: Short action-title captions (e.g., 'Solve for the Center', "
        "'Set Up the Area') describing equation derivations must be positioned with guaranteed clearance above the "
        "equation zone. Place captions strictly in a dedicated position above the equations, for example, using "
        ".next_to(equation_zone, UP, buff=0.3) or .next_to(equation, UP, buff=0.4), rather than placing them "
        "independently. This prevents overlap collisions with equations, fractions, and exponents.\n\n"
        "COMPLEX EQUATION REVEAL CONSTRAINT: To prevent raw/unrendered text or glyph artifacts from briefly "
        "popping or flashing before the final algebraic term forms, do NOT use Write() on complex MathTex or "
        "Tex objects that contain multiple nested fractions, exponents, integrals, or subparts. Instead, use "
        "FadeIn(mobject, scale=1.05) or a simple FadeIn(mobject) transition. Write() traces SVG paths and can "
        "visually expose malformed intermediate states during LaTeX rendering, whereas FadeIn reveals the "
        "fully-compiled equation as a unified whole.\n\n"
        "DOUBLE-EXPOSURE PREVENTION CONSTRAINT: When updating a title or transitioning an "
        "equation to a new form within the persistent-layout system, NEVER simply Write() the "
        "new text while the old text/equation object still exists un-removed in the scene. "
        "Always use ReplacementTransform(old, new) for equations morphing into a new "
        "algebraic form, or explicit FadeOut(old) followed by Write(new) for titles/discrete "
        "text changes. Before adding any new title or equation-state text, verify: has the "
        "corresponding old object from this same title/equation 'slot' been removed via "
        "ReplacementTransform or FadeOut? If not, this is the double-exposure bug - fix before "
        "finalizing.\n\n"
        f"{color_palette_context}\n\n"
        "CROSS-BEAT COLOR CONSISTENCY: Define the video-level semantic palette exactly once above the Scene class and "
        "reference its named role constants in every beat. Once a color is assigned to a semantic role in an early "
        "beat, ALL subsequent beats in the same video MUST reuse that exact color for that role. Never reassign a new "
        "color to an element that already has an established color earlier in the video. When patching Beat N, the "
        "established assignments above are hard constraints, not suggestions; do not modify them inside a beat block. "
        "This rule is universal: atoms and bonds, forces and components, curves and labels, equations, geometry, and "
        "any recurring object retain their semantic colors across the full scene.\n\n"
        "MORPH CONSTRAINT: When a storyboard beat says one element 'morphs into', 'becomes', "
        "or 'transforms into' another, use ReplacementTransform or Transform between them "
        "- never leave the prior mobject on screen while adding a new one in the same position. "
        "Before introducing ANY new text/equation at a position near a previous one, explicitly "
        "FadeOut or Transform the previous object first. Before writing any new equation, verify EVERY "
        "previously-written equation/expression in this beat has been explicitly FadeOut, Transform'd, "
        "or ReplacementTransform'd away. This applies to multi-step algebraic derivations such as solving "
        "systems, combining equations, substituting expressions, and isolating variables exactly as it applies "
        "to force diagrams. A SurroundingRectangle must be created only around the mobject that exists on screen "
        "at that moment, never left referencing a stale or removed mobject. Do not animate Transform(result.copy(), "
        "next_result) and then add next_result separately; that leaves duplicate equation glyphs on screen. Use "
        "ReplacementTransform(result, next_result), or FadeOut(result) before Write(next_result).\n\n"
        "ATTACHED LABEL LIFECYCLE CONSTRAINT: Any label, angle arc, or annotation positioned with "
        ".next_to(parent, ...) or otherwise attached to a diagram element MUST be placed in the SAME VGroup "
        "as that parent before any FadeOut, Create, Transform, or ReplacementTransform transition affects either "
        "object. Animate the enclosing group so the label and its parent enter, leave, and transform together. "
        "Never allow an attached label to remain visible while its parent diagram is absent, even for one animation "
        "step. This applies to numeric angle labels such as 109.5 and 107 degrees, axes labels, force annotations, "
        "atom labels, and every other diagram-attached annotation.\n\n"
        "CONTINUOUS CREATION CONSTRAINT: Never instantiate a mobject and animate it in, then shortly afterward "
        "create or reveal a near-duplicate of the same content. Build each on-screen element with one continuous "
        "animation sequence from creation to final state. Before returning, check every beat's opening moments for "
        "redundant recreation of the same formula, diagram, or label.\n\n"
        "CONSISTENT FORMULA REVEAL: When building a formula element by element, apply the same animation type and "
        "comparable run_time to every part in the sequence. If earlier terms use Write() or FadeIn(), the final term "
        "must use the same treatment; never introduce one term with add() or instant placement while its siblings are "
        "progressively animated.\n\n"
        "ALL-TEXT COLLISION CONSTRAINT: Before finalizing EVERY Text, Tex, or MathTex mobject's position, check it "
        "against every other simultaneously-visible mobject's bounding box, including axes, curves, graph regions, "
        "diagrams, arrows, equations, labels, headings, and recap text, using mobject.get_critical_point, "
        "get_corner, or a width/height-based rectangle check, and ensure a minimum buffer of 0.3 "
        "Manim units between them. If two labels would be within that buffer, offset one further "
        "using .next_to(..., buff=0.3) chained from a non-colliding anchor, or stagger them vertically "
        "instead of placing both near the same feature. Apply this same rule to decorative arrows and "
        "annotations: they must never cross a text or equation bounding box; route around it or shorten "
        "the arrow. There are no exemptions for captions, recap text, or summary beats.\n\n"
        "MANDATORY COMPOSITION HELPER: Include this helper function exactly once in the generated file, "
        "above the Scene class, and call it after placing every Text, Tex, or MathTex mobject:\n"
        "def avoid_overlap(mobj, others, min_gap=0.3):\n"
        "    for other in others:\n"
        "        attempts = 0\n"
        "        while attempts < 8:\n"
        "            dx = abs(mobj.get_center()[0] - other.get_center()[0])\n"
        "            dy = abs(mobj.get_center()[1] - other.get_center()[1])\n"
        "            min_dx = (mobj.width + other.width) / 2 + min_gap\n"
        "            min_dy = (mobj.height + other.height) / 2 + min_gap\n"
        "            if dx >= min_dx or dy >= min_dy:\n"
        "                break\n"
        "            direction = mobj.get_center() - ORIGIN\n"
        "            if np.linalg.norm(direction) < 0.001:\n"
        "                direction = UP + RIGHT\n"
        "            mobj.shift(normalize(direction) * 0.15)\n"
        "            attempts += 1\n"
        "    return mobj\n"
        "Keep a beat-local list such as existing_mobjects containing ALL objects already visible in that beat. Call "
        "avoid_overlap(new_text, existing_mobjects, min_gap=0.3) before appending the new Text/Tex/MathTex mobject. "
        "This is required for headings, recap text, equations, mg sin theta, mg cos theta, curve labels, axis labels, "
        "tangent annotations, and error labels.\n\n"
        "CURVE LABEL COLOR CONSTRAINT: Every label identifying a plotted curve or function must use the exact same "
        "color value as that curve. Never leave a curve-specific legend or inline label at the default or WHITE unless "
        "the corresponding curve is also WHITE.\n\n"
        "GRAPH TITLE AXIS CLEARANCE: Any title or caption near graph axes MUST use "
        "a place_graph_title(title, axes, min_buffer=0.4, min_clearance=0.3) helper. The helper MUST call "
        "title.next_to(axes, UP, buff=0.4) or the stricter equivalent "
        "title.next_to(axes, UP, buff=max(0.4, min_buffer)), compute axes.x_axis.get_center()[1] + 0.3, inspect "
        "title.get_bottom()[1], and shift the title upward when it does not clear that threshold. Do "
        "this AFTER all scale_to_fit_height(), scale_to_fit_width(), and move_to() layout operations, then call "
        "avoid_overlap(title, [graph_group, axes], min_gap=0.3). Numerically verify "
        "title.get_bottom()[1] > axes.x_axis.get_center()[1] + 0.3. If the condition fails, shift the title upward "
        "until it passes; never accept a near miss or use a smaller buffer. Apply the same check to horizontal divider "
        "Line objects.\n\n"
        "AXES AND FORCE VECTOR SEPARATION: When a beat shows both coordinate axes and force vectors on the same "
        "diagram, draw the axes from a point OFFSET from the object, for example 0.5-0.8 units below-left of the "
        "block along the slope, never from the exact same origin point as the force vectors. This prevents axis "
        "labels and force labels from competing for the same angular space. Apply the avoid_overlap() check across "
        "ALL arrow labels in a beat - axes, forces, and components - not just forces against each other.\n\n"
        "MANDATORY DIAGRAM COMPOSITION: Every beat's main diagram VGroup MUST be scaled to fill roughly 50-60% of "
        "frame height and centered at ORIGIN before any animation plays on it. Use exactly this convention before "
        "any self.play() involving that beat's diagram: diagram = VGroup(...); "
        "diagram.scale_to_fit_height(config.frame_height * 0.55); diagram.move_to(ORIGIN). Never leave a diagram "
        "at its default/incidental size and position.\n\n"
        "CLARITY-FIRST MOTION: Prioritize clarity over visual density. Do not add bouncing, repeated Indicate calls, "
        "cosmetic color transitions, or emphasis scaling unless motion directly explains the relationship being taught. "
        "When in doubt, use a simpler, longer-held, clearly labeled static diagram. Motion must serve the explanation, "
        "not decorate it.\n\n"
        "GENUINE VISUALIZATION: Text revealed with Write() or FadeIn() alone is not an adequate visualization. Build or "
        "change the real relationship: plot a graph, substitute values into an equation and simplify, construct a "
        "diagram piece by piece, or show a parameter changing a curve. If a concept has no honest visual construction, "
        "keep the text static and restrained rather than adding decorative animation.\n\n"
        "COLOR CONSTRAINT: Only use these Manim CE color constants: WHITE, BLACK, RED, GREEN, BLUE, "
        "YELLOW, ORANGE, PURPLE, PINK, TEAL, GRAY, GREY, MAROON, GOLD, and their _A/_B/_C/_D/_E "
        "shade variants. Never invent compound names like YELLOW_GREEN or GREEN_YELLOW. For "
        "intermediate shades use interpolate_color() or a hex string like '#RRGGBB'.\n\n"
        "TEXT KWARG CONSTRAINT: Never pass font_family= to MathTex, Tex, Text, or any Manim mobject. "
        "Manim CE rejects that keyword during render. For MathTex/Tex use font_size, color, and layout "
        "methods only. For plain Text, use Text(..., font='...') only when a specific font is required.\n\n"
        "LATEX TEXT CONSTRAINT: Any content containing LaTeX commands such as \\frac, \\sum, \\cdots, "
        "\\sqrt, \\theta, ^{...}, or _{...} MUST use MathTex(r\"...\"), never Text(\"...\"). "
        "Text() is only for plain prose or labels with no mathematical notation. A Text() string containing even "
        "one '$', backslash, or '^(' sequence is a hard validation failure with no exceptions; '^{', '_(', and '_{' "
        "are rejected by the same deterministic check.\n\n"
        "MACLAURIN ZERO CONSTRAINT: When LaTeX refers to numeric zero, including a Maclaurin center or derivative "
        "evaluation at x=0, always use numeral 0, never letter o. Check f^{(n)}(0), x=0, and a=0 before returning.\n\n"
        "SAFE SCALE CONSTRAINT: Include a safe_scale(mobj, scale_factor, max_width_pct=0.85, "
        "max_height_pct=0.75) helper that clamps a requested scale using config.frame_width and "
        "config.frame_height before returning mobj.animate.scale(...). Never call .animate.scale(factor) "
        "directly for emphasis or zoom effects. Always call safe_scale(mobj, factor) instead.\n\n"
        "VISUAL CONSTRUCTION CONSTRAINT - ON_SCREEN SPEC: The storyboard's ON SCREEN field is an operational "
        "specification, never a "
        "caption. Never copy its full sentence or a close paraphrase into Text(), Tex(), or MathTex(). Construct the "
        "actual visual or mathematical objects it describes. A graph comparison means plot the functions; a "
        "substitution step means display the resulting equation with MathTex. If a visible caption is genuinely "
        "needed, author a separate label of six words or fewer, never the operational sentence. Validation rejects "
        "captions longer than eight words whose vocabulary overlaps the beat specification by more than 60 percent. "
        "Imperative verbs such as Draw, Label, Show, Illustrate, Add, or Highlight are construction commands. For an "
        "Atwood machine, construct a Circle pulley, Line rope segments, Square mass blocks, Arrow force/tension "
        "vectors, and concise MathTex labels placed with .next_to().\n\n"
        "MOLECULAR GEOMETRY CONSTRAINT: When depicting three-dimensional molecular geometry such as tetrahedral "
        "or trigonal pyramidal structure in a standard 2D Scene, use wedge-dash notation. Use a filled Polygon wedge "
        "for a bond coming toward the viewer, a DashedLine for a bond going away, and ordinary Line bonds for bonds "
        "in the screen plane. Never draw every bond as a flat straight line. Include the actual atom labels at every "
        "vertex, such as C, H, and N when those atoms are requested. Use Angle or Arc with a numeric MathTex label "
        "for each bond angle stated by the storyboard, including degree notation. Draw lone pairs as a distinct pair "
        "of electron dots and keep them visually separate from bonding pairs.\n\n"
        "STANDARD TERMINOLOGY CONSTRAINT: Use full standard scientific and mathematical terminology in titles and "
        "labels rather than shortened or informal names. For example, label NH3 as 'trigonal pyramidal', not merely "
        "'pyramidal', and use 'tetrahedral', never an invented shorthand. Preserve the topic's recognized nomenclature "
        "consistently across all beats.\n\n"
        "PAGINATION CONSTRAINT: If one beat would need more than 4-5 simultaneous labeled elements, "
        "three or more labeled curves, or font sizes below readable scale, render the elements sequentially "
        "inside that beat or split dense content across the already-paginated storyboard beats. Never cram "
        "a dense derivation or diagram into a single unreadable shot.\n\n"
        "TIMING CONSTRAINT: create clearly commented sections named '# --- Beat 1 ---', "
        "'# --- Beat 2 ---', and so on. Each section's animation runtime plus self.wait() calls "
        "must be as close as Manim's timing model allows to that beat's target duration. "
        "Use explicit run_time values. Preserve the beat order. Do not merge beats. Every Write() or Create() of "
        "Text, Tex, or MathTex must finish before any later play or FadeOut affects that mobject. Allocate at least "
        "0.05 seconds per source character and at least 1.5 seconds total. If the beat cannot afford that time, "
        "shorten the displayed content or use FadeIn(); never squeeze a progressive reveal below that minimum. Hold "
        "the completed primary visual for at least 0.65 seconds before the next transition, while it remains visible. "
        "Never introduce four or more new visual objects in one beat; split the explanation instead.\n\n"
        "SCENE CONTINUITY CONSTRAINT: Before a new beat animates any Text, Tex, or MathTex, explicitly FadeOut the "
        "previous beat's captions and diagram, or verify the new text against every still-visible object. An immediate "
        "FadeOut followed directly by the next beat is allowed; never self.wait() after removing all visible content. "
        "Never FadeOut a primary graph, diagram, or main equation inside a beat unless replacement visual content is "
        "introduced in that same animation or the immediately following animation. Every non-final transition must "
        "avoid both stale text overlap and a timed blank frame; floating captions alone are not replacement visuals.\n\n"
        "SUMMARY REVEAL CONSTRAINT: In a closing or recap beat with three or more cards, buttons, or grouped elements, "
        "reveal them with LaggedStart/AnimationGroup or sequential FadeIn animations using a visible 0.15-0.2 second "
        "start offset. Do not reveal every recap element simultaneously.\n\n"
        "BEAT PARAMETER CONSTRAINT: Every beat must define tunable numeric values at the top of that beat's "
        "code block before any objects or animations. Use exactly these variable names for each beat number: "
        "beatN_scale, beatN_gap, and beatN_speed, replacing N with the beat number, for example "
        "# --- Beat 10 params ---\nbeat10_scale = 1.0\nbeat10_gap = 2.3\nbeat10_speed = 1.0\n"
        "# --- Beat 10 ---\n"
        "Use beatN_scale for object scale factors, beatN_gap for spacing/position offsets, and beatN_speed "
        "for animation run_time values. Do not hide these values as inline numeric literals where a user may "
        "need to tune scale, spacing, or speed later.\n\n"
        f"VERIFIED WORKING REFERENCE EXAMPLES (Manim CE 0.20.1):\n{selected_reference_scenes(storyboard)}"
        f"{learned_failure_block}"
    )

    from app.vivacity_prompts import build_manim_codegen_addon
    system += "\n\n" + build_manim_codegen_addon(include_recall_checkpoint=True)

    user_msg = (
        f"Write a Manim Scene class named `{scene_name}` implementing this storyboard:\n\n"
        f"{storyboard}\n\n"
        "Use this per-beat timing table. Each beat's voiceover clip duration is used as an explicit "
        "timing target for that beat's animation, with automated overflow and drift checks before a job "
        "is marked complete.\n\n"
        f"{timing_table(timed_beats)}\n\n"
        f"Total target duration including explicit gaps: {planned_total_duration(timed_beats):.2f} seconds."
    )

    if error_feedback:
        if previous_code:
            previous_fragment = extract_beat_block(previous_code, target_beat_number) if target_beat_number else previous_code
            user_msg += (
                f"\n\nHere is the exact code from the previous attempt:\n```python\n{previous_fragment}\n```\n\n"
                f"That attempt failed validation with this feedback:\n{error_feedback}\n\n"
                + (
                    f"Return only the corrected Beat {target_beat_number} block and preserve the beat comments."
                    if target_beat_number is not None
                    else "Return the FULL corrected Python file because no single affected beat was identified."
                )
            )
        else:
            user_msg += (
                f"\n\nPrevious attempt failed validation with this feedback:\n{error_feedback}\n"
                + (
                    f"Fix the specific issue and return only the Beat {target_beat_number} block."
                    if target_beat_number is not None
                    else "Fix the specific issue and return the FULL corrected Python file."
                )
            )

    active_model = codegen_model_for_attempt(provider, attempt_number)
    if db is not None and job_id is not None:
        enforce_job_cost_budget(
            db,
            job_id,
            projected_llm_call_cost(provider.name, active_model, system, user_msg, MAX_TOKENS),
        )
    response = provider.generate(
        system=system,
        user_message=user_msg,
        max_tokens=MAX_TOKENS,
        model=active_model,
    )
    if db is not None and job_id is not None:
        actual_provider, actual_model = llm_response_identity(response, provider, active_model)
        add_llm_cost(db, job_id, actual_provider, actual_model, response.input_tokens, response.output_tokens)
    code = strip_code_fence(normalize_generated_text(response.text))
    if response.truncated:
        partial_tail = code[-240:].strip() or "<empty response>"
        raise TruncatedCodeResponse(
            "Your previous response was truncated mid-string or before the Python file completed "
            f"(response tail: {partial_tail!r}). Ensure your response completes fully within the token budget; "
            "if a string is very long, use a shorter equivalent form. Respond with ONLY the code."
        )
    return code


def generate_valid_manim_code(
    db: Session,
    job_id: str,
    provider: LLMProvider,
    storyboard: str,
    scene_name: str,
    timed_beats: list[TimedBeat],
    orientation: Orientation,
    attempt_start_time: float,
    render_attempt: int,
    render_error_feedback: str | None,
    previous_render_code: str | None,
    debug_log_path: Path | None = None,
) -> str:
    error_feedback = render_error_feedback
    previous_code = previous_render_code
    target_beat_number = beat_number_from_traceback(previous_render_code, render_error_feedback) or beat_number_from_feedback(
        render_error_feedback
    )

    for parse_attempt in range(1, CODEGEN_PARSE_RETRIES + 2):
        ensure_attempt_time_remaining(attempt_start_time, render_attempt)
        base_code = previous_code or previous_render_code
        code = ""
        rate_limit_retry = 0
        truncated_feedback: str | None = None
        while True:
            ensure_attempt_time_remaining(attempt_start_time, render_attempt)
            try:
                with timed_stage(debug_log_path, f"codegen_llm_attempt_{render_attempt}_syntax_{parse_attempt}"):
                    code = generate_manim_code(
                        provider,
                        storyboard,
                        scene_name,
                        timed_beats,
                        attempt_number=render_attempt,
                        orientation=orientation,
                        error_feedback=error_feedback,
                        previous_code=previous_code,
                        target_beat_number=target_beat_number,
                        db=db,
                        job_id=job_id,
                    )
                break
            except TruncatedCodeResponse as exc:
                truncated_feedback = str(exc)
                break
            except Exception as exc:
                if not is_rate_limit_exception(exc):
                    raise
                rate_limit_retry += 1
                if rate_limit_retry > RATE_LIMIT_RETRY_LIMIT:
                    raise RateLimitExhausted(
                        f"Provider rate limit persisted for render attempt {render_attempt} after {RATE_LIMIT_RETRY_LIMIT} backoff retries."
                    ) from exc
                sleep_seconds = rate_limit_retry_after_seconds(exc)
                log_debug_timing(
                    debug_log_path,
                    f"RATE_LIMIT_RETRY attempt={render_attempt} syntax={parse_attempt} backoff={rate_limit_retry}/{RATE_LIMIT_RETRY_LIMIT} sleep_sec={sleep_seconds:.1f}",
                )
                update_job(
                    db,
                    job_id,
                    status=JobStatus.retrying,
                    progress_message=(
                        f"Rate limit encountered for attempt {render_attempt}/{MAX_RETRIES}; waiting {sleep_seconds:.1f}s before retrying the same attempt."
                    ),
                    attempt_number=render_attempt,
                    error=str(exc),
                )
                time.sleep(sleep_seconds)
        if truncated_feedback is not None:
            previous_code = base_code
            error_feedback = truncated_feedback
            update_job(
                db,
                job_id,
                status=JobStatus.generating_code if render_attempt == 1 else JobStatus.retrying,
                progress_message=(
                    f"Generated code was cut off for render attempt {render_attempt}/{MAX_RETRIES}; "
                    f"requesting a complete code response ({parse_attempt}/{CODEGEN_PARSE_RETRIES + 1})."
                ),
                attempt_number=render_attempt,
                error=truncated_feedback,
            )
            continue
        if target_beat_number is not None:
            response_marker_numbers = [
                int(match.group(1))
                for match in re.finditer(r"(?m)^[ \t]*#\s*---\s*Beat\s+(\d+)(?:\s+params)?\s*---\s*$", code)
            ]
            if not response_marker_numbers:
                previous_code = base_code
                error_feedback = PURE_PYTHON_FEEDBACK
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code if render_attempt == 1 else JobStatus.retrying,
                    progress_message=(
                        f"Generated response did not include a usable Beat {target_beat_number} block for render attempt "
                        f"{render_attempt}/{MAX_RETRIES}; requesting code-only output ({parse_attempt}/{CODEGEN_PARSE_RETRIES + 1})."
                    ),
                    attempt_number=render_attempt,
                    error=f"{PURE_PYTHON_FEEDBACK} Parser error: missing beat markers in response.",
                )
                continue
            if any(marker_number != target_beat_number for marker_number in response_marker_numbers):
                previous_code = base_code
                error_feedback = PURE_PYTHON_FEEDBACK
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code if render_attempt == 1 else JobStatus.retrying,
                    progress_message=(
                        f"Generated response included extra beat markers outside Beat {target_beat_number} for render attempt "
                        f"{render_attempt}/{MAX_RETRIES}; requesting code-only output ({parse_attempt}/{CODEGEN_PARSE_RETRIES + 1})."
                    ),
                    attempt_number=render_attempt,
                    error=f"{PURE_PYTHON_FEEDBACK} Parser error: extra beat markers in response.",
                )
                continue
            if base_code is None:
                raise AttemptFailed(f"Cannot patch Beat {target_beat_number} without prior full scene code.")
            try:
                code = replace_beat_block(base_code, target_beat_number, code)
            except ValueError as exc:
                previous_code = base_code
                error_feedback = PURE_PYTHON_FEEDBACK
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code if render_attempt == 1 else JobStatus.retrying,
                    progress_message=(
                        f"Generated response did not include a usable Beat {target_beat_number} block for render attempt "
                        f"{render_attempt}/{MAX_RETRIES}; requesting code-only output ({parse_attempt}/{CODEGEN_PARSE_RETRIES + 1})."
                    ),
                    attempt_number=render_attempt,
                    error=f"{PURE_PYTHON_FEEDBACK} Parser error: {exc}",
                )
                continue
        try:
            with timed_stage(debug_log_path, f"syntax_guard_attempt_{render_attempt}_syntax_{parse_attempt}"):
                validate_generated_python(code, storyboard)
                scene_class_names = scene_subclass_names_from_code(code)
                if scene_class_names != [scene_name]:
                    raise SyntaxError(
                        f"Generated code must define only class {scene_name}(Scene); found {scene_class_names}."
                    )
                previous_palette = semantic_color_assignments_in_code(previous_render_code)
                if previous_render_code is None or previous_palette:
                    expected_palette = established_semantic_color_assignments(previous_render_code)
                    validate_video_semantic_palette(code, expected_palette)
            if parse_attempt > 1:
                stage_failure_fix(
                    job_id=job_id,
                    scene_name=scene_name,
                    beat_number=target_beat_number,
                    failure_feedback=error_feedback,
                    fixed_code=code,
                )
            return code
        except SyntaxError as exc:
            previous_code = code
            error_feedback = (
                f"{PURE_PYTHON_FEEDBACK} The parser/validator error was: {exc}. "
                "Fix that exact issue in the returned Python code."
            )
            write_codegen_validation_rejection(
                job_id,
                render_attempt=render_attempt,
                validation_attempt=parse_attempt,
                provider_name=provider.name,
                model=codegen_model_for_attempt(provider, render_attempt),
                reason=str(exc),
                target_beat_number=target_beat_number,
            )
            update_job(
                db,
                job_id,
                status=JobStatus.generating_code if render_attempt == 1 else JobStatus.retrying,
                progress_message=(
                    f"Generated response was not valid Python for render attempt "
                    f"{render_attempt}/{MAX_RETRIES}; requesting code-only output "
                    f"({parse_attempt}/{CODEGEN_PARSE_RETRIES + 1})."
                ),
                attempt_number=render_attempt,
                error=f"{PURE_PYTHON_FEEDBACK} Parser error: {exc}",
            )
            if target_beat_number is None:
                target_beat_number = beat_number_from_feedback(error_feedback)

    raise AttemptFailed(
        "Generated code did not parse after code-format retries. "
        f"Last feedback: {PURE_PYTHON_FEEDBACK}"
    )


def _canonical_job_id(job_id: str) -> str:
    try:
        canonical = str(uuid.UUID(job_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise SceneIsolationError(f"Invalid job ID for render isolation: {job_id!r}.") from exc
    if canonical != job_id:
        raise SceneIsolationError(f"Job ID must use canonical UUID form: {job_id!r}.")
    return canonical


def expected_job_workspace(job_id: str, *, root: Path | None = None) -> Path:
    canonical = _canonical_job_id(job_id)
    return ((root or WORK_ROOT).resolve() / canonical).resolve()


def validate_job_workspace(job_id: str, work_dir: Path, *, root: Path | None = None) -> Path:
    expected = expected_job_workspace(job_id, root=root)
    actual = work_dir.resolve()
    if work_dir.is_symlink():
        raise SceneIsolationError(f"Job workspace cannot be a symbolic link: {work_dir}.")
    if actual != expected:
        raise SceneIsolationError(
            f"Job workspace mismatch for {job_id}: expected {expected}, received {actual}."
        )
    return expected


def _class_base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def scene_subclass_names_from_code(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SceneIsolationError(f"Scene source is not valid Python: {exc}.") from exc

    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    scene_names = set(MANIM_SCENE_BASE_NAMES)
    discovered: list[str] = []
    changed = True
    while changed:
        changed = False
        for node in class_nodes:
            if node.name in discovered:
                continue
            base_names = {_class_base_name(base) for base in node.bases}
            if any(base_name in scene_names for base_name in base_names if base_name):
                discovered.append(node.name)
                scene_names.add(node.name)
                changed = True
    return discovered


def _scene_source_sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _write_scene_isolation_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def record_scene_isolation_violation(
    job_id: str,
    scene_name: str,
    scene_file: Path,
    class_names: list[str],
    reason: str,
) -> None:
    try:
        audit_dir = expected_job_workspace(job_id)
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / "scene_isolation_violations.jsonl"
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "expected_scene_name": scene_name,
            "scene_file": str(scene_file.resolve()),
            "scene_class_names": class_names,
            "reason": reason,
        }
        with audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Isolation validation must still reject even if its audit path is unavailable.
        return


def validate_scene_file_isolation(
    job_id: str,
    scene_name: str,
    scene_file: Path,
    work_dir: Path,
    *,
    root: Path | None = None,
    write_manifest: bool = True,
) -> str:
    class_names: list[str] = []
    try:
        expected_workspace = validate_job_workspace(job_id, work_dir, root=root)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", scene_name or ""):
            raise SceneIsolationError(f"Invalid scene class name: {scene_name!r}.")
        expected_file = (expected_workspace / f"{scene_name}.py").resolve()
        actual_file = scene_file.resolve()
        if scene_file.is_symlink():
            raise SceneIsolationError(f"Scene source cannot be a symbolic link: {scene_file}.")
        if actual_file != expected_file:
            raise SceneIsolationError(
                f"Scene source mismatch for {job_id}: expected {expected_file}, received {actual_file}."
            )
        if not scene_file.is_file():
            raise SceneIsolationError(f"Scene source does not exist: {scene_file}.")

        code = scene_file.read_text(encoding="utf-8")
        class_names = scene_subclass_names_from_code(code)
        if len(class_names) != 1:
            raise SceneIsolationError(
                f"Expected exactly one Manim Scene subclass for job {job_id}; found "
                f"{len(class_names)}: {class_names}."
            )
        if class_names[0] != scene_name:
            raise SceneIsolationError(
                f"The sole Scene subclass must be {scene_name}; found {class_names[0]}."
            )

        source_hash = _scene_source_sha256(code)
        if write_manifest:
            _write_scene_isolation_json(
                expected_workspace / "scene_isolation_manifest.json",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_id": job_id,
                    "workspace": str(expected_workspace),
                    "scene_file": str(actual_file),
                    "scene_name": scene_name,
                    "scene_class_names": class_names,
                    "source_sha256": source_hash,
                    "render_target": scene_name,
                },
            )
        return source_hash
    except SceneIsolationError as exc:
        record_scene_isolation_violation(job_id, scene_name, scene_file, class_names, str(exc))
        raise


def write_job_scene_file(job_id: str, scene_name: str, code: str) -> Path:
    work_dir = expected_job_workspace(job_id)
    validate_job_workspace(job_id, work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    scene_file = work_dir / f"{scene_name}.py"
    if scene_file.is_symlink():
        raise SceneIsolationError(f"Scene source cannot be a symbolic link: {scene_file}.")

    # --- Prepend global monkeypatch to check mobject width/position for Text/Tex ---
    patch_code = """# --- Framework Level Frame-Overflow & Collision Prevention Patch ---
from manim import Scene, Mobject, config, RIGHT, UP

def safe_mobject_scale(mob, scene, ignore_mobs=None):
    if not isinstance(mob, Mobject):
        return mob
    if getattr(mob, "_safe_scaled", False):
        return mob
        
    def is_inside_tex_container(m, sc):
        def has_tex_ancestor(root, target):
            cls = root.__class__.__name__
            if ("Text" in cls or "Tex" in cls) and root != target:
                def contains(p, t):
                    if hasattr(p, "submobjects") and p.submobjects:
                        if t in p.submobjects:
                            return True
                        return any(contains(sub, t) for sub in p.submobjects)
                    return False
                if contains(root, target):
                    return True
            if hasattr(root, "submobjects") and root.submobjects:
                return any(has_tex_ancestor(sub, target) for sub in root.submobjects)
            return False
        return any(has_tex_ancestor(top_mob, m) for top_mob in sc.mobjects)

    if is_inside_tex_container(mob, scene):
        return mob
    
    actual_ignore = set(ignore_mobs) if ignore_mobs else set()
    actual_ignore.add(mob)
    
    def get_all_text_mobjects(m):
        cls_name = m.__class__.__name__
        if "SingleStringMobject" in cls_name or "TexSymbol" in cls_name:
            return []
        if "Text" in cls_name or "Tex" in cls_name:
            return [m]
        if cls_name == "VGroup":
            def is_pure_text_group(g):
                if "Text" in g.__class__.__name__ or "Tex" in g.__class__.__name__:
                    return True
                if g.__class__.__name__ == "VGroup" and hasattr(g, "submobjects") and g.submobjects:
                    return all(is_pure_text_group(sub) for sub in g.submobjects)
                return False
            if is_pure_text_group(m):
                return [m]
        res = []
        if hasattr(m, "submobjects") and m.submobjects:
            for sub in m.submobjects:
                res.extend(get_all_text_mobjects(sub))
        return res

    def get_axes_segments(axes):
        segments = []
        origin = axes.c2p(0, 0)
        
        # x-axis line
        x_min_scene = axes.c2p(axes.x_range[0], 0)[0]
        x_max_scene = axes.c2p(axes.x_range[1], 0)[0]
        y_axis_pos = origin[1]
        segments.append(("horizontal", y_axis_pos, x_min_scene, x_max_scene))
        
        # y-axis line
        y_min_scene = axes.c2p(0, axes.y_range[0])[1]
        y_max_scene = axes.c2p(0, axes.y_range[1])[1]
        x_axis_pos = origin[0]
        segments.append(("vertical", x_axis_pos, y_min_scene, y_max_scene))
        
        # Tick lines (0.1 units visual tick size)
        tick_size = 0.1
        for x_val in range(int(axes.x_range[0]), int(axes.x_range[1]) + 1):
            x_scene = axes.c2p(x_val, 0)[0]
            segments.append(("vertical", x_scene, y_axis_pos - tick_size, y_axis_pos + tick_size))
            
        for y_val in range(int(axes.y_range[0]), int(axes.y_range[1]) + 1):
            y_scene = axes.c2p(0, y_val)[1]
            segments.append(("horizontal", y_scene, x_axis_pos - tick_size, x_axis_pos + tick_size))
            
        return segments

    def avoid_collisions(text_mob, scene, ignore_mobs):
        obstacles = []
        axes_mobs = []

        def get_leaf_mobjects(m):
            if m == text_mob or m in ignore_mobs:
                return []
            cls = m.__class__.__name__
            if cls == "Axes":
                return []
            if "Text" in cls or "Tex" in cls:
                return [m]
            if cls == "VGroup" and hasattr(m, "submobjects") and m.submobjects:
                leaves = []
                for sub in m.submobjects:
                    leaves.extend(get_leaf_mobjects(sub))
                return leaves
            return [m]

        for m in scene.mobjects:
            if m == text_mob or m in ignore_mobs:
                continue
            cls = m.__class__.__name__
            if cls == "Axes":
                axes_mobs.append(m)
            else:
                obstacles.extend(get_leaf_mobjects(m))

        def get_bbox(m):
            padding = 0.05
            left = m.get_left()[0] - padding
            right = m.get_right()[0] + padding
            bottom = m.get_bottom()[1] - padding
            top = m.get_top()[1] + padding
            return [left, right, bottom, top]

        def overlaps(box1, box2):
            return not (box1[1] < box2[0] or box2[1] < box1[0] or box1[3] < box2[2] or box2[3] < box1[2])

        def overlaps_axes_segment(box, segment):
            seg_type, pos, start, end = segment
            if seg_type == "horizontal":
                return (box[2] <= pos <= box[3]) and not (end < box[0] or box[1] < start)
            else:
                return (box[0] <= pos <= box[1]) and not (end < box[2] or box[3] < start)

        axes_segments = []
        for axes in axes_mobs:
            axes_segments.extend(get_axes_segments(axes))

        max_attempts = 16
        step_size = 0.2
        directions = [UP, DOWN, RIGHT, LEFT, UP+RIGHT, UP+LEFT, DOWN+RIGHT, DOWN+LEFT]

        box = get_bbox(text_mob)
        collides = False
        for obs in obstacles:
            if overlaps(box, get_bbox(obs)):
                collides = True
                break
        if not collides:
            for seg in axes_segments:
                if overlaps_axes_segment(box, seg):
                    collides = True
                    break

        if not collides:
            return

        best_shift = None
        min_dist = float('inf')
        for direction in directions:
            temp_mob = text_mob.copy()
            for attempt in range(1, max_attempts + 1):
                shift_vec = direction * (step_size * attempt)
                temp_mob.shift(shift_vec)
                temp_box = get_bbox(temp_mob)
                
                any_collision = False
                for obs in obstacles:
                    if overlaps(temp_box, get_bbox(obs)):
                        any_collision = True
                        break
                if not any_collision:
                    for seg in axes_segments:
                        if overlaps_axes_segment(temp_box, seg):
                            any_collision = True
                            break
                if not any_collision:
                    dist = attempt * step_size
                    if dist < min_dist:
                        min_dist = dist
                        best_shift = shift_vec
                    break
                    
        if best_shift is not None:
            text_mob.shift(best_shift)

    def adjust_mobject_safety(text_mob):
        margin = 0.25
        safe_left = -config.frame_width / 2 + margin
        safe_right = config.frame_width / 2 - margin
        safe_top = config.frame_height / 2 - margin
        safe_bottom = -config.frame_height / 2 + margin

        max_w = safe_right - safe_left
        max_h = safe_top - safe_bottom

        if text_mob.width > max_w and text_mob.width > 1e-4:
            text_mob.scale_to_fit_width(max_w)
        if text_mob.height > max_h and text_mob.height > 1e-4:
            text_mob.scale_to_fit_height(max_h)

        left = text_mob.get_left()[0]
        right = text_mob.get_right()[0]
        bottom = text_mob.get_bottom()[1]
        top = text_mob.get_top()[1]

        shift_x = 0
        if left < safe_left:
            shift_x = safe_left - left
        elif right > safe_right:
            shift_x = safe_right - right

        shift_y = 0
        if bottom < safe_bottom:
            shift_y = safe_bottom - bottom
        elif top > safe_top:
            shift_y = safe_top - top

        if abs(shift_x) > 1e-4 or abs(shift_y) > 1e-4:
            text_mob.shift(shift_x * RIGHT + shift_y * UP)

    text_mobs = get_all_text_mobjects(mob)
    for text_mob in text_mobs:
        avoid_collisions(text_mob, scene, ignore_mobs=actual_ignore)
        adjust_mobject_safety(text_mob)
        
    def mark_scaled(m):
        m._safe_scaled = True
        if hasattr(m, "submobjects") and m.submobjects:
            for sub in m.submobjects:
                mark_scaled(sub)
    mark_scaled(mob)
    
    return mob

original_add = Scene.add
def patched_add(self, *mobjects):
    res = original_add(self, *mobjects)
    for mob in mobjects:
        safe_mobject_scale(mob, self)
    return res
Scene.add = patched_add

original_play = Scene.play
def patched_play(self, *args, **kwargs):
    new_args = []
    for arg in args:
        if isinstance(arg, Mobject):
            safe_mobject_scale(arg, self)
            new_args.append(arg)
        elif hasattr(arg, 'mobject'):
            if hasattr(arg, 'target_mobject') and arg.target_mobject:
                safe_mobject_scale(arg.target_mobject, self, ignore_mobs={arg.mobject})
            else:
                safe_mobject_scale(arg.mobject, self)
            new_args.append(arg)
        else:
            new_args.append(arg)
    res = original_play(self, *new_args, **kwargs)
    for mob in self.mobjects:
        safe_mobject_scale(mob, self)
    return res
Scene.play = patched_play

original_wait = Scene.wait
def patched_wait(self, *args, **kwargs):
    for mob in self.mobjects:
        safe_mobject_scale(mob, self)
    return original_wait(self, *args, **kwargs)
Scene.wait = patched_wait
# --------------------------------------------------------

"""
    code = patch_code + code

    with scene_file.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(code)
        handle.flush()
        os.fsync(handle.fileno())
    if scene_file.read_text(encoding="utf-8") != code:
        raise SceneIsolationError(f"Scene source verification failed after truncating write: {scene_file}.")
    validate_scene_file_isolation(job_id, scene_name, scene_file, work_dir)
    return scene_file




def render_scene(
    scene_file: Path,
    scene_name: str,
    work_dir: Path,
    orientation: Orientation = "portrait",
    timeout_seconds: float | None = None,
    job_id: str | None = None,
    render_tier: RenderTier | None = None,
) -> tuple[bool, str]:
    try:
        source_hash = None
        if job_id is not None:
            source_hash = validate_scene_file_isolation(job_id, scene_name, scene_file, work_dir)

        if render_tier is not None:
            quality = render_tier.quality_flag
            render_config = write_tier_render_config(work_dir, orientation, render_tier)
            resolution = (
                render_tier.landscape_resolution
                if orientation == "landscape"
                else render_tier.portrait_resolution
            )
            media_dir = work_dir / f"media_{render_tier.name}"
        else:
            quality = RENDER_QUALITY if RENDER_QUALITY in {"l", "m", "h", "p", "k"} else "m"
            fps = 60 if quality in {"h", "p", "k"} else (30 if quality == "m" else 15)
            render_config = write_orientation_render_config(work_dir, orientation, fps=fps)
            resolution = orientation_resolution(orientation)
            media_dir = work_dir / "media"

        result = run_command(
            [
                sys.executable,
                "-m",
                "manim",
                f"-q{quality}",
                "--disable_caching",
                "--config_file",
                str(render_config.resolve()),
                "--progress_bar",
                "none",
                "--resolution",
                resolution,
                "--media_dir",
                str(media_dir.resolve()),
                str(scene_file.resolve()),
                scene_name,
            ],
            cwd=work_dir,
            check=False,
            timeout_seconds=timeout_seconds,
        )
        output = subprocess_output_text(result.stdout) + "\n" + subprocess_output_text(result.stderr)
        if job_id is not None and source_hash is not None:
            post_render_hash = _scene_source_sha256(scene_file.read_text(encoding="utf-8"))
            if post_render_hash != source_hash:
                reason = (
                    f"Scene source changed while job {job_id} was rendering; expected hash "
                    f"{source_hash}, found {post_render_hash}."
                )
                record_scene_isolation_violation(job_id, scene_name, scene_file, [scene_name], reason)
                return False, reason
        return result.returncode == 0, output
    except SceneIsolationError as exc:
        return False, f"Scene isolation validation failed: {exc}"
    except subprocess.TimeoutExpired as exc:
        output = subprocess_output_text(exc.stdout) + "\n" + subprocess_output_text(exc.stderr)
        return False, f"Manim render timed out after {timeout_seconds:.1f}s.\n{output}"


def render_scene_for_job(
    job_id: str,
    scene_file: Path,
    scene_name: str,
    work_dir: Path,
    orientation: Orientation = "portrait",
    timeout_seconds: float | None = None,
    render_tier: RenderTier | None = None,
) -> tuple[bool, str]:
    """Render a scene for a job, optionally using a specific :class:`RenderTier`.

    When *render_tier* is supplied the render runs at the tier's resolution and
    quality settings and writes output to ``media_<tier.name>/`` inside the job
    work directory rather than the default ``media/`` directory.
    """
    source_hash = validate_scene_file_isolation(job_id, scene_name, scene_file, work_dir)
    kwargs: dict[str, object] = {
        "orientation": orientation,
        "timeout_seconds": timeout_seconds,
    }
    if "job_id" in inspect.signature(render_scene).parameters:
        kwargs["job_id"] = job_id
    if render_tier is not None and "render_tier" in inspect.signature(render_scene).parameters:
        kwargs["render_tier"] = render_tier
    result = render_scene(scene_file, scene_name, work_dir, **kwargs)  # type: ignore[arg-type]
    post_render_hash = _scene_source_sha256(scene_file.read_text(encoding="utf-8"))
    if post_render_hash != source_hash:
        reason = (
            f"Scene source changed while job {job_id} was rendering; expected hash "
            f"{source_hash}, found {post_render_hash}."
        )
        record_scene_isolation_violation(job_id, scene_name, scene_file, [scene_name], reason)
        return False, reason
    return result


def find_rendered_video(
    work_dir: Path,
    scene_name: str,
    render_tier: "RenderTier | None" = None,
) -> "Path | None":
    """Find the most recently rendered video for *scene_name* in *work_dir*.

    When *render_tier* is given, searches inside the tier-specific media
    sub-directory (``media_<tier.name>/``); otherwise falls back to the default
    ``media/`` directory and then any ``media_*/`` sub-directory.
    """
    if render_tier is not None:
        media_dirs = [work_dir / f"media_{render_tier.name}" / "videos"]
    else:
        media_dirs = [work_dir / "media" / "videos"] + [
            d / "videos" for d in work_dir.glob("media_*") if d.is_dir()
        ]
    candidates: list[Path] = []
    for media_dir in media_dirs:
        if media_dir.exists():
            candidates.extend(media_dir.rglob(f"{scene_name}.mp4"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def output_video_path_for_job(job: Job) -> "Path | None":
    if job.output_video_url and job.output_video_url.startswith("/outputs/"):
        candidate = OUTPUT_DIR / job.output_video_url.removeprefix("/outputs/")
        if candidate.exists():
            return candidate
    if job.scene_name:
        for root in (WORK_ROOT, LEGACY_WORK_ROOT):
            work_dir = root / job.id
            final_candidates = list(work_dir.glob(f"{job.scene_name}_FINAL.mp4"))
            if final_candidates:
                return max(final_candidates, key=lambda path: path.stat().st_mtime)
            rendered = find_rendered_video(work_dir, job.scene_name)
            if rendered:
                return rendered
    return None



def scene_file_for_job(job: Job) -> Path | None:
    if not job.scene_name:
        return None
    scene_name = safe_scene_name(job.scene_name)
    for root in (WORK_ROOT, LEGACY_WORK_ROOT):
        work_dir = root / job.id
        candidate = work_dir / f"{scene_name}.py"
        if candidate.exists():
            validate_scene_file_isolation(
                job.id,
                scene_name,
                candidate,
                work_dir,
                root=root,
                write_manifest=False,
            )
            return candidate
    if job.generated_code:
        return write_job_scene_file(job.id, scene_name, job.generated_code)
    return None


def extract_frame_at(video_path: Path, timestamp: float, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(out_path),
        ]
    )


def beat_thumbnail_url(
    job_id: str,
    beat: StoryboardBeat,
    video_path: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> str:
    start = beat.start_sec if start_sec is None else max(0.0, float(start_sec))
    end = beat.end_sec if end_sec is None else max(start, float(end_sec))
    duration = max(0.0, end - start)
    timestamp = start + max(0.05, min(duration * 0.5, max(0.05, duration - 0.05)))
    out_name = f"{job_id}_beat_{beat.index:02d}.png"
    out_path = OUTPUT_DIR / out_name
    if not out_path.exists():
        extract_frame_at(video_path, timestamp, out_path)
    return f"/outputs/{out_name}"


def atempo_filter(ratio: float) -> str:
    filters: list[str] = []
    remaining = ratio
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def stretch_audio_to_duration(audio_path: Path, target_duration: float, out_path: Path) -> None:
    current = get_media_duration(audio_path)
    ratio = current / target_duration
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-filter:a",
            atempo_filter(ratio),
            str(out_path),
        ]
    )


def mux_audio_video(video_path: Path, audio_path: Path, out_path: Path) -> None:
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(out_path),
        ]
    )


def safe_scene_name(scene_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", scene_name or ""):
        raise ValueError("scene_name must be a valid Python class name.")
    return scene_name


def run_pipeline_for_job(
    job_id: str,
    storyboard: str,
    scene_name: str,
    orientation: Orientation = "portrait",
    max_target_seconds: int = MAX_TARGET_SECONDS,
) -> None:
    db = SessionLocal()
    beats: list[StoryboardBeat] = []
    scene_name_for_learning = scene_name
    try:
        storyboard = paginate_dense_storyboard_beats(normalize_generated_text(storyboard))
        job = db.get(Job, job_id)
        if job is not None:
            job.storyboard = storyboard
            db.commit()
        scene_name = safe_scene_name(scene_name)
        scene_name_for_learning = scene_name
        if orientation not in {"portrait", "landscape"}:
            raise ValueError("orientation must be portrait or landscape.")
        beats = validate_storyboard_or_raise(storyboard, max_target_seconds=max_target_seconds)

        work_dir = WORK_ROOT / job_id
        reset_job_render_workspace(work_dir, job_id)
        debug_log_path = work_dir / "debug_timing.log"
        log_debug_timing(debug_log_path, f"JOB_START job_id={job_id} scene={scene_name} orientation={orientation}")

        update_job(
            db,
            job_id,
            status=JobStatus.generating_voiceover,
            progress_message="Generating one voiceover clip per storyboard beat.",
        )
        with timed_stage(debug_log_path, "tts_generation_total"):
            timed_beats = generate_timed_beat_audio(beats, work_dir / "audio", debug_log_path, db, job_id)
        audio_track = work_dir / f"{scene_name}_beats.mp3"
        with timed_stage(debug_log_path, "audio_concatenate"):
            concatenate_audio(timed_beats, work_dir / "audio", audio_track)

        scene_file = work_dir / f"{scene_name}.py"
        error_feedback: str | None = None
        previous_code: str | None = None
        last_attempt_error: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            attempt_start_time = time.monotonic()
            provider = provider_for_job(db, job_id, attempt)
            log_debug_timing(debug_log_path, f"ATTEMPT_START attempt={attempt}/{MAX_RETRIES}")
            try:
                ensure_attempt_time_remaining(attempt_start_time, attempt)
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code if attempt == 1 else JobStatus.retrying,
                    progress_message=f"Generating Manim code for attempt {attempt}/{MAX_RETRIES}.",
                    attempt_number=attempt,
                )
                code = generate_valid_manim_code(
                    db=db,
                    job_id=job_id,
                    provider=provider,
                    storyboard=storyboard,
                    scene_name=scene_name,
                    timed_beats=timed_beats,
                    orientation=orientation,
                    attempt_start_time=attempt_start_time,
                    render_attempt=attempt,
                    render_error_feedback=error_feedback,
                    previous_render_code=previous_code,
                    debug_log_path=debug_log_path,
                )

                ensure_attempt_time_remaining(attempt_start_time, attempt)
                scene_file = write_job_scene_file(job_id, scene_name, code)
                persist_generated_code(db, job_id, code)

                update_job(
                    db,
                    job_id,
                    status=JobStatus.rendering,
                    progress_message=f"Rendering attempt {attempt}/{MAX_RETRIES}.",
                    attempt_number=attempt,
                    error=None,
                )
                render_started = time.monotonic()
                with timed_stage(debug_log_path, f"render_attempt_{attempt}_initial"):
                    render_ok, render_output = render_scene_for_job(
                        job_id,
                        scene_file,
                        scene_name,
                        work_dir,
                        orientation,
                        timeout_seconds=remaining_attempt_seconds(attempt_start_time, attempt),
                    )
                record_render_compute_cost(db, job_id, time.monotonic() - render_started)
                if not render_ok:
                    error_feedback = render_output[-4000:]
                    previous_code = code
                    update_job(
                        db,
                        job_id,
                        status=JobStatus.retrying,
                        progress_message=f"Render failed on attempt {attempt}/{MAX_RETRIES}; preparing retry.",
                        error=error_feedback,
                    )
                    continue

                video_path = find_rendered_video(work_dir, scene_name)
                if not video_path:
                    error_feedback = "Manim reported success, but no rendered mp4 was found under media/videos."
                    previous_code = code
                    update_job(
                        db,
                        job_id,
                        status=JobStatus.retrying,
                        progress_message=f"Attempt {attempt}/{MAX_RETRIES} did not produce an mp4; preparing retry.",
                        error=error_feedback,
                    )
                    continue

                ensure_attempt_time_remaining(attempt_start_time, attempt)
                target_duration = planned_total_duration(timed_beats)
                with timed_stage(debug_log_path, f"video_duration_probe_attempt_{attempt}"):
                    video_duration = get_media_duration(video_path)
                drift = abs(video_duration - target_duration)
                if target_duration > 0 and drift / target_duration > DRIFT_FAILURE_RATIO:
                    error_feedback = (
                        f"Rendered total duration was {video_duration:.2f}s, but the timing table target was "
                        f"{target_duration:.2f}s. Adjust the Beat sections' run_time and wait calls to reduce "
                        "the timing drift."
                    )
                    previous_code = code
                    update_job(
                        db,
                        job_id,
                        status=JobStatus.retrying,
                        progress_message=f"Timing drift exceeded limit on attempt {attempt}/{MAX_RETRIES}; preparing retry.",
                        error=error_feedback,
                    )
                    continue

                validation_retry = 0
                current_code = code
                current_video_path = video_path
                while True:
                    ensure_attempt_time_remaining(attempt_start_time, attempt)
                    update_job(
                        db,
                        job_id,
                        status=JobStatus.rendering,
                        progress_message="Checking sampled frames for visible boundary overflow.",
                    )
                    if current_video_path is None:
                        if validation_retry >= OVERLAP_RETRY_LIMIT:
                            raise AttemptFailed(error_feedback or "Render retry budget exhausted during validation repair.")
                        validation_retry += 1
                        previous_code = current_code
                        update_job(
                            db,
                            job_id,
                            status=JobStatus.retrying,
                            progress_message=(
                                f"Validation retry {validation_retry}/{OVERLAP_RETRY_LIMIT} for attempt {attempt}/{MAX_RETRIES}. "
                                "Patch only the affected beat section."
                            ),
                            error=error_feedback,
                        )
                        with timed_stage(debug_log_path, f"beat_patch_sub_retry_{attempt}_{validation_retry}_codegen"):
                            current_code = generate_valid_manim_code(
                                db=db,
                                job_id=job_id,
                                provider=provider,
                                storyboard=storyboard,
                                scene_name=scene_name,
                                timed_beats=timed_beats,
                                orientation=orientation,
                                attempt_start_time=attempt_start_time,
                                render_attempt=attempt,
                                render_error_feedback=error_feedback,
                                previous_render_code=previous_code,
                                debug_log_path=debug_log_path,
                            )
                        ensure_attempt_time_remaining(attempt_start_time, attempt)
                        scene_file = write_job_scene_file(job_id, scene_name, current_code)
                        persist_generated_code(db, job_id, current_code)

                        render_started = time.monotonic()
                        with timed_stage(debug_log_path, f"render_attempt_{attempt}_validation_retry_{validation_retry}"):
                            render_ok, render_output = render_scene_for_job(
                                job_id,
                                scene_file,
                                scene_name,
                                work_dir,
                                orientation,
                                timeout_seconds=remaining_attempt_seconds(attempt_start_time, attempt),
                            )
                        record_render_compute_cost(db, job_id, time.monotonic() - render_started)
                        if not render_ok:
                            error_feedback = render_output[-4000:]
                            current_video_path = None
                            continue

                        current_video_path = find_rendered_video(work_dir, scene_name)
                        if not current_video_path:
                            error_feedback = "Manim reported success, but no rendered mp4 was found under media/videos."
                        continue

                    lifecycle_feedback = text_lifecycle_feedback(beats, current_code)
                    if lifecycle_feedback:
                        error_feedback = lifecycle_feedback
                        if validation_retry >= OVERLAP_RETRY_LIMIT:
                            raise AttemptFailed(error_feedback)
                    else:
                        if not should_run_vision_quality_check(job_id):
                            log_debug_timing(
                                debug_log_path,
                                f"VISION_QUALITY_SKIPPED attempt={attempt} retry={validation_retry} mode={VISION_QUALITY_CHECK_MODE}",
                            )
                            break
                        try:
                            with timed_stage(debug_log_path, f"frame_quality_scan_attempt_{attempt}_retry_{validation_retry}"):
                                quality_findings = assess_video_quality(
                                    provider,
                                    current_video_path,
                                    beats,
                                    work_dir / "quality_samples",
                                    db,
                                    job_id,
                                )
                        except ProviderUnavailableError as exc:
                            quality_findings = []
                            log_debug_timing(debug_log_path, f"VISION_QUALITY_SKIPPED provider_unavailable={exc}")
                        if not quality_findings:
                            if validation_retry > 0 and error_feedback:
                                stage_failure_fix(
                                    job_id=job_id,
                                    scene_name=scene_name,
                                    beat_number=beat_number_from_feedback(error_feedback),
                                    failure_feedback=error_feedback,
                                    fixed_code=current_code,
                                )
                            break

                        error_feedback = build_quality_feedback(quality_findings[0])
                        if validation_retry >= OVERLAP_RETRY_LIMIT:
                            raise AttemptFailed(error_feedback)

                    validation_retry += 1
                    previous_code = current_code
                    update_job(
                        db,
                        job_id,
                        status=JobStatus.retrying,
                        progress_message=(
                            f"Validation retry {validation_retry}/{OVERLAP_RETRY_LIMIT} for attempt {attempt}/{MAX_RETRIES}. "
                            "Patch only the affected beat section."
                        ),
                        error=error_feedback,
                    )
                    with timed_stage(debug_log_path, f"beat_patch_sub_retry_{attempt}_{validation_retry}_codegen"):
                        current_code = generate_valid_manim_code(
                            db=db,
                            job_id=job_id,
                            provider=provider,
                            storyboard=storyboard,
                            scene_name=scene_name,
                            timed_beats=timed_beats,
                            orientation=orientation,
                            attempt_start_time=attempt_start_time,
                            render_attempt=attempt,
                            render_error_feedback=error_feedback,
                            previous_render_code=previous_code,
                            debug_log_path=debug_log_path,
                        )
                    ensure_attempt_time_remaining(attempt_start_time, attempt)
                    scene_file = write_job_scene_file(job_id, scene_name, current_code)
                    persist_generated_code(db, job_id, current_code)

                    render_started = time.monotonic()
                    with timed_stage(debug_log_path, f"render_attempt_{attempt}_validation_retry_{validation_retry}"):
                        render_ok, render_output = render_scene_for_job(
                            job_id,
                            scene_file,
                            scene_name,
                            work_dir,
                            orientation,
                            timeout_seconds=remaining_attempt_seconds(attempt_start_time, attempt),
                        )
                    record_render_compute_cost(db, job_id, time.monotonic() - render_started)
                    if not render_ok:
                        current_video_path = None
                        error_feedback = render_output[-4000:]
                        continue

                    current_video_path = find_rendered_video(work_dir, scene_name)
                    if not current_video_path:
                        error_feedback = "Manim reported success, but no rendered mp4 was found under media/videos."
                        continue

                video_path = current_video_path
                ensure_attempt_time_remaining(attempt_start_time, attempt)
                with timed_stage(debug_log_path, f"video_duration_probe_attempt_{attempt}_accepted"):
                    video_duration = get_media_duration(video_path)

                update_job(
                    db,
                    job_id,
                    status=JobStatus.muxing,
                    progress_message="Applying residual audio timing correction and muxing final video.",
                )
                corrected_audio = work_dir / f"{scene_name}_audio_corrected.mp3"
                with timed_stage(debug_log_path, "audio_residual_stretch"):
                    stretch_audio_to_duration(audio_track, video_duration, corrected_audio)
                final_path = work_dir / f"{scene_name}_FINAL.mp4"
                with timed_stage(debug_log_path, "mux_audio_video"):
                    mux_audio_video(video_path, corrected_audio, final_path)
                with timed_stage(debug_log_path, "storage_upload"):
                    output_url = upload_video(final_path, job_id)

                job_for_learning = db.get(Job, job_id)
                quality_scores = list(job_for_learning.quality_scores or []) if job_for_learning else []
                stage_verified_reference_examples(
                    job_id=job_id,
                    scene_name=scene_name,
                    storyboard=storyboard,
                    beats=learning_beats_from_storyboard(beats),
                    code=current_code,
                    quality_scores=quality_scores,
                    quality_threshold=QUALITY_SCORE_THRESHOLD,
                )
                record_job_category_events(
                    job_id=job_id,
                    scene_name=scene_name,
                    beats=learning_beats_from_storyboard(beats),
                    outcome="success",
                    retry_count=max(0, attempt - 1),
                )

                update_job(
                    db,
                    job_id,
                    status=JobStatus.complete,
                    progress_message="Video generation complete.",
                    error=None,
                    output_video_url=output_url,
                )
                log_debug_timing(debug_log_path, f"JOB_COMPLETE job_id={job_id}")
                return
            except (AttemptFailed, TimeoutError) as exc:
                last_attempt_error = str(exc)
                timeout_failure = isinstance(exc, TimeoutError)
                update_job(
                    db,
                    job_id,
                    status=JobStatus.retrying,
                    progress_message=(
                        f"Attempt {attempt}/{MAX_RETRIES} "
                        + (
                            f"exceeded the wall-clock limit of {ATTEMPT_WALL_CLOCK_LIMIT_SECONDS // 60} minutes"
                            if timeout_failure
                            else "exhausted its inner retry budget"
                        )
                        + "; moving to the next attempt."
                    ),
                    error=last_attempt_error,
                )
                previous_code = None
                error_feedback = None
                log_debug_timing(debug_log_path, f"ATTEMPT_FAILED attempt={attempt} reason={last_attempt_error}")
                continue
        raise RuntimeError(f"All {MAX_RETRIES} attempts failed. Last feedback: {last_attempt_error or error_feedback}")
    except RateLimitExhausted as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Video generation failed due to provider rate limiting.",
            error=str(exc),
        )
    except Exception as exc:
        if beats:
            record_job_category_events(
                job_id=job_id,
                scene_name=scene_name_for_learning,
                beats=learning_beats_from_storyboard(beats),
                outcome="failure",
                retry_count=MAX_RETRIES,
            )
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Video generation failed.",
            error=str(exc),
        )
    finally:
        db.close()


def run_topic_pipeline_for_job(
    job_id: str,
    topic: str,
    duration_seconds: int,
    audience: str,
    scene_name: str,
    orientation: Orientation = "portrait",
    pipeline_profile: str = "legacy",
) -> None:
    db = SessionLocal()
    try:
        update_job(
            db,
            job_id,
            status=JobStatus.generating_code,
            progress_message="Drafting storyboard from topic.",
        )
        provider = provider_for_job(db, job_id)
        draft_kwargs = {"db": db, "job_id": job_id}
        if "provider" in inspect.signature(generate_storyboard_draft).parameters:
            draft_kwargs["provider"] = provider
        draft = generate_storyboard_draft(topic, duration_seconds, audience, **draft_kwargs)
        storyboard = draft["storyboard"]
        validate_storyboard_or_raise(storyboard, max_target_seconds=TOPIC_MAX_TARGET_SECONDS)
        coverage = validate_generated_storyboard_integrity(topic, storyboard)
        write_storyboard_topic_coverage_audit(job_id, 0, coverage)
        write_generated_storyboard_audit(job_id, storyboard)

        job = db.get(Job, job_id)
        if job is not None:
            job.storyboard = storyboard
            job.generated_storyboard = storyboard
            job.scene_name = scene_name
            job.orientation = orientation
            payload = dict(job.request_payload or {})
            payload["main_instance"] = draft.get("main_instance", "")
            payload["recall_instance"] = draft.get("recall_instance", {})
            payload["recall_question"] = draft.get("recall_question", {})
            job.request_payload = payload
            job.cost_breakdown = draft.get("cost_breakdown", job.cost_breakdown or {})
            job.estimated_cost_usd = float(draft.get("estimated_cost_usd", job.estimated_cost_usd or 0.0))
            db.commit()
    except Exception as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Topic storyboard generation failed.",
            error=str(exc),
        )
        return
    finally:
        db.close()

    if pipeline_profile == "craft":
        from app.craft_pipeline import run_craft_pipeline_for_job
        from app.pipeline import (
            parse_storyboard, WORK_ROOT, find_rendered_video, upload_video,
            RENDER_TIER_3_PRODUCTION,
        )

        beats = parse_storyboard(storyboard)
        work_dir = WORK_ROOT / job_id
        debug_log_path = work_dir / "debug_timing.log"
        run_craft_pipeline_for_job(job_id, db, work_dir, provider, job, beats, debug_log_path)

        video_name = f"CraftScene_{job_id.replace('-', '_')}"
        # Search Tier-3 production directory first; fall back to any media directory
        video_path = find_rendered_video(work_dir, video_name, render_tier=RENDER_TIER_3_PRODUCTION)
        if video_path is None:
            video_path = find_rendered_video(work_dir, video_name)
        if video_path is None:
            raise RuntimeError(f"Craft scene render output not found for {video_name}")

        output_url = upload_video(video_path, job_id)
        
        post_db = SessionLocal()
        try:
            update_job(
                post_db,
                job_id,
                status=JobStatus.complete,
                progress_message="Craft video generation complete.",
                error=None,
                output_video_url=output_url,
            )
        finally:
            post_db.close()
    elif pipeline_profile == "template":
        from app.template_pipeline import run_template_pipeline_for_job

        run_template_pipeline_for_job(
            job_id,
            storyboard,
            scene_name,
            orientation,
            max_target_seconds=TOPIC_MAX_TARGET_SECONDS,
        )
    else:
        run_pipeline_for_job(
            job_id,
            storyboard,
            scene_name,
            orientation,
            max_target_seconds=TOPIC_MAX_TARGET_SECONDS,
        )


def run_beat_regeneration_for_job(
    job_id: str,
    parent_job_id: str,
    beat_number: int,
    on_screen: str,
    vo_text: str,
) -> None:
    db = SessionLocal()
    try:
        parent = db.get(Job, parent_job_id)
        job = db.get(Job, job_id)
        if parent is None or job is None:
            raise RuntimeError("Original or edited job was not found.")
        if parent.status != JobStatus.complete:
            raise RuntimeError("Original job must be complete before beat regeneration.")
        if not parent.storyboard or not parent.scene_name:
            raise RuntimeError("Original job is missing storyboard metadata needed for beat regeneration.")

        scene_name = safe_scene_name(parent.scene_name)
        orientation = parent.orientation if parent.orientation in {"portrait", "landscape"} else "portrait"
        old_beats = validate_storyboard_or_raise(parent.storyboard)
        if beat_number < 1 or beat_number > len(old_beats):
            raise ValueError("Beat number is out of range.")

        old_beat = old_beats[beat_number - 1]
        new_vo = normalize_vo_text(vo_text)
        vo_changed = new_vo != old_beat.vo_text
        edited_storyboard = replace_storyboard_beat(parent.storyboard, beat_number, on_screen, vo_text)
        beats = validate_storyboard_or_raise(edited_storyboard)

        job.storyboard = edited_storyboard
        job.scene_name = scene_name
        job.orientation = orientation
        db.commit()

        parent_scene_file = scene_file_for_job(parent)
        if parent_scene_file is None:
            raise RuntimeError("Original job code file was not found.")
        parent_code = parent_scene_file.read_text(encoding="utf-8")
        parent_work_dir = WORK_ROOT / parent.id

        work_dir = WORK_ROOT / job_id
        reset_job_render_workspace(work_dir, job_id)
        debug_log_path = work_dir / "debug_timing.log"
        log_debug_timing(
            debug_log_path,
            f"JOB_START job_id={job_id} parent_job_id={parent_job_id} edited_beat={beat_number} orientation={orientation}",
        )

        update_job(
            db,
            job_id,
            status=JobStatus.generating_voiceover,
            progress_message=f"Preparing audio for edited Beat {beat_number}.",
        )
        with timed_stage(debug_log_path, "tts_generation_total"):
            timed_beats = generate_timed_beat_audio_for_edit(
                beats,
                parent_work_dir,
                work_dir / "audio",
                beat_number,
                vo_changed,
                debug_log_path,
                db,
                job_id,
            )
        audio_track = work_dir / f"{scene_name}_beats.mp3"
        with timed_stage(debug_log_path, "audio_concatenate"):
            concatenate_audio(timed_beats, work_dir / "audio", audio_track)

        scene_file = work_dir / f"{scene_name}.py"
        previous_code = parent_code
        error_feedback = (
            f"Beat {beat_number} was edited. Patch only the # --- Beat {beat_number} --- section to match "
            f"this new on-screen description and voiceover target. New on-screen: {on_screen.strip()}. "
            f"New VO: {vo_text.strip()}. Leave all other beat sections untouched."
        )
        last_error: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            attempt_start_time = time.monotonic()
            provider = provider_for_job(db, job_id, attempt)
            try:
                update_job(
                    db,
                    job_id,
                    status=JobStatus.generating_code if attempt == 1 else JobStatus.retrying,
                    progress_message=f"Patching Beat {beat_number} code for attempt {attempt}/{MAX_RETRIES}.",
                    attempt_number=attempt,
                )
                with timed_stage(debug_log_path, f"beat_edit_codegen_attempt_{attempt}"):
                    code = generate_valid_manim_code(
                        db=db,
                        job_id=job_id,
                        provider=provider,
                        storyboard=edited_storyboard,
                        scene_name=scene_name,
                        timed_beats=timed_beats,
                        orientation=orientation,  # type: ignore[arg-type]
                        attempt_start_time=attempt_start_time,
                        render_attempt=attempt,
                        render_error_feedback=error_feedback,
                        previous_render_code=previous_code,
                        debug_log_path=debug_log_path,
                    )
                scene_file = write_job_scene_file(job_id, scene_name, code)
                persist_generated_code(db, job_id, code)

                update_job(
                    db,
                    job_id,
                    status=JobStatus.rendering,
                    progress_message=f"Rendering edited Beat {beat_number}, attempt {attempt}/{MAX_RETRIES}.",
                    attempt_number=attempt,
                    error=None,
                )
                render_started = time.monotonic()
                with timed_stage(debug_log_path, f"render_attempt_{attempt}"):
                    render_ok, render_output = render_scene_for_job(
                        job_id,
                        scene_file,
                        scene_name,
                        work_dir,
                        orientation,  # type: ignore[arg-type]
                        timeout_seconds=remaining_attempt_seconds(attempt_start_time, attempt),
                    )
                record_render_compute_cost(db, job_id, time.monotonic() - render_started)
                if not render_ok:
                    last_error = render_output[-4000:]
                    previous_code = code
                    error_feedback = (
                        f"The Beat {beat_number} edit render failed. Patch only the # --- Beat {beat_number} --- "
                        f"section unless the traceback points elsewhere.\n\n{last_error}"
                    )
                    continue

                video_path = find_rendered_video(work_dir, scene_name)
                if not video_path:
                    last_error = "Manim reported success, but no rendered mp4 was found under media/videos."
                    previous_code = code
                    error_feedback = last_error
                    continue

                if should_run_vision_quality_check(job_id):
                    try:
                        with timed_stage(debug_log_path, f"frame_quality_scan_attempt_{attempt}"):
                            quality_findings = assess_video_quality(
                                provider,
                                video_path,
                                beats,
                                work_dir / "quality_samples",
                                db,
                                job_id,
                            )
                    except ProviderUnavailableError as exc:
                        quality_findings = []
                        log_debug_timing(debug_log_path, f"VISION_QUALITY_SKIPPED provider_unavailable={exc}")
                    if quality_findings:
                        last_error = build_quality_feedback(quality_findings[0])
                        previous_code = code
                        error_feedback = last_error
                        continue
                else:
                    log_debug_timing(debug_log_path, f"VISION_QUALITY_SKIPPED attempt={attempt} mode={VISION_QUALITY_CHECK_MODE}")

                with timed_stage(debug_log_path, f"video_duration_probe_attempt_{attempt}"):
                    video_duration = get_media_duration(video_path)

                update_job(
                    db,
                    job_id,
                    status=JobStatus.muxing,
                    progress_message=f"Muxing edited Beat {beat_number} version.",
                )
                corrected_audio = work_dir / f"{scene_name}_audio_corrected.mp3"
                with timed_stage(debug_log_path, "audio_residual_stretch"):
                    stretch_audio_to_duration(audio_track, video_duration, corrected_audio)
                final_path = work_dir / f"{scene_name}_FINAL.mp4"
                with timed_stage(debug_log_path, "mux_audio_video"):
                    mux_audio_video(video_path, corrected_audio, final_path)
                with timed_stage(debug_log_path, "storage_upload"):
                    output_url = upload_video(final_path, job_id)

                update_job(
                    db,
                    job_id,
                    status=JobStatus.complete,
                    progress_message=f"Edited Beat {beat_number} video generation complete.",
                    error=None,
                    output_video_url=output_url,
                )
                log_debug_timing(debug_log_path, f"JOB_COMPLETE job_id={job_id}")
                return
            except (AttemptFailed, TimeoutError) as exc:
                last_error = str(exc)
                previous_code = parent_code
                error_feedback = (
                    f"Beat {beat_number} edit attempt {attempt} failed. Start again from the original code and "
                    f"patch only the # --- Beat {beat_number} --- section. Failure: {last_error}"
                )
                update_job(
                    db,
                    job_id,
                    status=JobStatus.retrying,
                    progress_message=f"Edited Beat {beat_number} attempt {attempt}/{MAX_RETRIES} failed; preparing retry.",
                    error=last_error,
                )
                continue

        raise RuntimeError(f"Edited Beat {beat_number} regeneration failed after {MAX_RETRIES} attempts. {last_error or ''}")
    except RateLimitExhausted as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Beat regeneration failed due to provider rate limiting.",
            error=str(exc),
        )
    except Exception as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Beat regeneration failed.",
            error=str(exc),
        )
    finally:
        db.close()


def run_beat_param_render_for_job(
    job_id: str,
    parent_job_id: str,
    beat_number: int,
    params: dict[str, float],
) -> None:
    db = SessionLocal()
    try:
        parent = db.get(Job, parent_job_id)
        job = db.get(Job, job_id)
        if parent is None or job is None:
            raise RuntimeError("Original or parameter-edit job was not found.")
        if parent.status != JobStatus.complete:
            raise RuntimeError("Original job must be complete before beat parameter editing.")
        if not parent.scene_name or not parent.storyboard:
            raise RuntimeError("Original job is missing scene metadata.")

        scene_name = safe_scene_name(parent.scene_name)
        orientation = parent.orientation if parent.orientation in {"portrait", "landscape"} else "portrait"
        provider = provider_for_job(db, job_id)
        beats = validate_storyboard_or_raise(parent.storyboard)
        parent_scene_file = scene_file_for_job(parent)
        if parent_scene_file is None:
            raise RuntimeError("Original job code file was not found.")
        parent_code = parent_scene_file.read_text(encoding="utf-8")
        patched_code = patch_beat_params_in_code(parent_code, beat_number, params)

        parent_work_dir = WORK_ROOT / parent.id
        parent_audio_track = parent_work_dir / f"{scene_name}_beats.mp3"

        job.storyboard = parent.storyboard
        job.generated_storyboard = parent.generated_storyboard
        job.scene_name = scene_name
        job.orientation = orientation
        db.commit()
        record_render_only_edit(db, job_id)

        work_dir = WORK_ROOT / job_id
        reset_job_render_workspace(work_dir, job_id)
        debug_log_path = work_dir / "debug_timing.log"
        log_debug_timing(
            debug_log_path,
            f"JOB_START job_id={job_id} parent_job_id={parent_job_id} beat_param_edit={beat_number} orientation={orientation}",
        )

        scene_file = write_job_scene_file(job_id, scene_name, patched_code)
        persist_generated_code(db, job_id, patched_code)
        audio_track = work_dir / f"{scene_name}_beats.mp3"
        if parent_audio_track.exists():
            shutil.copy2(parent_audio_track, audio_track)
        else:
            with timed_stage(debug_log_path, "audio_rebuild_for_render_only_edit"):
                timed_beats = generate_timed_beat_audio(beats, work_dir / "audio", debug_log_path, db, job_id)
                concatenate_audio(timed_beats, work_dir / "audio", audio_track)

        update_job(
            db,
            job_id,
            status=JobStatus.rendering,
            progress_message=f"Rendering Beat {beat_number} parameter edit.",
            attempt_number=1,
            error=None,
        )
        render_started = time.monotonic()
        with timed_stage(debug_log_path, "render_only_param_edit"):
            render_ok, render_output = render_scene_for_job(
                job_id,
                scene_file,
                scene_name,
                work_dir,
                orientation,  # type: ignore[arg-type]
                timeout_seconds=ATTEMPT_WALL_CLOCK_LIMIT_SECONDS,
            )
        record_render_compute_cost(db, job_id, time.monotonic() - render_started)
        if not render_ok:
            raise RuntimeError(render_output[-4000:])

        video_path = find_rendered_video(work_dir, scene_name)
        if not video_path:
            raise RuntimeError("Manim reported success, but no rendered mp4 was found under media/videos.")

        if should_run_vision_quality_check(job_id):
            try:
                with timed_stage(debug_log_path, "frame_quality_scan_param_edit"):
                    quality_findings = assess_video_quality(provider, video_path, beats, work_dir / "quality_samples", db, job_id)
            except ProviderUnavailableError as exc:
                quality_findings = []
                log_debug_timing(debug_log_path, f"VISION_QUALITY_SKIPPED provider_unavailable={exc}")
            if quality_findings:
                raise RuntimeError(build_quality_feedback(quality_findings[0]))
        else:
            log_debug_timing(debug_log_path, f"VISION_QUALITY_SKIPPED param_edit mode={VISION_QUALITY_CHECK_MODE}")

        with timed_stage(debug_log_path, "video_duration_probe_param_edit"):
            video_duration = get_media_duration(video_path)

        update_job(
            db,
            job_id,
            status=JobStatus.muxing,
            progress_message=f"Muxing Beat {beat_number} parameter edit.",
        )
        corrected_audio = work_dir / f"{scene_name}_audio_corrected.mp3"
        with timed_stage(debug_log_path, "audio_residual_stretch"):
            stretch_audio_to_duration(audio_track, video_duration, corrected_audio)
        final_path = work_dir / f"{scene_name}_FINAL.mp4"
        with timed_stage(debug_log_path, "mux_audio_video"):
            mux_audio_video(video_path, corrected_audio, final_path)
        with timed_stage(debug_log_path, "storage_upload"):
            output_url = upload_video(final_path, job_id)

        update_job(
            db,
            job_id,
            status=JobStatus.complete,
            progress_message=f"Beat {beat_number} parameter edit complete.",
            error=None,
            output_video_url=output_url,
        )
        log_debug_timing(debug_log_path, f"JOB_COMPLETE job_id={job_id}")
    except Exception as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Beat parameter edit failed.",
            error=str(exc),
        )
    finally:
        db.close()
