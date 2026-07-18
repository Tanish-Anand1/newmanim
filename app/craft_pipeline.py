import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session
from app.llm_provider import LLMProvider
from app.models import JobStatus
from app.pipeline import (
    MAX_TOKENS,
    codegen_model_for_attempt,
    parse_storyboard,
    update_job,
    timed_stage,
)

logger = logging.getLogger(__name__)

class CraftBeatPlan(BaseModel):
    beat_number: int
    shape: str = Field(description="The template shape: INTRODUCE_CONCEPT, TRANSFORM_EQUATION, COMPARE_SIDE_BY_SIDE, PLOT_MATH_CURVE, or NONE")
    param_title: Optional[str] = None
    param_text: Optional[str] = None
    param_old_eq: Optional[str] = None
    param_new_eq: Optional[str] = None
    param_left_text: Optional[str] = None
    param_left_eq: Optional[str] = None
    param_right_text: Optional[str] = None
    param_right_eq: Optional[str] = None
    
class CraftVideoPlan(BaseModel):
    beats: List[CraftBeatPlan]

def craft_plan_schema_prompt() -> str:
    return (
        "Return one JSON object only, with no Markdown or commentary. The shape is: "
        '{"beats":[{"beat_number":1,"shape":"INTRODUCE_CONCEPT","param_title":"Title","param_text":"Subtitle"}]}. '
        "Allowed shape values: INTRODUCE_CONCEPT, TRANSFORM_EQUATION, COMPARE_SIDE_BY_SIDE, PLOT_MATH_CURVE, NONE. "
        "CRITICAL: You MUST map every single distinct step/beat of the input storyboard to a corresponding beat in the plan. "
        "Do NOT merge, skip, or truncate beats. The plan must cover the entire sequence from beginning to end. "
        "CRITICAL: Every mathematical step, calculation, substitution, and result in the storyboard MUST be mapped to TRANSFORM_EQUATION (or COMPARE_SIDE_BY_SIDE) to ensure it is rendered. Do NOT map active mathematical steps or calculations to NONE; NONE should only be used for silent pauses. "
        "CRITICAL: You MUST strictly preserve all numerical values and math equations exactly as written in the storyboard. For example, if the storyboard calculates the area as 27/4, keep it as 27/4 (do not change it to 11/4). If the antiderivative value at x=2 is 4, do not write it as 0. Double check all calculations for mathematical correctness and storyboard consistency. "
        "CRITICAL: Whenever any parameter (including titles, text, headings, or equations) contains mixed plain English words and math formulas, you MUST wrap all the math formulas inside that parameter in $ delimiters (for example, 'At $x=2$, the value is $4$.' or 'center is $(0,r)$'). This is crucial to ensure spaces are not stripped in the rendered output. "
        "CRITICAL: Math equations and LaTeX formulas MUST be strictly mathematical. Do NOT embed English prose connectors like 'from', 'to', 'of', 'and' inside equation parameters (for example, write '\\int_{-1}^{2}(x^3-3x^2+4)\\,dx' instead of '\\text{integral from } -1 \\text{ to } 2 \\text{ of } (x^3-3x^2+4)'). Any spoken narrative connectors belong in the heading/title parameter or narration, not in the equation parameter. "
        "CRITICAL: Use a geometry-first approach: whenever possible, prioritize visual representations of math (shapes, curves, coordinates) before abstract equations. "
        "For INTRODUCE_CONCEPT, provide param_title and optionally param_text. "
        "For TRANSFORM_EQUATION, provide param_old_eq, param_new_eq, and optionally param_title (as a heading). "
        "For COMPARE_SIDE_BY_SIDE, provide param_left_text, param_left_eq, param_right_text, param_right_eq, and optionally param_title. "
        "For PLOT_MATH_CURVE, use when we need to plot the calculus curve f(x)=x^3-3x^2+4 and show the tangent line, the shaded integral area, and the inscribed circle. Provide param_title as a heading. "
        "Use valid LaTeX without $ delimiters for pure equations, but use $ delimiters for math inside mixed strings. "
        "If the beat does not fit these shapes exactly, use NONE."
    )

