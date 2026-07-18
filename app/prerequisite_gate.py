"""Prerequisite gate — resolves syllabus prerequisites before script generation (§2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
PREREQUISITES_PATH = REPO_ROOT / "data" / "topic_prerequisites.json"

ExamContext = str  # "JEE Main" | "JEE Advanced" | "NEET"


class StudentSignal(BaseModel):
    self_rated_confidence: int = Field(..., ge=1, le=5)
    flagged_as_weak_topic: bool
    prior_attempt_count: int = Field(0, ge=0)
    unconfirmed_prerequisites: list[str] = Field(default_factory=list)


class TopicPrerequisites(BaseModel):
    topic_id: str
    prerequisites: list[str] = Field(default_factory=list)


def load_topic_prerequisites(topic_id: str) -> TopicPrerequisites:
    """Load authored prerequisites for one topic; never infer them with an LLM."""
    catalog = load_prerequisites_catalog()
    normalized = normalize_topic_key(topic_id)
    for exam_map in catalog.values():
        for authored_topic, prerequisites in exam_map.items():
            if normalize_topic_key(authored_topic) == normalized:
                return TopicPrerequisites(topic_id=topic_id, prerequisites=list(prerequisites))
    # TODO: author prerequisite data per topic
    return TopicPrerequisites(topic_id=topic_id, prerequisites=[])


@dataclass(frozen=True)
class PrerequisiteConfidence:
    concept: str
    confident: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PrerequisiteConfidence:
        return cls(
            concept=str(raw.get("concept", "")).strip(),
            confident=bool(raw.get("confident", True)),
        )


@dataclass(frozen=True)
class PrerequisiteGateResult:
    """Output of the prerequisite gate before script generation."""

    topic: str
    exam_context: str
    syllabus_prerequisites: list[str]
    unconfirmed_prerequisites: list[str]
    insert_refresher: bool
    flagged_as_weak_topic: bool
    prior_attempt_count: int
    self_rated_confidence: int

    def to_prompt_context(self) -> dict[str, Any]:
        return {
            "exam_context": self.exam_context,
            "flagged_as_weak_topic": self.flagged_as_weak_topic,
            "unconfirmed_prerequisites": self.unconfirmed_prerequisites,
            "prior_attempt_count": self.prior_attempt_count,
            "self_rated_confidence": self.self_rated_confidence,
        }


def normalize_topic_key(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().lower())


@lru_cache(maxsize=1)
def load_prerequisites_catalog() -> dict[str, dict[str, list[str]]]:
    if not PREREQUISITES_PATH.is_file():
        return {}
    return json.loads(PREREQUISITES_PATH.read_text(encoding="utf-8"))


def lookup_syllabus_prerequisites(topic: str, exam_context: str) -> list[str]:
    """Content-authoring lookup: which concepts the syllabus assumes for this topic."""
    catalog = load_prerequisites_catalog()
    exam_map = catalog.get(exam_context, {})
    normalized = normalize_topic_key(topic)

    # Exact match first
    for key, concepts in exam_map.items():
        if normalize_topic_key(key) == normalized:
            return list(concepts)

    # Substring match — topic contains catalog key or vice versa
    for key, concepts in exam_map.items():
        key_norm = normalize_topic_key(key)
        if key_norm in normalized or normalized in key_norm:
            return list(concepts)

    return []


def resolve_prerequisite_gate(
    student_signal: StudentSignal,
    topic_prereqs: TopicPrerequisites,
) -> list[str]:
    """Return authored prerequisites the student has explicitly not confirmed."""
    authored = {normalize_topic_key(item): item for item in topic_prereqs.prerequisites}
    return [
        authored[normalize_topic_key(item)]
        for item in student_signal.unconfirmed_prerequisites
        if normalize_topic_key(item) in authored
    ]


def resolve_prerequisite_gate_result(
    *,
    topic: str,
    exam_context: str | None = None,
    audience: str | None = None,
    assumed_prerequisites: list[PrerequisiteConfidence] | list[dict[str, Any]] | None = None,
    flagged_as_weak_topic: bool = False,
    prior_attempt_count: int = 0,
    self_rated_confidence: int = 3,
    explicit_unconfirmed: list[str] | None = None,
) -> PrerequisiteGateResult:
    """
    §2 prerequisite gate — runs before script generation.

    If the student marked any syllabus prerequisite as not confident, unconfirmed_prerequisites
    is non-empty and insert_refresher is True.
    """
    resolved_exam = exam_context or infer_exam_context(audience) or "JEE Main"
    syllabus = lookup_syllabus_prerequisites(topic, resolved_exam)

    confidence_items: list[PrerequisiteConfidence] = []
    if explicit_unconfirmed is not None:
        unconfirmed = list(explicit_unconfirmed)
    elif assumed_prerequisites:
        for item in assumed_prerequisites:
            if isinstance(item, PrerequisiteConfidence):
                confidence_items.append(item)
            elif isinstance(item, dict):
                confidence_items.append(PrerequisiteConfidence.from_dict(item))
            elif isinstance(item, str):
                confidence_items.append(PrerequisiteConfidence(concept=item, confident=False))

    if explicit_unconfirmed is None:
        if confidence_items:
            # Frontend sent explicit confidence flags — use those.
            unconfirmed = [p.concept for p in confidence_items if p.concept and not p.confident]
        else:
            # No frontend input — gate passes with no refresher (backward compatible).
            unconfirmed = []

    return PrerequisiteGateResult(
        topic=topic.strip(),
        exam_context=resolved_exam,
        syllabus_prerequisites=syllabus,
        unconfirmed_prerequisites=unconfirmed,
        insert_refresher=bool(unconfirmed),
        flagged_as_weak_topic=flagged_as_weak_topic,
        prior_attempt_count=max(0, prior_attempt_count),
        self_rated_confidence=max(1, min(5, self_rated_confidence)),
    )


def infer_exam_context(audience: str | None) -> str | None:
    if not audience:
        return None
    lower = audience.lower()
    if "neet" in lower:
        return "NEET"
    if "advanced" in lower:
        return "JEE Advanced"
    if "jee" in lower or "main" in lower:
        return "JEE Main"
    return None


def default_prerequisite_checklist(topic: str, exam_context: str) -> list[dict[str, Any]]:
    """API helper: return syllabus prerequisites as checkbox items for the frontend."""
    concepts = lookup_syllabus_prerequisites(topic, exam_context)
    return [{"concept": concept, "confident": True} for concept in concepts]
