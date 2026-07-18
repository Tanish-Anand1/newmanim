import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.learning as learning
import app.main as main
import app.pipeline as pipeline
from app.llm_provider import LLMResponse


class CapturingProvider:
    name = "openai"
    model = "fake-model"

    def __init__(self):
        self.calls: list[dict] = []

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        self.calls.append({"system": system, "user_message": user_message, "max_tokens": max_tokens, "model": model})
        return LLMResponse(
            text="from manim import *\n\ndef avoid_overlap(mobj, others, min_gap=0.3):\n    return mobj\n\nclass TestScene(Scene):\n    def construct(self):\n        # --- Beat 1 params ---\n        beat1_scale = 1.0\n        beat1_gap = 1.0\n        beat1_speed = 1.0\n        # --- Beat 1 ---\n        diagram = VGroup(Text('x'))\n        diagram.scale_to_fit_height(config.frame_height * 0.55)\n        diagram.move_to(ORIGIN)\n        self.play(FadeIn(diagram), run_time=beat1_speed)\n",
            truncated=False,
            input_tokens=10,
            output_tokens=10,
        )


def point_learning_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(learning, "LEARNING_MEMORY_DIR", tmp_path)
    monkeypatch.setattr(learning, "STAGED_REFERENCES_PATH", tmp_path / "staged_reference_examples.jsonl")
    monkeypatch.setattr(learning, "APPROVED_REFERENCES_PATH", tmp_path / "approved_reference_examples.jsonl")
    monkeypatch.setattr(learning, "STAGED_FAILURES_PATH", tmp_path / "staged_failure_patterns.jsonl")
    monkeypatch.setattr(learning, "APPROVED_FAILURES_PATH", tmp_path / "approved_failure_patterns.jsonl")
    monkeypatch.setattr(learning, "CATEGORY_EVENTS_PATH", tmp_path / "category_success_events.jsonl")


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_codegen_uses_approved_learning_records_but_not_staged(monkeypatch, tmp_path: Path):
    point_learning_paths(monkeypatch, tmp_path)
    append(
        learning.APPROVED_FAILURES_PATH,
        {
            "category": "layout-or-overlap",
            "keywords": ["curve"],
            "instruction": "Keep curve labels separated with explicit buff values.",
        },
    )
    append(
        learning.APPROVED_REFERENCES_PATH,
        {
            "category": "curve-plot",
            "job_id": "approved-job",
            "code": "# --- Beat 1 ---\nself.wait(1)",
        },
    )
    append(
        learning.STAGED_REFERENCES_PATH,
        {
            "category": "curve-plot",
            "job_id": "staged-job",
            "code": "# staged code must not be injected",
        },
    )
    provider = CapturingProvider()
    beat = pipeline.StoryboardBeat(1, 0, 1, "Plot a curve with a tangent label", "Plot it.")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

    pipeline.generate_manim_code(provider, '[0-1] ON SCREEN: Plot a curve | VO: "Plot it."', "TestScene", timed)

    system = provider.calls[0]["system"]
    assert "APPROVED LEARNED REFERENCE" in system
    assert "approved-job" in system
    assert "staged code must not be injected" not in system
    assert "APPROVED FAILURE-PATTERN REMINDERS" in system
    assert "explicit buff values" in system


def test_stage_verified_reference_skips_failed_beat(monkeypatch, tmp_path: Path):
    point_learning_paths(monkeypatch, tmp_path)
    code = """
# --- Beat 1 params ---
beat1_scale = 1.0
# --- Beat 1 ---
self.wait(1)
# --- Beat 2 params ---
beat2_scale = 1.0
# --- Beat 2 ---
self.wait(1)
"""
    staged = learning.stage_verified_reference_examples(
        job_id="job-1",
        scene_name="Scene",
        storyboard='[0-1] ON SCREEN: Plot curve | VO: "x"',
        beats=[
            learning.LearningBeat(1, "Plot a curve"),
            learning.LearningBeat(2, "Resolve forces"),
        ],
        code=code,
        quality_scores=[{"beat_index": 2, "accuracy": 3, "element_layout": 5}],
        quality_threshold=4,
    )

    records = learning.read_jsonl(learning.STAGED_REFERENCES_PATH)
    assert staged == 1
    assert len(records) == 1
    assert records[0]["beat_number"] == 1
    assert records[0]["review_status"] == "staged"
    assert "self.wait(1)" in records[0]["code"]


def test_stage_failure_fix_and_learning_summary(monkeypatch, tmp_path: Path):
    point_learning_paths(monkeypatch, tmp_path)

    learning.stage_failure_fix(
        job_id="job-1",
        scene_name="Scene",
        beat_number=2,
        failure_feedback="Frame maps to Beat 2. Failed scored checks: element_layout=3/5.",
        fixed_code="label.next_to(curve, buff=0.3)\nself.play(FadeOut(old_label))",
    )
    learning.record_job_category_events(
        job_id="job-1",
        scene_name="Scene",
        beats=[learning.LearningBeat(1, "Draw a force diagram"), learning.LearningBeat(2, "Plot two curves")],
        outcome="success",
        retry_count=0,
    )

    failures = learning.read_jsonl(learning.STAGED_FAILURES_PATH)
    summary = learning.learning_summary()

    assert failures[0]["error_type"] == "layout-or-overlap"
    assert "explicit spacing buffers" in failures[0]["fix_applied"]
    assert summary["staged_failure_patterns"] == 1
    assert any(row["category"] == "force-diagram" for row in summary["categories"])


def test_internal_learning_summary_requires_admin(monkeypatch, tmp_path: Path):
    point_learning_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    learning.record_category_event(
        job_id="job-1",
        scene_name="Scene",
        beat_number=1,
        category="curve-plot",
        outcome="failure",
        retry_count=4,
    )

    client = TestClient(main.app)
    unauthorized = client.get("/api/internal/learning/summary")
    authorized = client.get("/api/internal/learning/summary", headers={"x-admin-token": "admin-test"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["categories"][0]["category"] == "curve-plot"
