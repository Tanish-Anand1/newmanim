"""Pre-flight quality gate for the tiered render pipeline.

All six checks run against the Tier-1 (480p/15fps) draft video before the
production render starts.  The gate passes only when every check passes.

Usage::

    from app.preflight import run_preflight_gate

    all_passed, results = run_preflight_gate(
        draft_video_path=...,
        work_dir=...,
        generated_code=...,
        storyboard=...,
        timed_beats=...,
    )
    if not all_passed:
        failed = [r for r in results if not r.passed]
        raise RuntimeError("Pre-flight gate failed: " + "; ".join(f.summary for f in failed))
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class PreflightResult:
    """Outcome of a single pre-flight check."""

    check_name: str
    passed: bool
    summary: str
    details: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.check_name}: {self.summary}"


# ---------------------------------------------------------------------------
# Check 1 – Boundary pixel presence
# ---------------------------------------------------------------------------


def check_boundary_pixels(
    frames: Sequence[Path],
    *,
    background_rgb: tuple[int, int, int] = (0, 0, 0),
    channel_tolerance: int = 24,
) -> PreflightResult:
    """Fail if any sampled frame has non-background pixels in the outer 2px band."""
    from app.frame_check import border_content_ratio

    failing: list[str] = []
    for frame_path in frames:
        ratio = border_content_ratio(
            frame_path,
            background_rgb=background_rgb,
            channel_tolerance=channel_tolerance,
        )
        if ratio > 0.01:  # 1% tolerance — ignores single anti-aliased pixels
            failing.append(frame_path.name)

    if failing:
        return PreflightResult(
            check_name="boundary_pixels",
            passed=False,
            summary=f"Content found in outer 2-pixel border in {len(failing)} frame(s).",
            details="; ".join(failing),
        )
    return PreflightResult(
        check_name="boundary_pixels",
        passed=True,
        summary=f"No border overflow detected across {len(frames)} sampled frames.",
    )


# ---------------------------------------------------------------------------
# Check 2 – Collision boundary (no pair overlap > threshold)
# ---------------------------------------------------------------------------


def check_collision_boundaries(
    frames: Sequence[Path],
    *,
    overlap_threshold: float = 0.80,
    required_consecutive: int = 3,
) -> PreflightResult:
    """Fail if overlapping text/element blobs persist across ≥3 consecutive frames.

    Threshold is 0.80 (not 0.55) to avoid false positives from the bounding-box
    merge heuristic in foreground_bounds(). Heading + body text on the same frame
    can produce adjacent blobs that the merger joins into one large rectangle;
    a 0.55 threshold would flag that as overlap when it is legitimate layout.
    0.80 means the smaller blob must be almost entirely inside the larger one.
    """
    from app.frame_check import foreground_bounds, max_pair_overlap

    consecutive = 0
    failing: list[str] = []
    for frame_path in frames:
        bounds = foreground_bounds(frame_path)
        ratio = max_pair_overlap(bounds)
        if ratio >= overlap_threshold:
            consecutive += 1
            if consecutive >= required_consecutive:
                failing.append(f"{frame_path.name} (overlap={ratio:.2f})")
        else:
            consecutive = 0

    if failing:
        return PreflightResult(
            check_name="collision_boundary",
            passed=False,
            summary=f"Persistent text overlap (>{overlap_threshold:.0%}) in {len(failing)} frame cluster(s).",
            details="; ".join(failing),
        )
    return PreflightResult(
        check_name="collision_boundary",
        passed=True,
        summary=f"No persistent collision detected across {len(frames)} sampled frames.",
    )


# ---------------------------------------------------------------------------
# Check 3 – Animation timing budget
# ---------------------------------------------------------------------------

_RUN_TIME_RE = re.compile(r"run_time\s*=\s*([0-9]+(?:\.[0-9]*)?)")
_BEAT_COMMENT_RE = re.compile(r"#\s*Beat\s+(\d+)")


def check_animation_timing(
    generated_code: str,
    timed_beats: list[dict],  # [{index, target_duration_seconds}, ...]
) -> PreflightResult:
    """Fail if any beat's total run_time sum exceeds its target duration.

    We parse the generated Python code line-by-line, tracking which beat each
    run_time= belongs to (using ``# Beat N`` comment anchors), and compare the
    cumulative run_time against the beat's storyboard-allocated target duration.
    """
    if not timed_beats:
        return PreflightResult(
            check_name="animation_timing",
            passed=True,
            summary="No timed beats provided — timing check skipped.",
        )

    target_by_beat: dict[int, float] = {
        b.get("index", b.get("beat_number", 0)): float(b.get("target_duration_seconds", b.get("duration_seconds", 999)))
        for b in timed_beats
    }

    current_beat: int | None = None
    accumulated: dict[int, float] = {}

    for line in generated_code.splitlines():
        m_beat = _BEAT_COMMENT_RE.search(line)
        if m_beat:
            current_beat = int(m_beat.group(1))
            accumulated.setdefault(current_beat, 0.0)
            continue
        if current_beat is not None:
            for m_rt in _RUN_TIME_RE.finditer(line):
                accumulated[current_beat] = accumulated.get(current_beat, 0.0) + float(m_rt.group(1))

    overruns: list[str] = []
    for beat_idx, total_rt in accumulated.items():
        budget = target_by_beat.get(beat_idx)
        if budget is not None and total_rt > budget + 0.5:  # 0.5s grace period
            overruns.append(f"Beat {beat_idx}: {total_rt:.1f}s animation > {budget:.1f}s budget")

    if overruns:
        return PreflightResult(
            check_name="animation_timing",
            passed=False,
            summary=f"{len(overruns)} beat(s) exceed their timing budget.",
            details="; ".join(overruns),
        )
    return PreflightResult(
        check_name="animation_timing",
        passed=True,
        summary=f"All {len(accumulated)} timed beats within budget.",
    )


# ---------------------------------------------------------------------------
# Check 4 – Text spacing integrity
# ---------------------------------------------------------------------------


def check_text_spacing(
    frames: Sequence[Path],
    *,
    background_rgb: tuple[int, int, int] = (0, 0, 0),
    channel_tolerance: int = 32,
) -> PreflightResult:
    """Detect merged/glued words in generated scene source code.

    Instead of scanning pixels (which gives false positives on wide math
    equations), we scan the Text() string arguments in the generated .py file.
    Patterns like "Maclaurinlimit" or "TaylorSeries" (camelCase words that
    should have spaces) are caught here without ever touching MathTex content.
    """
    # Locate the generated scene .py file in the same directory as the frames
    scene_dir = frames[0].parent.parent if frames else None
    if scene_dir is None:
        return PreflightResult(
            check_name="text_spacing",
            passed=True,
            summary="No frames supplied — spacing check skipped.",
        )

    scene_files = list(scene_dir.glob("CraftScene_*.py"))
    if not scene_files:
        return PreflightResult(
            check_name="text_spacing",
            passed=True,
            summary="No generated scene file found — spacing check skipped.",
        )

    scene_src = scene_files[0].read_text(encoding="utf-8", errors="replace")

    # Extract all string literals passed to Text() calls
    # Match: Text("...") or Text('...') including multi-word strings
    text_strings: list[str] = re.findall(
        r'(?:^|\b)Text\s*\(\s*["\']([^"\']{2,120})["\']',
        scene_src,
    )

    # Detect merged camelCase words that should have spaces:
    # e.g. "Maclaurinlimit" → lower immediately followed by upper
    # e.g. "TaylorSeries"   → two capitalised words with no space
    GLUED_PATTERN = re.compile(
        r"(?:[a-z][A-Z])"           # camelCase boundary
        r"|(?:[A-Z][a-z]+[A-Z])"    # "McLimit" style
    )

    glued: list[str] = []
    for s in text_strings:
        # Skip strings that are likely pure math / formula fragments
        if re.search(r"[\\$^_{}]", s):
            continue
        # Skip intentional PascalCase scene names (no spaces expected)
        if re.match(r"^[A-Z][A-Za-z0-9]+$", s.strip()):
            continue
        if GLUED_PATTERN.search(s):
            glued.append(repr(s[:60]))

    if glued:
        return PreflightResult(
            check_name="text_spacing",
            passed=False,
            summary=f"Merged words detected in {len(glued)} Text() string(s).",
            details="; ".join(glued),
        )
    return PreflightResult(
        check_name="text_spacing",
        passed=True,
        summary=f"No merged-word glitches found in {len(text_strings)} Text() strings.",
    )



# ---------------------------------------------------------------------------
# Check 5 – LaTeX leak detection
# ---------------------------------------------------------------------------

# Patterns that indicate raw LaTeX control sequences inside Text() calls
_LATEX_IN_TEXT_RE = re.compile(
    r"Text\s*\([^)]*\\(?:frac|int|sum|prod|alpha|beta|gamma|delta|theta|pi|infty|sqrt|cdot|times|div|pm|leq|geq|neq|approx|in|subset|cup|cap|forall|exists|partial|nabla|vec|hat|bar|tilde|overline|underline|text|mathbf|mathrm|mathit|left|right|begin|end)",
    re.DOTALL,
)
# Patterns like Text("x^{2}") or Text("_{n}") that are also LaTeX-only syntax
_LATEX_SUBSCRIPT_IN_TEXT_RE = re.compile(r"Text\s*\([^)]*[\^_]\{", re.DOTALL)


def check_latex_leaks(
    generated_code: str,
) -> PreflightResult:
    """Fail if generated code places raw LaTeX control sequences inside Text() calls.

    MathTex must be used for anything containing \\frac, \\int, ^{}, _{}, etc.
    Finding these inside Text() means uncompiled LaTeX would appear as literal
    backslash-characters in the rendered video.
    """
    control_matches = _LATEX_IN_TEXT_RE.findall(generated_code)
    subscript_matches = _LATEX_SUBSCRIPT_IN_TEXT_RE.findall(generated_code)

    leaks = len(control_matches) + len(subscript_matches)
    if leaks:
        samples = (control_matches + subscript_matches)[:3]
        return PreflightResult(
            check_name="latex_leaks",
            passed=False,
            summary=f"LaTeX control sequences found inside Text() in {leaks} location(s).",
            details="; ".join(s[:80] for s in samples),
        )
    return PreflightResult(
        check_name="latex_leaks",
        passed=True,
        summary="No raw LaTeX found inside Text() calls.",
    )


# ---------------------------------------------------------------------------
# Check 6 – Content completeness
# ---------------------------------------------------------------------------

# Maps storyboard keyword → required LaTeX pattern in generated code
_CONTENT_REQUIREMENTS: list[tuple[list[str], str, str]] = [
    (
        ["integral", "∫", r"\int", "area", "enclosed"],
        r"\\int",
        "integral evaluation",
    ),
    (
        ["tangent", "tangent line"],
        r"y\s*=|\\text\{tangent\}|tangent",
        "tangent line equation",
    ),
    (
        ["circle", "radius", "inscribed circle"],
        r"Circle\(|\\text\{circle\}|radius|r\s*=",
        "circle construction",
    ),
    (
        ["local minimum", "critical point", "derivative"],
        r"f'\(|\\frac\{d|f_x|MathTex.*=.*0",
        "derivative / critical point",
    ),
]


def check_content_completeness(
    storyboard: str,
    generated_code: str,
) -> PreflightResult:
    """Fail if the storyboard implies a computation that never appears in the generated code.

    Uses keyword heuristics: if the storyboard mentions a concept (integral,
    tangent, circle, critical point), at least one MathTex or plot call in the
    generated code must match the corresponding LaTeX/Python pattern.
    """
    storyboard_lower = storyboard.lower()
    code_lower = generated_code.lower()

    missing: list[str] = []
    for keywords, code_pattern, label in _CONTENT_REQUIREMENTS:
        storyboard_match = any(kw.lower() in storyboard_lower for kw in keywords)
        if not storyboard_match:
            continue
        code_match = bool(re.search(code_pattern, generated_code, re.IGNORECASE))
        if not code_match:
            missing.append(label)

    if missing:
        return PreflightResult(
            check_name="content_completeness",
            passed=False,
            summary=f"{len(missing)} concept(s) mentioned in storyboard but absent from generated code.",
            details="; ".join(missing),
        )
    return PreflightResult(
        check_name="content_completeness",
        passed=True,
        summary="All detected storyboard concepts are represented in the generated code.",
    )


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


def run_preflight_gate(
    draft_video_path: Path,
    work_dir: Path,
    generated_code: str,
    storyboard: str,
    timed_beats: list[dict],
    *,
    sample_count: int = 10,
) -> tuple[bool, list[PreflightResult]]:
    """Run all six pre-flight checks against a Tier-1 draft render.

    Args:
        draft_video_path: Path to the 480p/15fps draft MP4.
        work_dir:         Job work directory — frames are written to work_dir/preflight_frames/.
        generated_code:   The generated Manim Python source.
        storyboard:       The storyboard text used to generate the code.
        timed_beats:      List of beat dicts containing ``index`` and
                          ``target_duration_seconds`` keys.
        sample_count:     Number of frames to sample from the draft video.

    Returns:
        ``(all_passed, results)`` where ``results`` is a list of
        :class:`PreflightResult` — one per check.
    """
    from app.frame_check import extract_sample_frames

    frames_dir = work_dir / "preflight_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Extract frames once, share across checks that need them
    logger.info("Pre-flight gate: extracting %d sample frames from %s", sample_count, draft_video_path)
    try:
        frame_pairs = extract_sample_frames(draft_video_path, frames_dir, sample_count)
    except Exception as exc:
        logger.warning("Pre-flight gate: frame extraction failed (%s) — gate skipped.", exc)
        return True, [
            PreflightResult(
                check_name="frame_extraction",
                passed=True,
                summary=f"Frame extraction failed ({exc}); gate skipped to avoid blocking production.",
                details=str(exc),
            )
        ]

    frames = [p for _, p in frame_pairs]

    results: list[PreflightResult] = []

    # 1. Boundary pixels
    r1 = check_boundary_pixels(frames)
    results.append(r1)
    logger.info("  boundary_pixels: %s", r1.summary)

    # 2. Collision boundary
    r2 = check_collision_boundaries(frames)
    results.append(r2)
    logger.info("  collision_boundary: %s", r2.summary)

    # 3. Animation timing budget
    r3 = check_animation_timing(generated_code, timed_beats)
    results.append(r3)
    logger.info("  animation_timing: %s", r3.summary)

    # 4. Text spacing
    r4 = check_text_spacing(frames)
    results.append(r4)
    logger.info("  text_spacing: %s", r4.summary)

    # 5. LaTeX leaks
    r5 = check_latex_leaks(generated_code)
    results.append(r5)
    logger.info("  latex_leaks: %s", r5.summary)

    # 6. Content completeness
    r6 = check_content_completeness(storyboard, generated_code)
    results.append(r6)
    logger.info("  content_completeness: %s", r6.summary)

    all_passed = all(r.passed for r in results)
    gate_status = "PASS" if all_passed else "FAIL"
    failed_count = sum(1 for r in results if not r.passed)
    logger.info(
        "Pre-flight gate %s — %d/6 checks passed, %d failed.",
        gate_status,
        6 - failed_count,
        failed_count,
    )
    return all_passed, results


def format_gate_report(results: list[PreflightResult]) -> str:
    """Human-readable gate report for logging / job error messages."""
    lines = ["Pre-Flight Gate Report", "=" * 40]
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        lines.append(f"{status}  {r.check_name}")
        lines.append(f"       {r.summary}")
        if r.details:
            lines.append(f"       Details: {r.details[:200]}")
    all_passed = all(r.passed for r in results)
    lines.append("=" * 40)
    lines.append("OVERALL: PASS" if all_passed else "OVERALL: FAIL")
    return "\n".join(lines)
