"""§6 QA checklist — run against every generated storyboard before render."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.prerequisite_gate import PrerequisiteGateResult
from app.vivacity_prompts import FORBIDDEN_NARRATION_WORDS, RECALL_CHECKPOINT_TAG


@dataclass
class QACheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class MasterPipelineQAReport:
    passed: bool
    checks: list[QACheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def _extract_vo_text(storyboard: str) -> str:
    parts: list[str] = []
    for match in re.finditer(r'VO:\s*"([^"]*)"', storyboard, re.IGNORECASE):
        parts.append(match.group(1))
    return " ".join(parts)


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", text))


def _first_concrete_beat(storyboard: str) -> str:
    for line in storyboard.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if RECALL_CHECKPOINT_TAG in stripped:
            continue
        if "ON SCREEN:" in stripped:
            return stripped
    return ""


def _recall_checkpoint_beat(storyboard: str) -> str:
    for line in storyboard.splitlines():
        if RECALL_CHECKPOINT_TAG in line:
            return line.strip()
    return ""


def check_symbols_named_in_plain_language(storyboard: str) -> QACheckResult:
    """Heuristic: formula beats should follow concept beats with plain-language VO."""
    vo = _extract_vo_text(storyboard).lower()
    has_formula = bool(re.search(r"[=+\-*/^]|\\frac|\\int|derivative|formula", storyboard, re.I))
    has_plain_intro = any(
        phrase in vo
        for phrase in ("call this", "we name", "this means", "in words", "notice that", "when ")
    )
    passed = not has_formula or has_plain_intro or "approach:" in storyboard.lower()
    return QACheckResult(
        name="symbols_named_in_plain_language",
        passed=passed,
        detail="Formula present but no plain-language naming detected in VO." if not passed else "",
    )


def check_recall_instance_differs(storyboard: str) -> QACheckResult:
    """§4.1 — new instance numbers must differ from STEP 1."""
    if RECALL_CHECKPOINT_TAG not in storyboard:
        return QACheckResult(
            name="recall_instance_differs",
            passed=False,
            detail=f"Missing {RECALL_CHECKPOINT_TAG} tag in storyboard.",
        )
    step1 = _first_concrete_beat(storyboard)
    recall = _recall_checkpoint_beat(storyboard)
    if not step1 or not recall:
        return QACheckResult(
            name="recall_instance_differs",
            passed=False,
            detail="Could not locate STEP 1 or recall checkpoint beats.",
        )
    step1_nums = _extract_numbers(step1)
    recall_nums = _extract_numbers(recall)
    if not recall_nums:
        return QACheckResult(
            name="recall_instance_differs",
            passed=False,
            detail="Recall checkpoint beat has no distinct numbers.",
        )
    if step1_nums and recall_nums == step1_nums:
        return QACheckResult(
            name="recall_instance_differs",
            passed=False,
            detail="Recall instance uses identical numbers to STEP 1 (dictation, not recall).",
        )
    return QACheckResult(name="recall_instance_differs", passed=True)


def check_prerequisite_refresher(gate: PrerequisiteGateResult | None, storyboard: str) -> QACheckResult:
    if gate is None or not gate.insert_refresher:
        return QACheckResult(name="prerequisite_refresher", passed=True, detail="Not required.")
    # Look for early beats mentioning prerequisite concepts
    early = "\n".join(storyboard.splitlines()[:8]).lower()
    found_any = any(p.lower() in early for p in gate.unconfirmed_prerequisites)
    return QACheckResult(
        name="prerequisite_refresher",
        passed=found_any,
        detail="Unconfirmed prerequisites flagged but no refresher detected in opening beats."
        if not found_any
        else "",
    )


def check_forbidden_narration_words(storyboard: str) -> QACheckResult:
    vo = _extract_vo_text(storyboard).lower()
    found = [w for w in FORBIDDEN_NARRATION_WORDS if re.search(rf"\b{re.escape(w)}\b", vo)]
    return QACheckResult(
        name="forbidden_narration_words",
        passed=not found,
        detail=f"Found forbidden words: {', '.join(found)}" if found else "",
    )


def check_concrete_before_abstract(storyboard: str) -> QACheckResult:
    """§0.2 — concrete example should appear before general formula claims."""
    lines = [ln.strip() for ln in storyboard.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 2:
        return QACheckResult(name="concrete_before_abstract", passed=True)
    first = lines[0].lower()
    has_early_number = bool(_extract_numbers(first))
    formula_early = bool(re.search(r"\\frac|\\int|=\s*[^|]+\\", first))
    passed = has_early_number or not formula_early
    return QACheckResult(
        name="concrete_before_abstract",
        passed=passed,
        detail="First beat appears to lead with formula rather than concrete example."
        if not passed
        else "",
    )


def check_pause_prompt_present(storyboard: str) -> QACheckResult:
    if RECALL_CHECKPOINT_TAG not in storyboard:
        return QACheckResult(name="pause_prompt_present", passed=False, detail="No recall checkpoint.")
    lower = storyboard.lower()
    passed = "pause" in lower and "try" in lower
    return QACheckResult(
        name="pause_prompt_present",
        passed=passed,
        detail="Recall checkpoint missing 'Pause and try this' phrasing." if not passed else "",
    )


def run_master_pipeline_qa(
    storyboard: str,
    *,
    gate: PrerequisiteGateResult | None = None,
    strict: bool = False,
) -> MasterPipelineQAReport:
    """
    Run §6 QA checklist against a generated storyboard.

    When strict=False (default), failures are reported but passed may still be True for
    backward-compatible topic jobs without master-pipeline context.
    When strict=True, any failed check fails the report.
    """
    checks = [
        check_symbols_named_in_plain_language(storyboard),
        check_recall_instance_differs(storyboard),
        check_prerequisite_refresher(gate, storyboard),
        check_forbidden_narration_words(storyboard),
        check_concrete_before_abstract(storyboard),
        check_pause_prompt_present(storyboard),
    ]
    failed = [c for c in checks if not c.passed]
    if strict:
        passed = not failed
    else:
        # Non-strict: only hard-fail forbidden words and concrete-before-abstract
        hard_fail_names = {"forbidden_narration_words", "concrete_before_abstract"}
        passed = not any(c.name in hard_fail_names and not c.passed for c in checks)
    return MasterPipelineQAReport(passed=passed, checks=checks)
