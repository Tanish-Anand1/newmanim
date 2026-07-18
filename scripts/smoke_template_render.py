from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path


resolution = os.getenv("SMOKE_RESOLUTION", "360,640")
target_duration = max(0.8, float(os.getenv("SMOKE_DURATION_SECONDS", "1.2")))
os.environ["MANIM_RENDER_QUALITY"] = os.getenv("SMOKE_RENDER_QUALITY", "l")
os.environ["MANIM_PORTRAIT_RESOLUTION"] = resolution
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.frame_check import detect_frame_overflow, get_media_duration
from app.pipeline import find_rendered_video, render_scene, validate_generated_python
from app.template_engine import TemplateBeatInput, TemplateBeatPlan, TemplateVideoPlan, compile_template_scene


def main() -> int:
    plan = TemplateVideoPlan(
        title="Template smoke render",
        beats=[
            TemplateBeatPlan(
                beat_number=1,
                heading="Resolve the vector",
                lines=["Horizontal component"],
                equations=[r"F_x = F\cos\theta"],
                visual_kind="vector",
                visual_labels=["F"],
            )
        ],
    )
    beat_inputs = [
        TemplateBeatInput(
            beat_number=1,
            target_duration=target_duration,
            gap_before=0.0,
            on_screen="Resolve a vector into its horizontal component",
            vo_text=None,
        )
    ]

    with tempfile.TemporaryDirectory(prefix="vivacity-smoke-") as temp_dir:
        work_dir = Path(temp_dir)
        scene_name = "TemplateSmokeScene"
        code = compile_template_scene(scene_name, "portrait", beat_inputs, plan, use_mathtex=True)
        validate_generated_python(code)
        scene_file = work_dir / f"{scene_name}.py"
        scene_file.write_text(code, encoding="utf-8")

        started = time.monotonic()
        ok, output = render_scene(scene_file, scene_name, work_dir, "portrait", timeout_seconds=180)
        elapsed = time.monotonic() - started
        if not ok:
            print(output[-4000:])
            return 1

        video_path = find_rendered_video(work_dir, scene_name)
        if video_path is None:
            print("Manim returned success without an mp4 output.")
            return 1
        overflow = detect_frame_overflow(video_path, work_dir / "boundary_samples", sample_count=5)
        print(
            json.dumps(
                {
                    "render_seconds": round(elapsed, 3),
                    "resolution": resolution,
                    "video_seconds": round(get_media_duration(video_path), 3),
                    "video_bytes": video_path.stat().st_size,
                    "overflow_findings": len(overflow),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
