from __future__ import annotations

import os
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.frame_check import detect_frame_overflow, detect_sparse_frames, get_media_duration
from app.llm_provider import LLMProvider, ProviderUnavailableError
from app.models import Job, JobStatus, SessionLocal
from app.storage import upload_video
from app.template_engine import (
    TemplateBeatInput,
    TemplateVideoPlan,
    build_heuristic_template_plan,
    compile_template_scene,
    enrich_template_plan_visuals,
    parse_template_plan,
    template_plan_schema_prompt,
    template_plan_user_message,
    validate_template_plan_topic_isolation,
)


TEMPLATE_PLAN_PARSE_RETRIES = max(1, int(os.getenv("TEMPLATE_PLAN_PARSE_RETRIES", "2")))
TEMPLATE_RENDER_ATTEMPTS = max(1, int(os.getenv("TEMPLATE_RENDER_ATTEMPTS", "2")))


def generate_template_plan(
    provider: LLMProvider,
    storyboard: str,
    orientation: str,
    beat_numbers: list[int],
    db: Session,
    job_id: str,
    debug_log_path: Path,
) -> TemplateVideoPlan:
    from app.pipeline import (
        MAX_TOKENS,
        RATE_LIMIT_RETRY_LIMIT,
        add_llm_cost,
        codegen_model_for_attempt,
        enforce_job_cost_budget,
        is_rate_limit_exception,
        llm_response_identity,
        log_debug_timing,
        projected_llm_call_cost,
        parse_storyboard,
        rate_limit_retry_after_seconds,
        timed_stage,
        timed_beat_windows,
        update_job,
        write_codegen_validation_rejection,
    )

    system = template_plan_schema_prompt()
    user_message = template_plan_user_message(storyboard, orientation)
    last_error: Exception | None = None
    model = codegen_model_for_attempt(provider, 1)
    on_screen_by_beat = {beat.index: beat.on_screen_text for beat in parse_storyboard(storyboard)}

    for parse_attempt in range(1, TEMPLATE_PLAN_PARSE_RETRIES + 1):
        rate_attempt = 0
        while True:
            try:
                with timed_stage(debug_log_path, f"template_plan_llm_{parse_attempt}"):
                    enforce_job_cost_budget(
                        db,
                        job_id,
                        projected_llm_call_cost(provider.name, model, system, user_message, min(MAX_TOKENS, 2600)),
                    )
                    response = provider.generate(
                        system=system,
                        user_message=user_message,
                        max_tokens=min(MAX_TOKENS, 2600),
                        model=model,
                    )
                break
            except Exception as exc:
                if not is_rate_limit_exception(exc) or rate_attempt >= RATE_LIMIT_RETRY_LIMIT:
                    raise
                rate_attempt += 1
                sleep_seconds = rate_limit_retry_after_seconds(exc)
                update_job(
                    db,
                    job_id,
                    status=JobStatus.retrying,
                    progress_message=f"Provider is busy; retrying the same layout-plan request in {sleep_seconds:.0f}s.",
                    error=str(exc),
                )
                log_debug_timing(
                    debug_log_path,
                    f"TEMPLATE_PLAN_RATE_LIMIT retry={rate_attempt}/{RATE_LIMIT_RETRY_LIMIT} sleep_sec={sleep_seconds:.1f}",
                )
                time.sleep(sleep_seconds)

        actual_provider, actual_model = llm_response_identity(response, provider, model)
        add_llm_cost(db, job_id, actual_provider, actual_model, response.input_tokens, response.output_tokens)
        try:
            plan = parse_template_plan(response.text, beat_numbers, on_screen_by_beat)
            validate_template_plan_topic_isolation(storyboard, plan)
            return plan
        except ValueError as exc:
            last_error = exc
            write_codegen_validation_rejection(
                job_id,
                render_attempt=1,
                validation_attempt=parse_attempt,
                provider_name=actual_provider,
                model=actual_model,
                reason=f"template_plan: {exc}",
                target_beat_number=None,
            )
            user_message = (
                f"{template_plan_user_message(storyboard, orientation)}\n\n"
                f"Your previous JSON failed validation: {exc}. Return corrected JSON only."
            )
            update_job(
                db,
                job_id,
                status=JobStatus.retrying,
                progress_message=f"Repairing the structured layout plan ({parse_attempt}/{TEMPLATE_PLAN_PARSE_RETRIES}).",
                error=str(exc),
            )

    raise RuntimeError(f"Structured layout plan remained invalid: {last_error}")


