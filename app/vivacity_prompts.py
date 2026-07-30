"""Central prompt builders for the Vivacity master pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION_PATH = REPO_ROOT / "vivacity_video_constitution.md"
MASTER_PROMPT_PATH = REPO_ROOT / "vivacity_master_system_prompt.md"
_master_prompt_cache: tuple[int, int, str] | None = None

FORBIDDEN_NARRATION_WORDS = ("obviously", "simply", "just", "clearly")
RECALL_CHECKPOINT_TAG = "[RECALL_CHECKPOINT]"


@lru_cache(maxsize=1)
def load_video_constitution() -> str:
    if CONSTITUTION_PATH.is_file():
        return CONSTITUTION_PATH.read_text(encoding="utf-8").strip()
    return ""


def load_master_system_prompt() -> str:
    """Load the canonical prompt, rereading it whenever its file changes."""
    global _master_prompt_cache
    if not MASTER_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Canonical Vivacity prompt is missing: {MASTER_PROMPT_PATH}")
    stat = MASTER_PROMPT_PATH.stat()
    cache_key = (stat.st_mtime_ns, stat.st_size)
    if _master_prompt_cache is not None and _master_prompt_cache[:2] == cache_key:
        return _master_prompt_cache[2]
    text = MASTER_PROMPT_PATH.read_text(encoding="utf-8").strip()
    _master_prompt_cache = (cache_key[0], cache_key[1], text)
    return text


def build_script_generation_system_prompt(
    *,
    topic: str,
    exam_context: str,
    flagged_as_weak_topic: bool,
    unconfirmed_prerequisites: list[str],
    weak_topic_extra_scaffolding: bool = True,
) -> str:
    """§3 script-generation system prompt for storyboard drafting."""
    prereq_block = ""
    if unconfirmed_prerequisites:
        prereq_list = ", ".join(unconfirmed_prerequisites)
        prereq_block = (
            f"\nSTEP 0 (mandatory — unconfirmed prerequisites: {prereq_list}):\n"
            "Write a 30-45s refresher beat for EACH unconfirmed prerequisite before the main topic. "
            "Use one concrete number per refresher. Do not use notation the student hasn't seen defined "
            "in that same beat.\n"
        )
    else:
        prereq_block = "\nSTEP 0: Skip — no unconfirmed prerequisites.\n"

    weak_note = ""
    if flagged_as_weak_topic and weak_topic_extra_scaffolding:
        weak_note = (
            "\nSTUDENT CONTEXT: This topic is flagged as weak. Add extra concrete examples in STEP 1-2 "
            "and slow the pacing — one relationship per beat, shorter sentences.\n"
        )

    constitution_ref = (
        "Follow vivacity_video_constitution.md for beat duration (3-8s), sentence length, and layout hints "
        "when writing ON SCREEN specs.\n"
    )
    master_prompt = load_master_system_prompt()

    return (
        f"{master_prompt}\n\n"
        "Apply the canonical rules above to this request.\n\n"
        "You are generating a teaching script for a JEE/NEET student.\n"
        f"Topic: {topic}\n"
        f"Exam context: {exam_context}\n"
        f"Weak topic flag: {flagged_as_weak_topic}\n"
        f"Unconfirmed prerequisites: {', '.join(unconfirmed_prerequisites) or 'none'}\n"
        f"{weak_note}\n"
        "GEOMETRIC PROOF REQUIREMENT: If the topic contains 'visually prove', 'show geometrically', 'construct', or similar, you MUST plan a visual, shape-building proof. "
        "For 'sum of first n odd integers', you MUST explicitly describe building an n x n grid of unit squares/dots one L-shaped layer at a time (e.g. 'layer 1 is a single square, layer 2 adds an L-shaped band of 3 squares making a 2x2 block', etc.). "
        "You MUST include shape words like 'Square', 'Dot grid', 'layer', or 'block' in the ON SCREEN text for these beats.\n"
        "OUTPUT FORMAT: Return ONLY storyboard text. One beat per line. Example EXACT format:\n"
        '# Approach: concrete example first, then guided noticing, then formula.\n'
        '[0-4] ON SCREEN: Show a specific numerical example | VO: "Start with one concrete case."\n'
        '[4-8] ON SCREEN: Vary one part and observe the pattern | VO: "Notice what changes when we modify a value."\n'
        'Each line MUST start with [number-number] ON SCREEN: and contain | VO: "text"\n'
        "The [start-end] numbers are integer seconds. Start at 0.\n"
        "VO text MUST be inside double quotes.\n"
        f"{constitution_ref}\n"
        "STRUCTURE — follow exactly, in order. Do not skip or reorder steps.\n"
        f"{prereq_block}\n"
        "STEP 1 — Concrete instance:\n"
        "Open with one specific numerical/geometric example of the topic. No general claim yet. No formula yet.\n\n"
        "STEP 2 — Guided noticing:\n"
        "Walk through what changes/stays the same when you vary one part of the STEP 1 example. "
        'State the observation in plain words ("notice that when X grows, Y always does this...") '
        "before naming it mathematically.\n\n"
        "STEP 3 — Name the general claim in words.\n"
        "One sentence, no notation.\n\n"
        "STEP 4 — Introduce the formula.\n"
        "Build it term-by-term, each term explicitly mapped back to the part of the STEP 1 example it represents. "
        "Never introduce a symbol the script hasn't already used a plain-language name for.\n\n"
        "STEP 5 — Edge case or why does this actually work.\n"
        "One case where naive intuition would get it wrong, resolved.\n\n"
        f"STEP 6 — ACTIVE RECALL CHECKPOINT:\n"
        f"Insert the literal tag {RECALL_CHECKPOINT_TAG} in a beat's ON SCREEN field. "
        "That beat must show a NEW instance of the same problem type as STEP 1 with DIFFERENT numbers "
        "(not copy-paste). ON SCREEN must include 'Pause and try this' and the new instance only — no solution. "
        "Follow with beats that reveal the worked solution to the new instance, narrated concrete-first but compressed.\n\n"
        "HARD RULES:\n"
        "- MATH NOTATION: In the ON SCREEN fields, always write mathematical equations using standard LaTeX notation enclosed in backticks (e.g. `f(t) = \\frac{4}{\\pi} \\sin(\\omega t)`), using the standard `=` operator. Do not use Unicode characters like `≈`, `π`, `ω`, `θ`, or plain-text slashes for divisions. This is required for validation parser compatibility.\n"
        "- Every technical term must be spoken in plain language before its symbol/name is used.\n"
        "- No step may reference a formula or term not yet introduced in an earlier step.\n"
        "- Sentence length: prefer under 20 words.\n"
        f"- Do not use {', '.join(repr(w) for w in FORBIDDEN_NARRATION_WORDS)}.\n"
        "- Preserve the user's exact formulas, numbers, and named terms from the topic request.\n"
        "- PHYSICS FACT CHECK: Before finalizing any physics narration, verify every causal and directional claim against the actual physics. For a pendulum, tension points along the string toward the pivot, while the tangential restoring-force component points toward the equilibrium position (theta=0), not toward the pivot. Do not conflate these forces.\n"
        "- Each beat 3-8 seconds; total timing approximately the requested duration.\n"
        "- Do not create a render job or output anything except storyboard beats."
    )


def build_storyboard_format_addon() -> str:
    """Legacy Manim storyboard constraints merged with master pipeline output."""
    return (
        "Each beat must be 3 to 8 seconds long. For derivations, break each step into its own beat. "
        "ON SCREEN is a visual specification: describe graphs, diagrams, or stepwise substitution — "
        "not decorative motion applied to prose. Use (silent) only when there is intentionally no voiceover."
    )


def build_manim_codegen_addon(*, include_recall_checkpoint: bool = True) -> str:
    """§5 additional Manim codegen requirements fed into legacy/template/craft prompts."""
    constitution = load_video_constitution()
    master_prompt = load_master_system_prompt()
    recall_block = ""
    if include_recall_checkpoint:
        recall_block = (
            "\nRECALL CHECKPOINT RENDERING: When the storyboard contains "
            f"{RECALL_CHECKPOINT_TAG}, render the pause-timer using the SAME anchor-zone/equation-zone "
            "split as the rest of the scene (vivacity_video_constitution.md §1.3). Do not create new layout "
            "primitives for the timer: reuse the existing anchor-zone components that render the main diagram. "
            "Place new-instance numbers where STEP 1 numbers were. Show 'Pause and try this' with a "
            "5-8 second countdown timer in the anchor zone. After the pause, reveal the compressed solution "
            "in the equation zone.\n"
        )
    constitution_block = f"\n\n--- vivacity_video_constitution.md ---\n{constitution}\n--- end constitution ---\n"
    return (
        f"{master_prompt}\n\n"
        "Apply the canonical rules above to the generated scene.\n\n"
        "Convert the script into a Manim scene following vivacity_video_constitution.md strictly "
        "(§1 layout, §1.3 swap rule, §2 pacing).\n"
        "CRITICAL CODE RULE: Do not copy the storyboard ON SCREEN descriptions verbatim into Text(), Tex(), or fitted_text() calls. "
        "The ON SCREEN field describes what visual objects to construct (e.g., Axes, Graphs, Vectors)—it is NOT a subtitle or caption to write on screen. "
        "The validator will fail if there is any word overlap between your text labels and the ON SCREEN text. "
        "Write only very short, separately authored mathematical labels or section headers (e.g., Text('Fourier Series') or Text('Linear Approximation')).\n"
        "CRITICAL MATH NOTATION DELIMITERS RULE: Double-check all LaTeX syntax you write (especially in MathTex or Tex calls). All nested curly braces `{}`, parentheses `()`, and square brackets `[]` must be perfectly balanced and matching (e.g., do not write `^{(n-1}` without the closing `}`). Mismatched delimiters will crash the parser.\n"
        f"{recall_block}"
        "Self-check before returning code: does every symbol on screen at the formula step have a "
        "plain-language name spoken before it appears? If unsure, add the spoken definition.\n"
        f"{constitution_block}"
    )


def build_end_of_video_recall_prompt(
    *,
    topic: str,
    storyboard: str,
    step1_example_hint: str = "",
) -> tuple[str, str]:
    """§4.2 end-of-video retrieval question — one question combining edge-case reasoning."""
    system = (
        "Generate exactly ONE end-of-video retrieval question for a JEE/NEET student. "
        "The question must require combining the main concrete example (STEP 1-4) with the edge case "
        "(STEP 5) — not just repeating the main example. "
        "It must be answerable from the video content but require application, not dictation. "
        'Output JSON only: {"question": "...", "answer": "...", "explanation": "..."}'
    )
    user = f"Topic: {topic}\n"
    if step1_example_hint:
        user += f"STEP 1 example hint: {step1_example_hint}\n"
    user += f"\nStoryboard:\n{storyboard}"
    return system, user


def build_in_video_recall_prompt(*, topic: str, step1_example: str) -> tuple[str, str]:
    """§4.1 recall checkpoint instance generation (when storyboard lacks explicit new instance)."""
    system = (
        "STEP 6 ACTIVE RECALL INSTANCE: Generate ONE new problem instance of the same type as the given "
        "STEP 1 example, with verifiably different numeric values that require reapplying the logic, not "
        "copy-paste. This is a new-instance checkpoint, not a restatement of the lesson. "
        'Output JSON: {"instance_description": "...", "solution_outline": "..."}'
    )
    user = f"Topic: {topic}\nSTEP 1 example: {step1_example}"
    return system, user


def extract_recall_checkpoint_context(storyboard: str) -> dict[str, Any]:
    """Parse recall-related metadata from a generated storyboard."""
    has_checkpoint = RECALL_CHECKPOINT_TAG in storyboard
    step1_hint = ""
    for line in storyboard.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "ON SCREEN:" in stripped and RECALL_CHECKPOINT_TAG not in stripped:
            step1_hint = stripped
            break
    return {
        "has_recall_checkpoint": has_checkpoint,
        "step1_example_hint": step1_hint,
    }
