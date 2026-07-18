import os
import shutil
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(os.getenv("VIVACITY_OUTPUT_DIR", str(PROJECT_DIR / "outputs"))).resolve()


def verify_render_quality(video_path: Path, job_id: str) -> None:
    """Run verification checks on the final rendered video to prevent cuts, overlapping, and frame-out glitches."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        from app.models import SessionLocal, Job
        from app.pipeline import WORK_ROOT, parse_storyboard
        from app.preflight import run_preflight_gate, format_gate_report
    except ImportError as exc:
        logger.warning("Could not import verification modules: %s; skipping quality gate.", exc)
        return

    # 1. Fetch job metadata from DB
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                logger.warning("Job %s not found in DB; skipping quality verification.", job_id)
                return
            storyboard = job.storyboard or job.generated_storyboard
            scene_name = job.scene_name
    except Exception as exc:
        logger.warning("Database query failed while fetching job %s: %s; skipping quality verification.", job_id, exc)
        return

    if not storyboard:
        logger.warning("No storyboard found for job %s; skipping quality verification.", job_id)
        return

    # 2. Locate generated python code file in work directory
    work_dir = WORK_ROOT / job_id
    if not work_dir.exists():
        logger.warning("Work directory %s does not exist; skipping quality verification.", work_dir)
        return

    scene_file = None
    if scene_name:
        possible_names = [
            scene_name,
            f"CraftScene_{job_id.replace('-', '_')}",
            f"TemplateScene_{job_id.replace('-', '_')}",
        ]
        for name in possible_names:
            p = work_dir / f"{name}.py"
            if p.exists():
                scene_file = p
                break

    if not scene_file:
        py_files = list(work_dir.glob("*.py"))
        if py_files:
            scene_file = py_files[0]

    if not scene_file or not scene_file.exists():
        logger.warning("No generated python scene file found in %s; skipping quality verification.", work_dir)
        return

    try:
        generated_code = scene_file.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read python scene file %s: %s; skipping quality verification.", scene_file, exc)
        return

    # 3. Parse storyboard beats
    try:
        beats = parse_storyboard(storyboard)
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
    except Exception as exc:
        logger.warning("Failed to parse storyboard for job %s: %s; skipping quality verification.", job_id, exc)
        return

    # 4. Run verification checks
    logger.info("Running quality verification gate on final render: %s", video_path)
    try:
        gate_passed, gate_results = run_preflight_gate(
            draft_video_path=video_path,
            work_dir=work_dir,
            generated_code=generated_code,
            storyboard=storyboard,
            timed_beats=timed_beats_list,
            sample_count=10,
        )
    except Exception as exc:
        logger.error("Quality verification gate crashed on final render %s: %s", video_path, exc, exc_info=True)
        raise RuntimeError(f"Quality verification gate crashed: {exc}") from exc

    gate_report = format_gate_report(gate_results)
    logger.info("Verification gate report for job %s:\n%s", job_id, gate_report)

    if not gate_passed:
        failed_checks = [r for r in gate_results if not r.passed]
        raise RuntimeError(
            f"Verification gate FAILED for final video ({len(failed_checks)}/6 checks failed). "
            + "; ".join(r.summary for r in failed_checks)
            + "\n\nFull report:\n"
            + gate_report
        )
    logger.info("Verification gate PASSED for final video successfully.")


def upload_video(video_path: Path, job_id: str) -> str:
    """Upload to Supabase when configured, otherwise expose through local static files."""
    # Perform pre-delivery render verification gate checks
    verify_render_quality(video_path, job_id)

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    bucket = os.getenv("SUPABASE_BUCKET")

    if supabase_url and supabase_key and bucket:
        from supabase import create_client

        client = create_client(supabase_url, supabase_key)
        object_name = f"{job_id}/{video_path.name}"
        with video_path.open("rb") as fh:
            client.storage.from_(bucket).upload(
                object_name,
                fh,
                file_options={"content-type": "video/mp4", "upsert": True},
            )
        return client.storage.from_(bucket).get_public_url(object_name)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_name = f"{job_id}_{video_path.name}"
    local_path = OUTPUT_DIR / local_name
    shutil.copy2(video_path, local_path)
    return f"/outputs/{local_name}"