def run_template_pipeline_for_job(
    job_id: str,
    storyboard: str,
    scene_name: str,
    orientation: str = "portrait",
    max_target_seconds: int | None = None,
) -> None:
    from app.pipeline import (
        DRIFT_FAILURE_RATIO,
        MAX_TARGET_SECONDS,
        RENDER_COMPUTE_USD_PER_HOUR,
        WORK_ROOT,
        assess_video_quality,
        concatenate_audio,
        generate_timed_beat_audio,
        log_debug_timing,
        mux_audio_video,
        normalize_generated_text,
        persist_generated_code,
        planned_total_duration,
        provider_for_job,
        reset_job_render_workspace,
        render_scene_for_job,
        safe_scene_name,
        should_run_vision_quality_check,
        stretch_audio_to_duration,
        timed_beat_windows,
        timed_stage,
        update_job,
        validate_generated_python,
        validate_video_semantic_palette,
        validate_storyboard_or_raise,
        write_job_scene_file,
        enforce_job_cost_budget,
        is_provider_capacity_exception,
    )

    db = SessionLocal()
    work_dir = WORK_ROOT / job_id
    debug_log_path = work_dir / "debug_timing.log"
    beats = []
    try:
        storyboard = normalize_generated_text(storyboard)
        scene_name = safe_scene_name(scene_name)
        if orientation not in {"portrait", "landscape"}:
            raise ValueError("orientation must be portrait or landscape.")
        beats = validate_storyboard_or_raise(
            storyboard,
            max_target_seconds=max_target_seconds or MAX_TARGET_SECONDS,
        )
        job = db.get(Job, job_id)
        if job is not None:
            job.storyboard = storyboard
            job.pipeline_profile = "template"
            db.commit()

        reset_job_render_workspace(work_dir, job_id)
        log_debug_timing(debug_log_path, f"TEMPLATE_JOB_START job_id={job_id} scene={scene_name} orientation={orientation}")

        # Compile a deterministic, storyboard-derived scene before TTS. This
        # catches malformed user math and structural template failures before
        # spending on voice clips that cannot lead to a renderable video.
        preflight_inputs: list[TemplateBeatInput] = []
        previous_end = 0.0
        for beat in beats:
            preflight_inputs.append(
                TemplateBeatInput(
                    beat_number=beat.index,
                    target_duration=max(0.3, beat.end_sec - beat.start_sec),
                    gap_before=max(0.0, beat.start_sec - previous_end),
                    on_screen=beat.on_screen_text,
                    vo_text=beat.vo_text,
                )
            )
            previous_end = beat.end_sec
        update_job(
            db,
            job_id,
            status=JobStatus.generating_code,
            progress_message="Validating storyboard math and animation structure.",
            attempt_number=1,
        )
        preflight_plan = enrich_template_plan_visuals(
            storyboard,
            build_heuristic_template_plan(scene_name, preflight_inputs),
            {beat_input.beat_number: beat_input.on_screen for beat_input in preflight_inputs},
        )
        preflight_code = compile_template_scene(
            scene_name,
            orientation,
            preflight_inputs,
            preflight_plan,
            use_mathtex=True,
        )
        validate_generated_python(preflight_code, storyboard)
        validate_video_semantic_palette(preflight_code)
        log_debug_timing(debug_log_path, "TEMPLATE_PREFLIGHT status=pass tts_calls=0")

        update_job(
            db,
            job_id,
            status=JobStatus.generating_voiceover,
            progress_message="Generating one voiceover clip per storyboard beat.",
            attempt_number=1,
        )
        with timed_stage(debug_log_path, "tts_generation_total"):
            timed_beats = generate_timed_beat_audio(beats, work_dir / "audio", debug_log_path, db, job_id)
        audio_track = work_dir / f"{scene_name}_beats.mp3"
        with timed_stage(debug_log_path, "audio_concatenate"):
            concatenate_audio(timed_beats, work_dir / "audio", audio_track)

        template_inputs = [
            TemplateBeatInput(
                beat_number=timed.beat.index,
                target_duration=timed.target_duration,
                gap_before=timed.gap_before,
                on_screen=timed.beat.on_screen_text,
                vo_text=timed.beat.vo_text,
            )
            for timed in timed_beats
        ]
        target_duration = planned_total_duration(timed_beats)
        if job is not None:
            request_payload = dict(job.request_payload or {})
            request_payload["rendered_beat_windows"] = timed_beat_windows(timed_beats)
            request_payload["rendered_duration_seconds"] = target_duration
            job.request_payload = request_payload
            db.commit()
        planner_mode = os.getenv("TEMPLATE_PLANNER", "llm").strip().lower()
        if planner_mode not in {"llm", "heuristic"}:
            raise RuntimeError("TEMPLATE_PLANNER must be either 'llm' or 'heuristic'.")
        provider = None
        update_job(
            db,
            job_id,
            status=JobStatus.generating_code,
            progress_message=(
                "Building a deterministic animation plan."
                if planner_mode == "heuristic"
                else "Building a validated structured animation plan."
            ),
        )
        if planner_mode == "heuristic":
            plan = build_heuristic_template_plan(scene_name, template_inputs)
            log_debug_timing(debug_log_path, "TEMPLATE_PLANNER mode=heuristic llm_calls=0")
        else:
            provider = provider_for_job(db, job_id)
            plan = generate_template_plan(
                provider,
                storyboard,
                orientation,
                [beat.index for beat in beats],
                db,
                job_id,
                debug_log_path,
            )
        plan = enrich_template_plan_visuals(
            storyboard,
            plan,
            {beat_input.beat_number: beat_input.on_screen for beat_input in template_inputs},
        )
        (work_dir / "template_plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        scene_file = work_dir / f"{scene_name}.py"
        video_path = None
        render_feedback = ""
        for render_attempt in range(1, TEMPLATE_RENDER_ATTEMPTS + 1):
            code = compile_template_scene(
                scene_name,
                orientation,
                template_inputs,
                plan,
                use_mathtex=True,
            )
            validate_generated_python(code, storyboard)
            validate_video_semantic_palette(code)
            scene_file = write_job_scene_file(job_id, scene_name, code)
            persist_generated_code(db, job_id, code)
            update_job(
                db,
                job_id,
                status=JobStatus.rendering,
                progress_message=f"Rendering structured scene ({render_attempt}/{TEMPLATE_RENDER_ATTEMPTS}).",
                attempt_number=render_attempt,
                error=None,
            )
            projected_render_seconds = max(
                1.0,
                float(os.getenv("CAPACITY_PLANNING_JOB_SECONDS", "180")),
            )
            enforce_job_cost_budget(
                db,
                job_id,
                projected_render_seconds / 3600.0 * RENDER_COMPUTE_USD_PER_HOUR,
            )
            render_started = time.monotonic()
            with timed_stage(debug_log_path, f"template_render_{render_attempt}"):
                render_ok, render_feedback = render_scene_for_job(
                    job_id,
                    scene_file,
                    scene_name,
                    work_dir,
                    orientation,
                )
            from app.pipeline import record_render_compute_cost

            record_render_compute_cost(db, job_id, time.monotonic() - render_started)
            if render_ok:
                from app.pipeline import find_rendered_video

                video_path = find_rendered_video(work_dir, scene_name)
                if video_path is not None:
                    break
            update_job(
                db,
                job_id,
                status=JobStatus.retrying,
                progress_message="Retrying the deterministic scene with text-safe equation rendering.",
                error=render_feedback[-4000:],
            )

        if video_path is None:
            raise RuntimeError(f"Structured scene render failed: {render_feedback[-2000:]}")

        video_duration = get_media_duration(video_path)
        if target_duration > 0 and abs(video_duration - target_duration) / target_duration > DRIFT_FAILURE_RATIO:
            raise RuntimeError(
                f"Structured scene timing drift exceeded the configured ratio: target={target_duration:.2f}s, "
                f"rendered={video_duration:.2f}s."
            )
        if job is not None:
            request_payload = dict(job.request_payload or {})
            request_payload["rendered_beat_windows"] = timed_beat_windows(timed_beats, video_duration)
            request_payload["rendered_duration_seconds"] = video_duration
            job.request_payload = request_payload
            db.commit()

        update_job(
            db,
            job_id,
            status=JobStatus.rendering,
            progress_message="Running deterministic frame-boundary checks.",
        )
        with timed_stage(debug_log_path, "template_frame_boundary_scan"):
            overflow = detect_frame_overflow(video_path, work_dir / "boundary_samples")
        if overflow:
            first = overflow[0]
            raise RuntimeError(f"Visible content reached the frame boundary near {first.timestamp:.2f}s.")

        with timed_stage(debug_log_path, "template_sparse_frame_scan"):
            rendered_windows = timed_beat_windows(timed_beats, video_duration)
            sparse_frames = detect_sparse_frames(
                video_path,
                work_dir / "sparse_samples",
                beat_windows=[
                    (float(window["start"]), float(window["end"]))
                    for window in rendered_windows
                ],
            )
        if sparse_frames:
            first = sparse_frames[0]
            raise RuntimeError(
                "Rendered scene contains sustained nearly empty output "
                f"near {first.timestamp:.2f}s (foreground ratio {first.foreground_pixel_ratio:.4f})."
            )

        if should_run_vision_quality_check(job_id):
            provider = provider or provider_for_job(db, job_id)
            try:
                with timed_stage(debug_log_path, "template_spot_quality_scan"):
                    findings = assess_video_quality(
                        provider,
                        video_path,
                        beats,
                        work_dir / "quality_samples",
                        db,
                        job_id,
                    )
            except Exception as exc:
                if not isinstance(exc, ProviderUnavailableError) and not is_provider_capacity_exception(exc):
                    raise
                findings = []
                log_debug_timing(debug_log_path, f"TEMPLATE_SPOT_QUALITY_SKIPPED provider_unavailable={exc}")
            if findings:
                first = findings[0]
                raise RuntimeError(
                    f"Spot quality check rejected Beat {first.beat_index}: "
                    f"accuracy={first.accuracy}/5, element_layout={first.element_layout}/5."
                )

        update_job(
            db,
            job_id,
            status=JobStatus.muxing,
            progress_message="Combining audio and video.",
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
            progress_message="Video generation complete.",
            error=None,
            output_video_url=output_url,
        )
        log_debug_timing(debug_log_path, f"TEMPLATE_JOB_COMPLETE job_id={job_id}")
    except Exception as exc:
        update_job(
            db,
            job_id,
            status=JobStatus.failed,
            progress_message="Structured video generation failed.",
            error=str(exc),
        )
    finally:
        db.close()