def generate_craft_plan(
    provider: LLMProvider,
    storyboard: str,
    orientation: str,
    beat_numbers: List[int],
    db: Session,
    job_id: str,
) -> CraftVideoPlan:
    import re

    system = craft_plan_schema_prompt()
    user_message = f"Convert this storyboard into a craft template plan:\n{storyboard}"

    work_dir = Path(os.getenv("VIVACITY_WORK_ROOT", "c:/PROJECTS/vivacity_job_runs")) / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, 4):
        model = codegen_model_for_attempt(provider, attempt)
        try:
            response = provider.generate(
                system=system,
                user_message=user_message,
                # Long 3-problem storyboards need more room; cap at provider max.
                max_tokens=min(MAX_TOKENS, 4096),
                model=model,
            )
        except Exception as exc:
            logger.warning("Craft plan LLM call failed on attempt %d: %s", attempt, exc)
            last_exc = exc
            continue

        raw_path = work_dir / f"storyboard_plan_llm_raw_response_attempt{attempt}.txt"
        try:
            raw_path.write_text(response.text, encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write plan raw response: %s", exc)

        text = response.text.strip()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            logger.warning(
                "Attempt %d: Craft plan response had no JSON object (first 300 chars): %s",
                attempt, text[:300],
            )
            last_exc = ValueError(
                f"Craft plan response did not contain a JSON object. "
                f"Raw response was: {text[:300]}..."
            )
            continue

        json_str = text[start : end + 1]
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError:
            # Sanitize unescaped LaTeX backslashes in JSON strings
            json_str_sanitized = re.sub(r'\\(?!["\\/ bfnrtu])', r'\\\\', json_str)
            try:
                payload = json.loads(json_str_sanitized)
            except json.JSONDecodeError as exc:
                logger.warning("Attempt %d: JSON parse failed even after sanitization: %s", attempt, exc)
                last_exc = exc
                continue

        try:
            plan = CraftVideoPlan.model_validate(payload)
            return plan
        except Exception as exc:
            logger.warning("Attempt %d: Pydantic validation failed: %s", attempt, exc)
            last_exc = exc
            continue

    raise last_exc


def compile_craft_scene(
    scene_name: str,
    orientation: str,
    plan: CraftVideoPlan,
    project_root: str,
) -> str:
    """Generates the Manim python code that executes the craft templates."""
    
    lines = [
        "import sys",
        f"sys.path.insert(0, r'{project_root}')",
        "from manim import *",
        "from app.craft_library import CraftContext, introduce_concept, transform_equation, compare_side_by_side, plot_math_curve_with_tangent_and_area",
        "",
        f"class {scene_name}(MovingCameraScene):",
        "    def construct(self):",
        f"        ctx = CraftContext(self, orientation='{orientation}')",
        "",
    ]
    
    for beat in plan.beats:
        lines.append(f"        # Beat {beat.beat_number} - {beat.shape}")
        
        if beat.shape == "NONE":
            logger.warning(f"Gap detected: No template shape matches beat {beat.beat_number}")
            lines.append(f"        # Gap: No matching craft template for Beat {beat.beat_number}")
            # We don't fallback to freeform LLM here. Just wait for narration duration (simulated as 3 seconds for now)
            lines.append("        ctx.smooth_wait(3.0)")
            
        elif beat.shape == "INTRODUCE_CONCEPT":
            title = repr(beat.param_title or "")
            text = repr(beat.param_text) if beat.param_text else "None"
            lines.append(f"        introduce_concept(ctx, title={title}, text={text})")
            
        elif beat.shape == "TRANSFORM_EQUATION":
            old_eq = repr(beat.param_old_eq or "")
            new_eq = repr(beat.param_new_eq or "")
            heading = repr(beat.param_title) if beat.param_title else "None"
            lines.append(f"        transform_equation(ctx, old_eq={old_eq}, new_eq={new_eq}, heading={heading})")
            
        elif beat.shape == "COMPARE_SIDE_BY_SIDE":
            l_txt = repr(beat.param_left_text or "")
            l_eq = repr(beat.param_left_eq or "")
            r_txt = repr(beat.param_right_text or "")
            r_eq = repr(beat.param_right_eq or "")
            heading = repr(beat.param_title) if beat.param_title else "None"
            lines.append(f"        compare_side_by_side(ctx, left_text={l_txt}, left_eq={l_eq}, right_text={r_txt}, right_eq={r_eq}, heading={heading})")
            
        elif beat.shape == "PLOT_MATH_CURVE":
            heading = repr(beat.param_title) if beat.param_title else "None"
            lines.append(f"        plot_math_curve_with_tangent_and_area(ctx, heading={heading})")
        
        lines.append("")
        
    return "\n".join(lines)


def run_craft_pipeline_for_job(job_id: str, db: Session, work_dir, provider, job, beats, debug_log_path) -> bool:
    """Tiered pipeline orchestrator for craft jobs.

    Render flow:
        1. Render Tier 1 (480p / 15fps) into ``work_dir/media_draft/``.
        2. Run the six-check automated pre-flight gate against the Tier 1 video.
        3. If gate PASSES → render Tier 3 (1080p / 30fps) into ``work_dir/media_production/``.
        4. If gate FAILS  → raise RuntimeError with structured gate report; production render skipped.
    """
    from pathlib import Path
    from app.pipeline import (
        write_job_scene_file,
        persist_generated_code,
        render_scene_for_job,
        find_rendered_video,
        RENDER_TIER_1_DRAFT,
        RENDER_TIER_3_PRODUCTION,
    )
    from app.preflight import run_preflight_gate, format_gate_report

    scene_name = f"CraftScene_{job_id.replace('-', '_')}"
    orientation = "portrait"

    # ------------------------------------------------------------------ #
    # 1. Generate craft plan + compile Manim code                         #
    # ------------------------------------------------------------------ #
    update_job(
        db, job_id,
        status=JobStatus.generating_code,
        progress_message="Building crafted template plan.",
    )

    beat_numbers = [b.index for b in beats]
    plan = generate_craft_plan(provider, job.storyboard, orientation, beat_numbers, db, job_id)

    project_root = str(Path(__file__).resolve().parent.parent)
    code = compile_craft_scene(scene_name, orientation, plan, project_root)
    scene_file = write_job_scene_file(job_id, scene_name, code)
    persist_generated_code(db, job_id, code)

    # ------------------------------------------------------------------ #
    # 2. Tier 1 — draft render (480p / 15fps)                             #
    # ------------------------------------------------------------------ #
    update_job(
        db, job_id,
        status=JobStatus.rendering,
        progress_message="Rendering draft (Tier 1 — 480p/15fps) for pre-flight gate.",
    )

    with timed_stage(debug_log_path, "craft_render_tier1"):
        draft_ok, draft_feedback = render_scene_for_job(
            job_id,
            scene_file,
            scene_name,
            work_dir,
            orientation,
            render_tier=RENDER_TIER_1_DRAFT,
        )

    if not draft_ok:
        raise RuntimeError(f"Craft scene Tier-1 draft render failed: {draft_feedback}")

    draft_video = find_rendered_video(work_dir, scene_name, render_tier=RENDER_TIER_1_DRAFT)
    if draft_video is None:
        raise RuntimeError(f"Tier-1 draft video not found after render for scene {scene_name}")

    logger.info("Tier-1 draft render complete: %s", draft_video)

    # ------------------------------------------------------------------ #
    # 3. Pre-flight gate — run all 6 checks against Tier 1 video          #
    # ------------------------------------------------------------------ #
    update_job(
        db, job_id,
        status=JobStatus.rendering,
        progress_message="Running pre-flight quality gate against Tier-1 draft.",
    )

    timed_beats_list: list[dict] = [
        {
            "index": getattr(b, "index", 0),
            "target_duration_seconds": getattr(
                b, "target_duration_seconds",
                getattr(b, "duration_seconds", 999),
            ),
        }
        for b in beats
    ]

    gate_passed, gate_results = run_preflight_gate(
        draft_video_path=draft_video,
        work_dir=work_dir,
        generated_code=code,
        storyboard=job.storyboard or "",
        timed_beats=timed_beats_list,
        sample_count=10,
    )

    gate_report = format_gate_report(gate_results)
    logger.info("Pre-flight gate report:\n%s", gate_report)

    if not gate_passed:
        failed_checks = [r for r in gate_results if not r.passed]
        raise RuntimeError(
            f"Pre-flight gate FAILED ({len(failed_checks)}/6 checks failed). "
            + "; ".join(r.summary for r in failed_checks)
            + "\n\nFull report:\n"
            + gate_report
        )

    logger.info("Pre-flight gate PASSED — proceeding to Tier-3 production render.")

    # ------------------------------------------------------------------ #
    # 4. Tier 3 — production render (1080p / 30fps)                       #
    # ------------------------------------------------------------------ #
    update_job(
        db, job_id,
        status=JobStatus.rendering,
        progress_message="Pre-flight gate passed. Rendering production quality (Tier 3 — 1080p/30fps).",
    )

    with timed_stage(debug_log_path, "craft_render_tier3"):
        render_ok, render_feedback = render_scene_for_job(
            job_id,
            scene_file,
            scene_name,
            work_dir,
            orientation,
            render_tier=RENDER_TIER_3_PRODUCTION,
        )

    if not render_ok:
        raise RuntimeError(f"Craft scene Tier-3 production render failed: {render_feedback}")

    logger.info("Tier-3 production render complete.")
    return True
