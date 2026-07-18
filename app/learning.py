import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEARNING_MEMORY_DIR = Path(os.getenv("LEARNING_MEMORY_DIR", "learning_memory")).resolve()
STAGED_REFERENCES_PATH = LEARNING_MEMORY_DIR / "staged_reference_examples.jsonl"
APPROVED_REFERENCES_PATH = LEARNING_MEMORY_DIR / "approved_reference_examples.jsonl"
STAGED_FAILURES_PATH = LEARNING_MEMORY_DIR / "staged_failure_patterns.jsonl"
APPROVED_FAILURES_PATH = LEARNING_MEMORY_DIR / "approved_failure_patterns.jsonl"
CATEGORY_EVENTS_PATH = LEARNING_MEMORY_DIR / "category_success_events.jsonl"


@dataclass(frozen=True)
class LearningBeat:
    index: int
    on_screen_text: str


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_learning_dir() -> None:
    LEARNING_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_learning_dir()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def infer_learning_category(text: str) -> str:
    normalized = text.lower()
    category_keywords = {
        "force-diagram": (
            "force", "friction", "normal", "incline", "inclined", "block", "mg", "tension", "weight",
            "free body", "component", "acceleration",
        ),
        "curve-plot": (
            "curve", "graph", "plot", "axis", "axes", "sine", "cosine", "parabola", "function",
            "tangent", "slope",
        ),
        "algebraic-derivation": (
            "derive", "equation", "solve", "substitute", "simplify", "therefore", "series", "limit",
            "expansion", "transform", "becomes",
        ),
        "geometric-proof": (
            "triangle", "circle", "angle", "proof", "similar", "chord", "radius", "perpendicular",
            "theorem", "geometry",
        ),
    }
    scores = {
        category: sum(normalized.count(keyword) for keyword in keywords)
        for category, keywords in category_keywords.items()
    }
    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else "general-animation"


def code_section_for_beat(code: str, beat_number: int) -> str | None:
    markers = list(re.finditer(r"(?m)^#\s*---\s*Beat\s+(\d+)(?:\s+params\s*)?---\s*$", code))
    start_match = next((match for match in markers if int(match.group(1)) == beat_number), None)
    if not start_match:
        return None
    end = len(code)
    for marker in markers:
        if marker.start() <= start_match.start():
            continue
        if int(marker.group(1)) != beat_number:
            end = marker.start()
            break
    return code[start_match.start() : end].strip()


def quality_failed_for_beat(quality_scores: list[dict[str, Any]], beat_number: int, threshold: int) -> bool:
    for score in quality_scores:
        if int(score.get("beat_index", -1)) != beat_number:
            continue
        if int(score.get("accuracy", 5) or 0) < threshold:
            return True
        if int(score.get("element_layout", 5) or 0) < threshold:
            return True
    return False


def stage_verified_reference_examples(
    *,
    job_id: str,
    scene_name: str,
    storyboard: str,
    beats: list[LearningBeat],
    code: str,
    quality_scores: list[dict[str, Any]],
    quality_threshold: int,
) -> int:
    staged_count = 0
    for beat in beats:
        if quality_failed_for_beat(quality_scores, beat.index, quality_threshold):
            continue
        section = code_section_for_beat(code, beat.index)
        if not section:
            continue
        category = infer_learning_category(beat.on_screen_text)
        append_jsonl(
            STAGED_REFERENCES_PATH,
            {
                "created_at": utc_timestamp(),
                "job_id": job_id,
                "scene_name": scene_name,
                "beat_number": beat.index,
                "category": category,
                "on_screen_text": beat.on_screen_text,
                "storyboard_excerpt": storyboard[:2000],
                "code": section,
                "review_status": "staged",
            },
        )
        staged_count += 1
    return staged_count


def approved_reference_context(categories: list[str], max_examples: int = 2) -> str:
    approved = read_jsonl(APPROVED_REFERENCES_PATH)
    selected: list[str] = []
    category_set = set(categories)
    for record in reversed(approved):
        if record.get("category") not in category_set:
            continue
        code = str(record.get("code") or "").strip()
        if not code:
            continue
        selected.append(
            "# APPROVED LEARNED REFERENCE\n"
            f"# category: {record.get('category')}\n"
            f"# source_job_id: {record.get('job_id')}\n"
            f"{code}"
        )
        if len(selected) >= max_examples:
            break
    return "\n\n".join(reversed(selected))


def classify_failure_feedback(feedback: str | None) -> str:
    text = (feedback or "").lower()
    if "color" in text or "yellow_green" in text or "green_yellow" in text:
        return "invented-color-name"
    if "syntax" in text or "pure python" in text or "parse" in text:
        return "non-python-response"
    if "overlap" in text or "layout" in text or "spacing" in text or "frame" in text:
        return "layout-or-overlap"
    if "accuracy" in text or "equation" in text or "math" in text:
        return "math-accuracy"
    if "duration" in text or "timing" in text or "drift" in text:
        return "timing-drift"
    if "traceback" in text or "nameerror" in text or "typeerror" in text:
        return "render-traceback"
    return "general-generation-failure"


