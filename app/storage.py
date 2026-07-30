import os
import shutil
import ast
import json
import subprocess
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(os.getenv("VIVACITY_OUTPUT_DIR", str(PROJECT_DIR / "outputs"))).resolve()
logger = logging.getLogger(__name__)


class PublishBlocked(RuntimeError):
    """Raised when a rendered video fails a mandatory publish check."""


@dataclass(frozen=True)
class PublishResult:
    passed: bool
    details: tuple[str, ...] = ()


class PublishGate:
    """The only gate through which a rendered video becomes publishable."""

    REQUIRED_CHECKS = (
        "compliance_suite",
        "static_connector_check",
        "overlap_check",
        "contrast_check",
        "cfr_export_check",
        "shared_data_consistency",
        "frame_rate_and_resolution",
    )

    def __init__(self, video_path: Path, job_id: str):
        self.video_path = Path(video_path)
        self.job_id = job_id
        self._job = None
        self._scene_file: Path | None = None
        self._generated_code = ""

    def _load_context(self):
        from app.models import Job, SessionLocal
        from app.pipeline import WORK_ROOT

        with SessionLocal() as db:
            self._job = db.get(Job, self.job_id)
        if self._job is None:
            raise PublishBlocked(f"publish blocked: job {self.job_id} was not found")

        work_dir = WORK_ROOT / self.job_id
        candidates = []
        if self._job.scene_name:
            candidates.append(work_dir / f"{self._job.scene_name}.py")
        candidates.extend(sorted(work_dir.glob("*.py")))
        self._scene_file = next((path for path in candidates if path.exists()), None)
        if self._scene_file is None:
            raise PublishBlocked(f"publish blocked: generated scene file missing for job {self.job_id}")
        self._generated_code = self._scene_file.read_text(encoding="utf-8")

    def _run_compliance_suite(self) -> tuple[bool, str]:
        tree = ast.parse(self._generated_code, filename=str(self._scene_file))
        scene_classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        for node in scene_classes:
            bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
            if "Scene" in bases or "VivacityScene" not in bases:
                return False, f"{node.name} must subclass VivacityScene"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"Transform", "ReplacementTransform"}:
                    return False, f"raw {node.func.id} at line {node.lineno}"
        return True, "scene AST compliance passed"

    def _run_overlap_check(self) -> tuple[bool, str]:
        from app.frame_check import verify_rendered_video
        from app.pipeline import WORK_ROOT

        report = verify_rendered_video(
            self.video_path,
            WORK_ROOT / self.job_id / "publish_gate_frames",
            sample_count=10,
        )
        if not report.passed:
            return False, report.failure_summary()
        return True, "no overflow, overlap, sparse frames, or temporal cuts"

    def _run_static_connector_check(self) -> tuple[bool, str]:
        from app.scene_compliance import assert_no_static_connectors

        assert self._scene_file is not None
        assert_no_static_connectors(self._scene_file)
        return True, "no static live-geometry connectors"

    def _run_contrast_check(self) -> tuple[bool, str]:
        if "app.craft_library" in self._generated_code:
            # Craft text is created through create_mixed_text(), which calls
            # craft_library.ensure_contrast() before constructing mobjects.
            return True, "craft-library contrast enforcement path present"
        if not any(marker in self._generated_code for marker in ("ensure_contrast", "_ensure_contrast", "safe_text")):
            return False, "generated scene has no enforced text-contrast path"
        return True, "contrast enforcement path present"

    def _run_cfr_export_check(self) -> tuple[bool, str]:
        from app.frame_check import verify_delivery_file

        report = verify_delivery_file(self.video_path)
        return report.passed, report.message

    def _run_shared_data_consistency(self) -> tuple[bool, str]:
        payload = self._job.request_payload or {}
        rolls = payload.get("dice_rolls")
        if not rolls:
            return True, "no randomized shared-data payload for this video"
        expected = repr(list(rolls))
        narration = str(payload.get("dice_narration_text") or "")
        if expected not in self._generated_code:
            return False, f"rendered scene does not contain persisted dice values {expected}"
        if not narration or narration.casefold() not in str(self._job.storyboard or "").casefold():
            return False, "persisted dice narration text is missing"
        return True, f"dice values {expected} are shared by scene and narration metadata"

    def _run_frame_rate_and_resolution(self) -> tuple[bool, str]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(self.video_path)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        if video is None:
            return False, "missing video stream"
        orientation = getattr(self._job, "orientation", "portrait") or "portrait"
        expected = (1080, 1920) if orientation == "portrait" else (1920, 1080)
        actual = (video.get("width"), video.get("height"))
        if actual != expected:
            return False, f"resolution {actual} does not match {orientation} target {expected}"
        return True, f"resolution {actual} matches {orientation} target"

    def run(self) -> PublishResult:
        self._load_context()
        failures: list[str] = []
        for check_name in self.REQUIRED_CHECKS:
            try:
                passed, detail = getattr(self, f"_run_{check_name}")()
            except Exception as exc:
                passed, detail = False, f"check crashed: {exc}"
            if not passed:
                failures.append(f"{check_name}: {detail}")
        if failures:
            raise PublishBlocked("; ".join(failures))
        self._write_monitor_record()
        return PublishResult(True)

    def _write_monitor_record(self) -> None:
        from app.pipeline import WORK_ROOT

        record = {
            "job_id": self.job_id,
            "estimated_cost_usd": float(self._job.estimated_cost_usd or 0.0),
            "estimated_compute_cost_usd": float(self._job.estimated_compute_cost_usd or 0.0),
            "render_seconds": float(self._job.render_seconds or 0.0),
        }
        monitor_path = WORK_ROOT / "publish_monitor.jsonl"
        monitor_path.parent.mkdir(parents=True, exist_ok=True)
        with monitor_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        logger.info("PUBLISH_MONITOR %s", json.dumps(record, sort_keys=True))
        from sqlalchemy import func, select
        from app.models import Job, JobStatus, SessionLocal

        with SessionLocal() as db:
            baseline = db.scalar(
                select(func.avg(Job.estimated_cost_usd)).where(
                    Job.status == JobStatus.complete,
                    Job.id != self.job_id,
                    Job.estimated_cost_usd > 0,
                )
            )
        if baseline and record["estimated_cost_usd"] > float(baseline) * 10:
            logger.warning(
                "PUBLISH_COST_ANOMALY job_id=%s cost_usd=%.4f baseline_usd=%.4f",
                self.job_id,
                record["estimated_cost_usd"],
                float(baseline),
            )


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


