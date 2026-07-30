from pathlib import Path
from types import SimpleNamespace

import pytest

from app.storage import PublishBlocked, PublishGate, publish_video


def test_publish_video_cannot_skip_gate(monkeypatch, tmp_path: Path):
    bad_scene = tmp_path / "bad_scene.py"
    bad_scene.write_text(
        "from manim import *\n"
        "class Broken(Scene):\n"
        "    def construct(self):\n"
        "        self.play(ReplacementTransform(Text('a'), Text('b')))\n",
        encoding="utf-8",
    )
    fake_job = SimpleNamespace(
        scene_name="Broken",
        orientation="portrait",
        request_payload={},
        storyboard="[0-1] ON SCREEN: x | VO: x",
    )

    def load_fake_context(gate):
        gate._job = fake_job
        gate._scene_file = bad_scene
        gate._generated_code = bad_scene.read_text(encoding="utf-8")

    monkeypatch.setattr(PublishGate, "_load_context", load_fake_context)
    with pytest.raises(PublishBlocked, match="compliance_suite"):
        publish_video({"video_path": tmp_path / "missing.mp4", "job_id": "broken-job"})