def stage_failure_fix(
    *,
    job_id: str,
    scene_name: str,
    beat_number: int | None,
    failure_feedback: str | None,
    fixed_code: str,
) -> None:
    error_type = classify_failure_feedback(failure_feedback)
    append_jsonl(
        STAGED_FAILURES_PATH,
        {
            "created_at": utc_timestamp(),
            "job_id": job_id,
            "scene_name": scene_name,
            "beat_number": beat_number,
            "category": error_type,
            "error_type": error_type,
            "failure_feedback": (failure_feedback or "")[:2000],
            "fix_applied": summarize_fix_from_code(fixed_code),
            "review_status": "staged",
        },
    )


def summarize_fix_from_code(code: str) -> str:
    signals = []
    if "ReplacementTransform" in code or "Transform(" in code:
        signals.append("uses Transform or ReplacementTransform for object continuity")
    if "FadeOut" in code:
        signals.append("removes prior mobjects before adding replacements")
    if "next_to" in code or "buff=" in code:
        signals.append("uses explicit spacing buffers")
    if "interpolate_color" in code or re.search(r"#[0-9A-Fa-f]{6}", code):
        signals.append("uses supported color expressions")
    if "run_time=" in code or "self.wait" in code:
        signals.append("uses explicit timing controls")
    return "; ".join(signals) if signals else "corrected generated scene code passed subsequent validation"


def approved_failure_instructions(storyboard: str, categories: list[str], max_patterns: int = 4) -> str:
    approved = read_jsonl(APPROVED_FAILURES_PATH)
    text = storyboard.lower()
    selected: list[str] = []
    category_set = set(categories)
    for record in reversed(approved):
        record_category = str(record.get("beat_category") or record.get("category") or "")
        failure_category = str(record.get("error_type") or record.get("category") or "")
        instruction = str(record.get("instruction") or record.get("fix_applied") or "").strip()
        keywords = [str(keyword).lower() for keyword in record.get("keywords", []) if str(keyword).strip()]
        category_match = record_category in category_set or failure_category in category_set
        keyword_match = bool(keywords and any(keyword in text for keyword in keywords))
        if not instruction or not (category_match or keyword_match):
            continue
        selected.append(f"- {failure_category}: {instruction}")
        if len(selected) >= max_patterns:
            break
    if not selected:
        return ""
    return "APPROVED FAILURE-PATTERN REMINDERS:\n" + "\n".join(reversed(selected))


def record_category_event(
    *,
    job_id: str,
    scene_name: str,
    beat_number: int,
    category: str,
    outcome: str,
    retry_count: int,
) -> None:
    append_jsonl(
        CATEGORY_EVENTS_PATH,
        {
            "created_at": utc_timestamp(),
            "job_id": job_id,
            "scene_name": scene_name,
            "beat_number": beat_number,
            "category": category,
            "outcome": outcome,
            "retry_count": retry_count,
        },
    )


def record_job_category_events(
    *,
    job_id: str,
    scene_name: str,
    beats: list[LearningBeat],
    outcome: str,
    retry_count: int,
) -> None:
    for beat in beats:
        record_category_event(
            job_id=job_id,
            scene_name=scene_name,
            beat_number=beat.index,
            category=infer_learning_category(beat.on_screen_text),
            outcome=outcome,
            retry_count=retry_count,
        )


def learning_summary(limit: int = 20) -> dict[str, Any]:
    events = read_jsonl(CATEGORY_EVENTS_PATH)
    summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"beats": 0, "successes": 0, "failures": 0, "first_attempt_successes": 0, "retry_count": 0}
    )
    for event in events[-limit * 20 :]:
        category = str(event.get("category") or "unknown")
        bucket = summary[category]
        bucket["beats"] += 1
        retry_count = int(event.get("retry_count", 0) or 0)
        bucket["retry_count"] += retry_count
        if event.get("outcome") == "success":
            bucket["successes"] += 1
            if retry_count == 0:
                bucket["first_attempt_successes"] += 1
        else:
            bucket["failures"] += 1

    categories = []
    for category, data in sorted(summary.items()):
        beats = max(1, int(data["beats"]))
        categories.append(
            {
                "category": category,
                "beats": data["beats"],
                "successes": data["successes"],
                "failures": data["failures"],
                "first_attempt_success_rate": data["first_attempt_successes"] / beats,
                "average_retry_count": data["retry_count"] / beats,
            }
        )

    return {
        "learning_memory_dir": str(LEARNING_MEMORY_DIR),
        "staged_reference_examples": len(read_jsonl(STAGED_REFERENCES_PATH)),
        "approved_reference_examples": len(read_jsonl(APPROVED_REFERENCES_PATH)),
        "staged_failure_patterns": len(read_jsonl(STAGED_FAILURES_PATH)),
        "approved_failure_patterns": len(read_jsonl(APPROVED_FAILURES_PATH)),
        "categories": categories,
    }