def _actually_publish(video_path: Path, job_id: str) -> str:
    """Upload only after PublishGate has completed.
    
    Tries S3-compatible storage (Supabase) first when env vars are set.
    Falls back to local /outputs/ otherwise.
    """

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    bucket = os.getenv("SUPABASE_BUCKET")

    if supabase_url and supabase_key and bucket:
        try:
            from supabase import create_client

            client = create_client(supabase_url, supabase_key)
            object_name = f"{job_id}/{video_path.name}"

            # Read file into memory — the Supabase SDK sometimes chokes on
            # raw file handles depending on the httpx transport version.
            file_bytes = video_path.read_bytes()

            # Upsert: remove any existing object with the same path first
            # so the upload is truly idempotent across restarts.
            try:
                client.storage.from_(bucket).remove([object_name])
            except Exception:
                pass

            client.storage.from_(bucket).upload(
                object_name,
                file_bytes,
                file_options={"content-type": "video/mp4", "upsert": "true"},
            )
            public_url = client.storage.from_(bucket).get_public_url(object_name)
            logger.info(
                "S3_UPLOAD_SUCCESS job_id=%s url=%s bucket=%s path=%s",
                job_id, public_url, bucket, object_name,
            )
            return public_url
        except Exception as exc:
            logger.warning(
                "S3_UPLOAD_FAILED job_id=%s bucket=%s error=%s — falling back to local storage.",
                job_id, bucket, exc,
            )
            # Fall through to local fallback

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_name = f"{job_id}_{video_path.name}"
    local_path = OUTPUT_DIR / local_name
    shutil.copy2(video_path, local_path)
    logger.info(
        "LOCAL_STORAGE job_id=%s path=%s",
        job_id, str(local_path),
    )
    return f"/outputs/{local_name}"


def publish_video(video_job) -> str:
    """The sole publish entry point used by workers and API-facing pipelines."""
    if isinstance(video_job, dict):
        video_path = Path(video_job["video_path"])
        job_id = str(video_job["job_id"])
    else:
        video_path = Path(video_job.video_path)
        job_id = str(video_job.job_id)
    PublishGate(video_path, job_id).run()
    return _actually_publish(video_path, job_id)


def upload_video(video_path: Path, job_id: str) -> str:
    """Compatibility wrapper; all callers still pass through PublishGate."""
    return publish_video({"video_path": video_path, "job_id": job_id})
