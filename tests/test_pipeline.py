from pathlib import Path
import subprocess
from types import SimpleNamespace

import app.pipeline as pipeline
from app.llm_provider import LLMResponse
from app.models import Job, SessionLocal, init_db
from sqlalchemy import text
import pytest


VALID_SCENE_CODE = """from manim import *

TITLE_COLOR = TEAL_C
PRIMARY_COLOR = BLUE_C
SECONDARY_COLOR = WHITE
STRUCTURE_COLOR = GREY_B
RELATION_COLOR = YELLOW_C
HIGHLIGHT_COLOR = ORANGE
SPECIAL_COLOR = PURPLE_C
POSITIVE_COLOR = GREEN_C
NEGATIVE_COLOR = RED_C
REFERENCE_CURVE_COLOR = WHITE
PRIMARY_CURVE_COLOR = BLUE_C
SECONDARY_CURVE_COLOR = GOLD_A
CENTRAL_ATOM_COLOR = PRIMARY_COLOR
SURROUNDING_ATOM_COLOR = SECONDARY_COLOR
BOND_COLOR = RELATION_COLOR
LONE_PAIR_COLOR = SPECIAL_COLOR
ANGLE_COLOR = HIGHLIGHT_COLOR
FORCE_COLOR = PRIMARY_COLOR

def avoid_overlap(mobj, others, min_gap=0.3):
    return mobj

class TestScene(Scene):
    def construct(self):
        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 1.0
        beat1_speed = 1.0
        # --- Beat 1 ---
        existing_mobjects = []
        label = Text("x")
        avoid_overlap(label, existing_mobjects)
        diagram = VGroup(label)
        diagram.scale_to_fit_height(config.frame_height * 0.55)
        diagram.move_to(ORIGIN)
        self.play(FadeIn(diagram), run_time=beat1_speed)
"""


class FakeProvider:
    def __init__(self, name: str = "anthropic", model: str = "fake-model", responses: list[str] | None = None):
        self.name = name
        self.model = model
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        self.calls.append({"system": system, "user_message": user_message, "max_tokens": max_tokens, "model": model})
        text_response = self.responses.pop(0) if self.responses else VALID_SCENE_CODE
        return LLMResponse(text=text_response, truncated=False, input_tokens=1000, output_tokens=200)

    def inspect_image(self, frame_path: Path, prompt: str, max_tokens: int) -> LLMResponse:
        self.calls.append({"frame_path": frame_path, "prompt": prompt, "max_tokens": max_tokens})
        return LLMResponse(
            text=(
                '{"accuracy": 5, "depth": 4, "logical_flow": 5, '
                '"visual_relevance": 5, "element_layout": 5, "summary": "Frame is readable."}'
            ),
            truncated=False,
            input_tokens=500,
            output_tokens=20,
        )


class RateLimitError(Exception):
    def __init__(self, retry_after: str | None = None):
        self.status_code = 429
        self.response = SimpleNamespace(status_code=429, headers={"Retry-After": retry_after} if retry_after is not None else {})
        super().__init__("429 Too Many Requests")


def test_silent_beat_does_not_call_tts(monkeypatch, tmp_path: Path):
    storyboard = """
TITLE: Silent Test
TARGET LENGTH: 4

[0-2] ON SCREEN: A title appears | VO: "(silent)"
[2-4] ON SCREEN: The title fades | VO: "Now it fades."
"""
    beats = pipeline.parse_storyboard(storyboard)
    calls: list[str] = []

    def fake_tts(text: str, out_path: Path, *_) -> None:
        calls.append(text)
        out_path.write_bytes(b"fake mp3")

    def fake_duration(path: Path) -> float:
        return 1.25

    monkeypatch.setattr(pipeline, "generate_tts_audio", fake_tts)
    monkeypatch.setattr(pipeline, "get_media_duration", fake_duration)
    monkeypatch.setattr(pipeline, "TTS_PROVIDER", "openai")

    timed = pipeline.generate_timed_beat_audio(beats, tmp_path)

    assert calls == ["Now it fades."]
    assert timed[0].audio_path is None
    assert timed[0].target_duration == 2
    assert timed[1].audio_path is not None
    assert timed[1].target_duration == 2


def test_timed_beat_duration_keeps_authored_pacing_without_rushing_tts():
    beat = pipeline.StoryboardBeat(1, 0, 5, "Show the equation", "Narrate it.")

    assert pipeline.timed_beat_duration(beat, 3.2) == 5
    assert pipeline.timed_beat_duration(beat, 6.4) == 6.4


def test_timed_beat_windows_follow_audio_aware_render_durations():
    first = pipeline.StoryboardBeat(1, 0, 5, "First", "One")
    second = pipeline.StoryboardBeat(2, 5, 10, "Second", "Two")
    timed = [
        pipeline.TimedBeat(first, None, 6.0, 0.0),
        pipeline.TimedBeat(second, None, 5.0, 0.5),
    ]

    assert pipeline.timed_beat_windows(timed) == [
        {"beat_number": 1, "start": 0.0, "end": 6.0},
        {"beat_number": 2, "start": 6.5, "end": 11.5},
    ]


def test_tts_cache_reuses_identical_clip_and_separates_speeds(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, str, str, float]] = []
    monkeypatch.setattr(pipeline, "TTS_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(pipeline, "TTS_CACHE_ENABLED", True)

    def fake_synthesize(text: str, out_path: Path, model: str, voice: str, speed: float) -> None:
        calls.append((text, model, voice, speed))
        out_path.write_bytes(b"audio")

    monkeypatch.setattr(pipeline, "_synthesize_openai_tts", fake_synthesize)
    first = tmp_path / "first.mp3"
    second = tmp_path / "second.mp3"
    pipeline.generate_tts_audio("Same narration", first, model="tts-1-hd", voice="alloy", speed=0.92)
    pipeline.generate_tts_audio("Same narration", second, model="tts-1-hd", voice="alloy", speed=0.92)
    pipeline.generate_tts_audio("Same narration", tmp_path / "slower.mp3", model="tts-1-hd", voice="alloy", speed=0.85)

    assert calls == [
        ("Same narration", "tts-1-hd", "alloy", 0.92),
        ("Same narration", "tts-1-hd", "alloy", 0.85),
    ]
    assert first.read_bytes() == second.read_bytes() == b"audio"


def test_text_lifecycle_feedback_requires_transform_for_morph_beat():
    beat = pipeline.StoryboardBeat(
        index=3,
        start_sec=9,
        end_sec=15,
        on_screen_text='Ratio "PF / PD" appears as text, morphs into "e"',
        vo_text="The ratio becomes e.",
    )
    code = """
class Scene:
    def construct(self):
        # --- Beat 3 ---
        old = MathTex("PF / PD")
        new = MathTex("e")
        self.play(Write(old))
        self.play(Write(new))
"""

    feedback = pipeline.text_lifecycle_feedback([beat], code)

    assert feedback is not None
    assert "Beat 3" in feedback


def test_overlap_feedback_identifies_beat_section():
    beats = [
        pipeline.StoryboardBeat(1, 0, 4, "Intro", "Hi"),
        pipeline.StoryboardBeat(2, 4, 9, "Middle", "Keep going"),
        pipeline.StoryboardBeat(3, 9, 15, 'Ratio "PF / PD" morphs into "e"', "The ratio changes."),
    ]

    feedback = pipeline.build_overlap_feedback(
        beats,
        12.4,
        "Use ReplacementTransform, Transform, or FadeOut before placing new Text or MathTex near the same position.",
    )

    assert "Beat 3" in feedback
    assert "leave other beats untouched" in feedback


def test_attempt_timeout_guard_raises():
    start = 100.0

    def fake_monotonic() -> float:
        return start + pipeline.ATTEMPT_WALL_CLOCK_LIMIT_SECONDS + 1

    original = pipeline.time.monotonic
    pipeline.time.monotonic = fake_monotonic
    try:
        try:
            pipeline.ensure_attempt_time_remaining(start, 2)
        except TimeoutError as exc:
            assert "wall-clock limit" in str(exc)
        else:
            raise AssertionError("Expected a TimeoutError")
    finally:
        pipeline.time.monotonic = original


def test_render_scene_normalizes_missing_subprocess_output(monkeypatch, tmp_path: Path):
    def fake_run_command(*_, **__):
        return subprocess.CompletedProcess(args=["manim"], returncode=1, stdout="render failed", stderr=None)

    monkeypatch.setattr(pipeline, "run_command", fake_run_command)

    ok, output = pipeline.render_scene(tmp_path / "Scene.py", "Scene", tmp_path)

    assert ok is False
    assert "render failed" in output


def test_render_scene_normalizes_timeout_bytes(monkeypatch, tmp_path: Path):
    def fake_run_command(*_, **__):
        raise subprocess.TimeoutExpired(
            cmd=["manim"],
            timeout=3,
            output=b"partial stdout",
            stderr=None,
        )

    monkeypatch.setattr(pipeline, "run_command", fake_run_command)

    ok, output = pipeline.render_scene(tmp_path / "Scene.py", "Scene", tmp_path, timeout_seconds=3)

    assert ok is False
    assert "timed out" in output
    assert "partial stdout" in output


def test_run_command_forces_utf8_subprocess_decoding(monkeypatch, tmp_path: Path):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.run_command(["fake"], cwd=tmp_path, check=False, timeout_seconds=5)

    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["text"] is True


def test_validation_subloop_exhaustion_advances_to_next_outer_attempt(monkeypatch, tmp_path: Path):
    init_db()
    db = SessionLocal()
    try:
        job = Job(max_attempts=pipeline.MAX_RETRIES)
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    beat = pipeline.StoryboardBeat(1, 0, 1, "Title appears", "Title.")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]
    video_path = tmp_path / "render.mp4"
    video_path.write_bytes(b"fake video")
    render_attempts: list[int] = []
    quality_calls = {"count": 0}

    monkeypatch.setattr(pipeline, "get_llm_provider", lambda provider_name=None: FakeProvider())
    monkeypatch.setattr(pipeline, "WORK_ROOT", tmp_path / "runs")
    monkeypatch.setattr(pipeline, "validate_storyboard_or_raise", lambda storyboard, max_target_seconds=pipeline.MAX_TARGET_SECONDS: [beat])
    monkeypatch.setattr(pipeline, "generate_timed_beat_audio", lambda beats, audio_dir, debug_log_path=None, db=None, job_id=None: timed)
    monkeypatch.setattr(pipeline, "concatenate_audio", lambda timed_beats, audio_dir, out_path: out_path.write_bytes(b"audio"))
    monkeypatch.setattr(
        pipeline,
        "render_scene",
        lambda scene_file, scene_name, work_dir, orientation="portrait", timeout_seconds=None: (True, ""),
    )
    monkeypatch.setattr(pipeline, "render_scene_for_job", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(pipeline, "find_rendered_video", lambda work_dir, scene_name: video_path)
    monkeypatch.setattr(pipeline, "get_media_duration", lambda path: 1.0)
    monkeypatch.setattr(pipeline, "text_lifecycle_feedback", lambda beats, code: None)
    monkeypatch.setattr(pipeline, "should_run_vision_quality_check", lambda job_id, manual_requested=False: True)
    monkeypatch.setattr(pipeline, "stretch_audio_to_duration", lambda audio_path, target_duration, out_path: out_path.write_bytes(b"audio"))
    monkeypatch.setattr(pipeline, "mux_audio_video", lambda video_path, audio_path, out_path: out_path.write_bytes(b"video"))
    monkeypatch.setattr(pipeline, "assert_delivery_file_clean", lambda path: None)
    monkeypatch.setattr(pipeline, "assert_rendered_video_clean", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "upload_video", lambda final_path, job_id: "/outputs/final.mp4")

    def fake_generate_valid(**kwargs):
        render_attempts.append(kwargs["render_attempt"])
        return VALID_SCENE_CODE

    def fake_assess_video_quality(provider, video_path, beats, out_dir, db=None, job_id=None):
        quality_calls["count"] += 1
        if quality_calls["count"] <= pipeline.OVERLAP_RETRY_LIMIT + 1:
            return [pipeline.FrameQualityScore(0.5, tmp_path / "frame.png", 1, 5, 5, 5, 5, 2, "Layout issue.")]
        return []

    monkeypatch.setattr(pipeline, "generate_valid_manim_code", fake_generate_valid)
    monkeypatch.setattr(pipeline, "assess_video_quality", fake_assess_video_quality)

    pipeline.run_pipeline_for_job(
        job_id,
        '[0-1] ON SCREEN: Title appears | VO: "Title."',
        "TestScene",
    )

    db = SessionLocal()
    try:
        db_job = db.get(Job, job_id)
        assert db_job is not None
        assert db_job.status.value == "complete"
        assert db_job.attempt_number == 2
        assert 2 in render_attempts
    finally:
        db.close()


def test_mocked_pipeline_job_records_active_provider_cost(monkeypatch, tmp_path: Path):
    init_db()

    for provider_name in ("anthropic", "openai"):
        db = SessionLocal()
        try:
            job = Job(max_attempts=pipeline.MAX_RETRIES, cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = job.id
        finally:
            db.close()

        video_path = tmp_path / f"{provider_name}.mp4"
        video_path.write_bytes(b"fake video")
        provider = FakeProvider(name=provider_name, model=f"{provider_name}-model")

        monkeypatch.setattr(pipeline, "WORK_ROOT", tmp_path / f"runs_{provider_name}")
        monkeypatch.setattr(pipeline, "get_llm_provider", lambda provider_name=None, provider=provider: provider)
        monkeypatch.setattr(pipeline, "concatenate_audio", lambda timed_beats, audio_dir, out_path: out_path.write_bytes(b"audio"))
        monkeypatch.setattr(
            pipeline,
            "render_scene",
            lambda scene_file, scene_name, work_dir, orientation="portrait", timeout_seconds=None: (True, ""),
        )
        monkeypatch.setattr(pipeline, "render_scene_for_job", lambda *args, **kwargs: (True, ""))
        monkeypatch.setattr(pipeline, "find_rendered_video", lambda work_dir, scene_name, video_path=video_path: video_path)
        monkeypatch.setattr(pipeline, "get_media_duration", lambda path: 1.0)
        monkeypatch.setattr(pipeline, "assess_video_quality", lambda provider, video_path, beats, out_dir, db=None, job_id=None: [])
        monkeypatch.setattr(pipeline, "stretch_audio_to_duration", lambda audio_path, target_duration, out_path: out_path.write_bytes(b"audio"))
        monkeypatch.setattr(pipeline, "mux_audio_video", lambda video_path, audio_path, out_path: out_path.write_bytes(b"video"))
        monkeypatch.setattr(pipeline, "assert_delivery_file_clean", lambda path: None)
        monkeypatch.setattr(pipeline, "assert_rendered_video_clean", lambda *args, **kwargs: None)
        monkeypatch.setattr(pipeline, "upload_video", lambda final_path, job_id: f"/outputs/{provider_name}.mp4")

        pipeline.run_pipeline_for_job(
            job_id,
            '[0-1] ON SCREEN: Title appears | VO: "(silent)"',
            "TestScene",
        )

        db = SessionLocal()
        try:
            db_job = db.get(Job, job_id)
            assert db_job is not None
            assert db_job.status.value == "complete"
            assert db_job.cost_breakdown[provider_name]["calls"] == 1
            assert db_job.cost_breakdown[provider_name]["model"] == f"{provider_name}-model"
            assert db_job.estimated_cost_usd > 0
        finally:
            db.close()


def test_orientation_resolution_and_frame_prompt():
    assert pipeline.orientation_resolution("portrait") == "1080,1920"
    assert pipeline.orientation_resolution("landscape") == "1920,1080"
    assert pipeline.orientation_frame_dimensions("portrait") == (4.5, 8.0)
    assert pipeline.orientation_frame_dimensions("landscape") == (14.222222222222221, 8.0)
    assert "vertical 9:16" in pipeline.frame_constraint_for_orientation("portrait")
    assert "horizontal 16:9" in pipeline.frame_constraint_for_orientation("landscape")


def test_orientation_render_config_uses_matching_logical_frame(tmp_path: Path):
    config_path = pipeline.write_orientation_render_config(tmp_path, "portrait")
    config = config_path.read_text(encoding="utf-8")
    assert "pixel_width = 1080" in config
    assert "pixel_height = 1920" in config
    assert "frame_width = 4.50000000" in config
    assert "frame_height = 8.00000000" in config


def test_replace_storyboard_beat_preserves_boundaries_and_silent_marker():
    storyboard = """
# Approach: test
[0-4] ON SCREEN: Intro | VO: "Hello"
[4-8] ON SCREEN: Explain | VO: "Old line"
"""
    edited = pipeline.replace_storyboard_beat(storyboard, 2, "New visual", "(silent)")
    beats = pipeline.parse_storyboard(edited)

    assert beats[1].start_sec == 4
    assert beats[1].end_sec == 8
    assert beats[1].on_screen_text == "New visual"
    assert beats[1].vo_text is None


def test_generate_storyboard_draft_returns_cost():
    provider = FakeProvider(
        name="openai",
        model="gpt-5.5",
        responses=['# Approach: definition first\n[0-4] ON SCREEN: Taylor series formula `f(x)=\\sum_{n=0}^{\\infty}a_n(x-a)^n` | VO: "Taylor series uses polynomial terms."'],
    )

    draft = pipeline.generate_storyboard_draft("Taylor series", 30, "JEE aspirants", provider=provider)

    assert draft["storyboard"].startswith("# Approach:")
    assert draft["cost_breakdown"]["openai"]["calls"] == 2
    assert draft["cost_breakdown"]["openai"]["model"] == "gpt-5.5"
    assert draft["estimated_cost_usd"] > 0


def test_storyboard_draft_uses_local_fallback_when_provider_capacity_is_unavailable():
    class UnavailableProvider(FakeProvider):
        def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
            raise RateLimitError()

    draft = pipeline.generate_storyboard_draft(
        "Taylor series",
        60,
        "JEE aspirants",
        provider=UnavailableProvider(name="gemini", model="gemini-fast"),
    )
    beats = pipeline.validate_storyboard_or_raise(draft["storyboard"], max_target_seconds=60)

    assert len(beats) >= 8
    assert beats[-1].end_sec == 60
    assert "\\sum" in draft["storyboard"]
    assert draft["estimated_cost_usd"] == 0
    assert draft["cost_breakdown"]["gemini"]["calls"] == 0


def test_storyboard_integrity_rejects_generic_scaffold_and_missing_topic_terms():
    leaked = (
        '# Approach: generic\n'
        '[0-4] ON SCREEN: Highlight known information and the target quantity | VO: "Use a symbolic example."\n'
        '[4-8] ON SCREEN: Show a three-step process: identify, relate, solve | VO: "Arrange a cause-and-effect map."'
    )
    try:
        pipeline.validate_generated_storyboard_integrity("Atwood machine", leaked)
    except ValueError as exc:
        assert "generic scaffold phrase" in str(exc)
    else:
        raise AssertionError("Expected leaked scaffold storyboard to fail integrity validation")

    underspecified = (
        '# Approach: overview\n'
        '[0-4] ON SCREEN: Molecular structure | VO: "A central idea."\n'
        '[4-8] ON SCREEN: Geometric construction | VO: "Observe the arrangement."'
    )
    try:
        pipeline.validate_generated_storyboard_integrity(
            "VSEPR theory using NH3 and CH4 with bond angles 109.5 and 107 degrees",
            underspecified,
        )
    except ValueError as exc:
        assert "topic-term coverage" in str(exc)
        assert "NH3" in str(exc)
    else:
        raise AssertionError("Expected a topic-free chemistry storyboard to fail integrity validation")


def test_topic_term_extraction_and_coverage_are_domain_agnostic():
    topic = "VSEPR theory using NH3 and CH4 as examples, showing bond angles 109.5 and 107 degrees"
    assert pipeline.extract_topic_key_terms(topic) == ["VSEPR", "NH3", "CH4", "bond angles", "109.5", "107"]

    storyboard = (
        '# Approach: compare electron domains\n'
        '[0-5] ON SCREEN: Compare VSEPR models for NH3 and CH4 | VO: "Both molecules arrange electron domains."\n'
        '[5-10] ON SCREEN: Mark bond angles 109.5° and 107° | VO: "The lone pair compresses the ammonia angle."'
    )
    coverage = pipeline.validate_generated_storyboard_integrity(topic, storyboard)

    assert coverage.ratio == 1.0
    assert coverage.missing_terms == ()
    assert pipeline.topic_term_is_present("NH3", "Ammonia has one lone pair.")
    assert pipeline.topic_term_is_present("CH4", "Methane is tetrahedral.")


def test_topic_term_gate_generalizes_across_unrelated_subjects():
    cases = (
        (
            "DNA replication with helicase, DNA polymerase, leading strand and lagging strand",
            '[0-6] ON SCREEN: DNA replication fork with helicase | VO: "DNA polymerase extends the leading strand and lagging strand."',
        ),
        (
            "Lagrange multipliers for constrained optimization using gradient vectors",
            '[0-6] ON SCREEN: Lagrange multipliers for constrained optimization | VO: "Gradient vectors become parallel at the constrained optimum."',
        ),
        (
            "Dijkstra shortest path using a priority queue on a weighted graph",
            '[0-6] ON SCREEN: Dijkstra shortest path on a weighted graph | VO: "A priority queue selects the smallest tentative distance."',
        ),
    )
    generic = '[0-6] ON SCREEN: Core idea | VO: "Observe the general structure and process."'

    for topic, specific_storyboard in cases:
        try:
            pipeline.validate_generated_storyboard_integrity(topic, generic)
        except ValueError as exc:
            assert "topic-term coverage" in str(exc)
        else:
            raise AssertionError(f"Expected generic storyboard for {topic!r} to fail")
        coverage = pipeline.validate_generated_storyboard_integrity(topic, specific_storyboard)
        assert coverage.ratio >= pipeline.TOPIC_TERM_COVERAGE_THRESHOLD


def test_topic_term_gate_rejects_full_topic_echo_as_placeholder_content():
    topic = "DNA replication with helicase and DNA polymerase"
    storyboard = pipeline.build_local_storyboard_draft(topic, 30, "biology students")

    try:
        pipeline.validate_generated_storyboard_integrity(topic, storyboard)
    except ValueError as exc:
        assert "full-topic echoing" in str(exc)
    else:
        raise AssertionError("Expected repeated topic text inside generic fallback beats to fail")


def test_storyboard_draft_regenerates_after_scaffold_leak():
    leaked = (
        '# Approach: generic\n'
        '[0-4] ON SCREEN: Highlight known information and the target quantity | VO: "Use a symbolic example."'
    )
    valid = (
        '# Approach: Newton laws first\n'
        '[0-4] ON SCREEN: Atwood machine with a pulley, m1, and m2 | VO: "Two masses share one string over a pulley."\n'
        '[4-8] ON SCREEN: Label tension T and acceleration a | VO: "The same tension acts on both masses."\n'
        '[8-12] ON SCREEN: Write `T-m_1g=m_1a` and `m_2g-T=m_2a` | VO: "Apply Newton law to each mass."\n'
        '[12-16] ON SCREEN: Write `a=\\frac{(m_2-m_1)g}{m_1+m_2}` | VO: "The mass difference sets the acceleration."'
    )
    provider = FakeProvider(name="gemini", model="gemini-test", responses=[leaked, valid])

    draft = pipeline.generate_storyboard_draft("Atwood machine", 30, "JEE aspirants", provider=provider)

    assert "known information" not in draft["storyboard"].lower()
    assert "m_1" in draft["storyboard"]
    assert len(provider.calls) == 3
    assert draft["cost_breakdown"]["gemini"]["calls"] == 3


def test_local_atwood_fallback_is_topic_specific_and_passes_integrity():
    storyboard = pipeline.build_local_storyboard_draft("Atwood machine", 60, "JEE aspirants")

    pipeline.validate_generated_storyboard_integrity("Atwood machine", storyboard)
    assert "m_1" in storyboard
    assert "tension T" in storyboard
    assert "cause-and-effect" not in storyboard.lower()


def test_local_vsepr_fallback_preserves_requested_entities_and_angles():
    topic = "VSEPR theory using NH3 and CH4 with bond angles 109.5 and 107 degrees"
    storyboard = pipeline.build_local_storyboard_draft(topic, 60, "JEE aspirants")

    coverage = pipeline.validate_generated_storyboard_integrity(topic, storyboard)

    assert coverage.ratio == 1.0
    assert "solid wedge" in storyboard
    assert "dashed bond" in storyboard
    assert "lone pair" in storyboard
    assert "109.5" in storyboard
    assert "107" in storyboard


def test_storyboard_integrity_rejects_duplicate_connectors_and_underexplained_math():
    duplicate = (
        '# Approach: derivative pattern\n'
        '[0-5] ON SCREEN: Taylor coefficients then then appear | VO: "Each derivative supplies a coefficient."'
    )
    sparse_math = (
        '# Approach: derivative pattern\n'
        '[0-5] ON SCREEN: `f^(n)(a)` and `(x-a)^n` | VO: "Two terms."'
    )

    for storyboard, expected in ((duplicate, "duplicate connector"), (sparse_math, "five words")):
        try:
            pipeline.validate_generated_storyboard_integrity("Taylor series", storyboard)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"Expected storyboard integrity failure containing {expected!r}")


def test_storyboard_integrity_rejects_maclaurin_letter_o_center():
    storyboard = (
        '# Approach: derivatives at zero\n'
        '[0-5] ON SCREEN: Write `f^{(n)}(o)` for the coefficient | '
        'VO: "Evaluate every derivative at the Maclaurin center before substitution."'
    )

    try:
        pipeline.validate_generated_storyboard_integrity("Maclaurin series", storyboard)
    except ValueError as exc:
        assert "letter-o" in str(exc)
    else:
        raise AssertionError("Expected letter o at the Maclaurin center to fail integrity validation")


def test_storyboard_draft_repairs_mojibake_and_writes_raw_response_audit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pipeline, "WORK_ROOT", tmp_path / "runs")
    mojibake = '# Approach: symbols\n[0-6] ON SCREEN: Greek symbols Î¸, Î£, 90Â°, and â€” | VO: "Î¸ and Î£."'
    provider = FakeProvider(name="openai", model="gpt-5.5", responses=[mojibake])

    draft = pipeline.generate_storyboard_draft("Greek symbols", 30, "students", job_id="unicode-job", provider=provider)

    assert "θ" in draft["storyboard"]
    assert "Σ" in draft["storyboard"]
    assert "90°" in draft["storyboard"]
    assert "—" in draft["storyboard"]
    audit_dir = tmp_path / "runs" / "unicode-job"
    assert (audit_dir / "storyboard_llm_raw_response_utf8.bin").read_bytes() == mojibake.encode("utf-8")
    assert (audit_dir / "storyboard_llm_normalized_text.txt").read_text(encoding="utf-8") == draft["storyboard"]


def test_render_workspace_reset_preserves_storyboard_audits(tmp_path: Path):
    work_dir = tmp_path / "job"
    work_dir.mkdir()
    (work_dir / "generated_storyboard.txt").write_text("VSEPR NH3 CH4", encoding="utf-8")
    (work_dir / "storyboard_topic_coverage.jsonl").write_text('{"ratio": 1.0}\n', encoding="utf-8")
    (work_dir / "old_render.tmp").write_text("stale", encoding="utf-8")

    pipeline.reset_job_render_workspace(work_dir)

    assert (work_dir / "generated_storyboard.txt").read_text(encoding="utf-8") == "VSEPR NH3 CH4"
    assert (work_dir / "storyboard_topic_coverage.jsonl").read_text(encoding="utf-8") == '{"ratio": 1.0}\n'
    assert not (work_dir / "old_render.tmp").exists()


def test_normalize_generated_text_repairs_common_mojibake():
    corrupted = "Ï€ and Î£ use â€” with xÂ²"

    repaired = pipeline.normalize_generated_text(corrupted)

    assert repaired == "π and Σ use — with x²"


def test_normalize_generated_text_repairs_mixed_correct_unicode_and_mojibake():
    corrupted = "θ is already correct, but Î£, 90Â°, and â€” are corrupt"

    repaired = pipeline.normalize_generated_text(corrupted)

    assert repaired == "θ is already correct, but Σ, 90°, and — are corrupt"


def test_strip_code_fence_extracts_python_block_after_prose():
    response = "Here is the code:\n```python\nfrom manim import *\n\nclass X(Scene):\n    pass\n```\nDone."

    stripped = pipeline.strip_code_fence(response)

    assert stripped.startswith("from manim import *")
    assert "Here is the code" not in stripped


def test_generated_python_rejects_malformed_math_caption_and_debug_button_set():
    storyboard = '[0-4] ON SCREEN: Evaluate the integral | VO: "Compute it."'
    malformed = '''
from manim import *
class IntegralScene(Scene):
    def construct(self):
        self.add(Text("Displaystyle I Big x cos x"))
'''
    try:
        pipeline.validate_generated_python(malformed, storyboard)
    except SyntaxError as exc:
        assert "malformed math caption" in str(exc)
    else:
        raise AssertionError("Expected malformed math caption to be rejected")

    debug_buttons = '''
from manim import *
class IntegralScene(Scene):
    def construct(self):
        self.add(Text("Start"), Text("Change"), Text("Result"))
'''
    try:
        pipeline.validate_generated_python(debug_buttons, storyboard)
    except SyntaxError as exc:
        assert "debug-button" in str(exc)
    else:
        raise AssertionError("Expected debug-button labels to be rejected")


def test_generated_python_rejects_unescaped_latex_commands_and_integral_letter_o():
    storyboard = '[0-4] ON SCREEN: Evaluate the integral | VO: "Compute it."'
    unescaped = '''
from manim import *
class IntegralScene(Scene):
    def construct(self):
        self.add(MathTex("I=int_0^pi x sin x"))
'''
    try:
        pipeline.validate_generated_python(unescaped, storyboard)
    except SyntaxError as exc:
        assert "unescaped LaTeX command" in str(exc)
    else:
        raise AssertionError("Expected bare integral commands to be rejected")

    lower_bound_typo = '''
from manim import *
class IntegralScene(Scene):
    def construct(self):
        self.add(MathTex(r"\\int_{o}^{\\pi}x\\sin x"))
'''
    try:
        pipeline.validate_generated_python(lower_bound_typo, storyboard)
    except SyntaxError as exc:
        assert "letter o as an integral bound" in str(exc)
    else:
        raise AssertionError("Expected an integral lower-bound letter o to be rejected")


def test_storyboard_draft_unicode_stores_via_direct_db_query_for_each_provider(monkeypatch):
    init_db()
    symbols_storyboard = '# Approach: symbols\n[0-4] ON SCREEN: Greek symbols θ, Σ, 90°, and — | VO: "θ plus Σ at 90° — done."'

    for provider_name in ("anthropic", "openai"):
        db = SessionLocal()
        try:
            job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = job.id

            provider = FakeProvider(name=provider_name, model=f"{provider_name}-model", responses=[symbols_storyboard])
            draft = pipeline.generate_storyboard_draft("Greek symbols", 30, "students", db=db, job_id=job_id, provider=provider)
            job.generated_storyboard = draft["storyboard"]
            db.commit()

            row = db.execute(
                text("SELECT generated_storyboard, cost_breakdown FROM jobs WHERE id = :job_id"),
                {"job_id": job_id},
            ).one()
            assert row.generated_storyboard == symbols_storyboard
            assert db.get(Job, job_id).cost_breakdown[provider_name]["calls"] == 2
        finally:
            db.close()


def test_paginate_dense_storyboard_beats_splits_crowded_content():
    storyboard = (
        '[0-8] ON SCREEN: Show three labeled curves, tangent arrow, slope label, intercept label, '
        'and equation all simultaneously | VO: "Compare every object at once."\n'
        '[8-12] ON SCREEN: Conclude | VO: "Done."'
    )

    paginated = pipeline.paginate_dense_storyboard_beats(storyboard)
    beats = pipeline.parse_storyboard(paginated)

    assert len(beats) == 3
    assert beats[0].end_sec == beats[1].start_sec
    assert "Establish the first relationship" in beats[0].on_screen_text
    assert "Add the remaining relationship" in beats[1].on_screen_text


def test_topic_pipeline_stores_unicode_storyboard_character_for_character(monkeypatch, tmp_path: Path):
    init_db()
    db = SessionLocal()
    try:
        job = Job(scene_name="GreekScene")
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    storyboard = '# Approach: symbolic derivation\n[0-4] ON SCREEN: π, Σ, x², and a — symbol | VO: "π plus Σ gives x²."'

    monkeypatch.setattr(pipeline, "WORK_ROOT", tmp_path / "runs")
    monkeypatch.setattr(
        pipeline,
        "generate_storyboard_draft",
        lambda topic, duration_seconds, audience, db=None, job_id=None: {
            "storyboard": storyboard,
            "estimated_cost_usd": 0.0,
            "cost_breakdown": pipeline.empty_cost_breakdown(),
        },
    )
    monkeypatch.setattr(pipeline, "run_pipeline_for_job", lambda *args, **kwargs: None)

    pipeline.run_topic_pipeline_for_job(job_id, "Greek symbols", 30, "students", "GreekScene")

    db = SessionLocal()
    try:
        row = db.execute(text("SELECT generated_storyboard, storyboard FROM jobs WHERE id = :job_id"), {"job_id": job_id}).one()
        assert row.generated_storyboard == storyboard
        assert row.storyboard == storyboard
    finally:
        db.close()

    audit_text = (tmp_path / "runs" / job_id / "generated_storyboard.txt").read_text(encoding="utf-8")
    assert audit_text == storyboard


def test_codegen_prompt_restricts_manim_color_constants():
    provider = FakeProvider()

    beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

    pipeline.generate_manim_code(provider, '[0-1] ON SCREEN: Show x | VO: "x"', "TestScene", timed)

    system_prompt = provider.calls[0]["system"]
    assert "Only use these Manim CE color constants" in system_prompt
    assert "YELLOW_GREEN" in system_prompt
    assert "GREEN_YELLOW" in system_prompt
    assert "interpolate_color()" in system_prompt
    assert "minimum buffer of 0.3" in system_prompt
    assert "decorative arrows and annotations" in system_prompt
    assert "def avoid_overlap(mobj, others, min_gap=0.3)" in system_prompt
    assert "diagram.scale_to_fit_height(config.frame_height * 0.55)" in system_prompt
    assert "diagram.move_to(ORIGIN)" in system_prompt
    assert "Every beat's main diagram VGroup MUST" in system_prompt
    assert "AXES AND FORCE VECTOR SEPARATION" in system_prompt
    assert "0.5-0.8 units below-left" in system_prompt
    assert "ALL arrow labels" in system_prompt
    assert "multi-step algebraic derivations" in system_prompt
    assert "SurroundingRectangle must be created only around the mobject that exists on screen" in system_prompt
    assert "Do not animate Transform(result.copy(), next_result)" in system_prompt
    assert "LATEX TEXT CONSTRAINT" in system_prompt
    assert "one '$', backslash, or '^('" in system_prompt
    assert "0.05 seconds per source character" in system_prompt
    assert "CLARITY-FIRST MOTION" in system_prompt
    assert "GENUINE VISUALIZATION" in system_prompt
    assert "Hold the completed primary visual for at least 0.65 seconds" in system_prompt
    assert "SCENE CONTINUITY CONSTRAINT" in system_prompt
    assert "numeral 0, never letter o" in system_prompt
    assert "SAFE SCALE CONSTRAINT" in system_prompt
    assert "VISUAL CONSTRUCTION CONSTRAINT" in system_prompt
    assert "operational specification, never a caption" in system_prompt
    assert "six words or fewer" in system_prompt
    assert "axes, curves, graph regions" in system_prompt
    assert "Circle pulley" in system_prompt
    assert "CONTINUOUS CREATION CONSTRAINT" in system_prompt
    assert "CONSISTENT FORMULA REVEAL" in system_prompt
    assert "CURVE LABEL COLOR CONSTRAINT" in system_prompt
    assert "GRAPH TITLE AXIS CLEARANCE" in system_prompt
    assert "title.next_to(axes, UP, buff=0.4)" in system_prompt
    assert "title.get_bottom()[1] > axes.x_axis.get_center()[1] + 0.3" in system_prompt
    assert "SUMMARY REVEAL CONSTRAINT" in system_prompt
    assert "MOLECULAR GEOMETRY CONSTRAINT" in system_prompt
    assert "filled Polygon wedge" in system_prompt
    assert "DashedLine" in system_prompt
    assert "Draw lone pairs as a distinct pair" in system_prompt
    assert "VIDEO-LEVEL SEMANTIC COLOR PALETTE" in system_prompt
    assert "PRIMARY_COLOR = BLUE_C" in system_prompt
    assert "BOND_COLOR = RELATION_COLOR" in system_prompt
    assert "CROSS-BEAT COLOR CONSISTENCY" in system_prompt
    assert "hard constraints, not suggestions" in system_prompt
    assert "STANDARD TERMINOLOGY CONSTRAINT" in system_prompt
    assert "trigonal pyramidal" in system_prompt


def test_retry_feedback_includes_previous_code_for_patch_continuity():
    provider = FakeProvider()
    beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]
    previous_code = (
        "from manim import *\n\n"
        "PRIMARY_COLOR = GREEN_C\n"
        "FORCE_COLOR = PRIMARY_COLOR\n\n"
        "class TestScene(Scene):\n"
        "    def construct(self):\n"
        "        old = Text('old')\n"
    )

    pipeline.generate_manim_code(
        provider,
        '[0-1] ON SCREEN: Show x | VO: "x"',
        "TestScene",
        timed,
        error_feedback="Patch only Beat 1.",
        previous_code=previous_code,
    )

    user_message = provider.calls[0]["user_message"]
    system_prompt = provider.calls[0]["system"]
    assert previous_code in user_message
    assert "Patch only Beat 1." in user_message
    assert "ESTABLISHED COLOR ASSIGNMENTS FROM THE PREVIOUS SCENE" in system_prompt
    assert "PRIMARY_COLOR = GREEN_C" in system_prompt
    assert "FORCE_COLOR = PRIMARY_COLOR" in system_prompt


def test_generate_valid_manim_code_retries_invalid_python_without_render_budget(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
        db.add(job)
        db.commit()
        db.refresh(job)
        provider = FakeProvider(
            name="openai",
            model="gpt-5.5",
            responses=[
                "Looking at the failure: use code only next.",
                VALID_SCENE_CODE,
            ],
        )
        beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
        timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

        code = pipeline.generate_valid_manim_code(
            db=db,
            job_id=job.id,
            provider=provider,
            storyboard='[0-1] ON SCREEN: Show x | VO: "x"',
            scene_name="TestScene",
            timed_beats=timed,
            orientation="portrait",
            attempt_start_time=pipeline.time.monotonic(),
            render_attempt=1,
            render_error_feedback=None,
            previous_render_code=None,
        )

        assert "class TestScene" in code
        assert len(provider.calls) == 2
        assert "Respond with ONLY the code" in provider.calls[1]["user_message"]
        db.refresh(job)
        assert job.attempt_number == 1
        assert job.cost_breakdown["openai"]["calls"] == 2
    finally:
        db.close()


def test_generate_valid_manim_code_retries_validation_error_with_specific_feedback(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
        db.add(job)
        db.commit()
        db.refresh(job)
        missing_composition = VALID_SCENE_CODE.replace(
            "diagram.scale_to_fit_height(config.frame_height * 0.55)\n        diagram.move_to(ORIGIN)\n",
            "",
        )
        provider = FakeProvider(
            name="anthropic",
            model="claude-haiku-4-5",
            responses=[missing_composition, VALID_SCENE_CODE],
        )
        beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
        timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

        code = pipeline.generate_valid_manim_code(
            db=db,
            job_id=job.id,
            provider=provider,
            storyboard='[0-1] ON SCREEN: Show x | VO: "x"',
            scene_name="TestScene",
            timed_beats=timed,
            orientation="portrait",
            attempt_start_time=pipeline.time.monotonic(),
            render_attempt=1,
            render_error_feedback=None,
            previous_render_code=None,
        )

        assert "class TestScene" in code
        assert len(provider.calls) == 2
        retry_message = provider.calls[1]["user_message"]
        assert "parser/validator error" in retry_message
        assert "return the full corrected python file" in retry_message.lower()
    finally:
        db.close()


def test_generate_valid_manim_code_retries_truncated_provider_response_without_render_budget():
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
        db.add(job)
        db.commit()
        db.refresh(job)

        class TruncatingProvider(FakeProvider):
            def generate(
                self,
                system: str,
                user_message: str,
                max_tokens: int,
                model: str | None = None,
            ) -> LLMResponse:
                self.calls.append(
                    {"system": system, "user_message": user_message, "max_tokens": max_tokens, "model": model}
                )
                if len(self.calls) == 1:
                    return LLMResponse(
                        text='from manim import *\nvalue = MathTex(r"T = \\frac{2m_1m_2g}{(")',
                        truncated=True,
                        input_tokens=1000,
                        output_tokens=12000,
                    )
                return LLMResponse(text=VALID_SCENE_CODE, truncated=False, input_tokens=1000, output_tokens=200)

        provider = TruncatingProvider(name="anthropic", model="claude-haiku-4-5")
        beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
        timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

        code = pipeline.generate_valid_manim_code(
            db=db,
            job_id=job.id,
            provider=provider,
            storyboard='[0-1] ON SCREEN: Show x | VO: "x"',
            scene_name="TestScene",
            timed_beats=timed,
            orientation="portrait",
            attempt_start_time=pipeline.time.monotonic(),
            render_attempt=1,
            render_error_feedback=None,
            previous_render_code=None,
        )

        assert code.strip() == VALID_SCENE_CODE.strip()
        assert len(provider.calls) == 2
        assert "truncated mid-string" in provider.calls[1]["user_message"]
        db.refresh(job)
        assert job.attempt_number == 1
        assert job.cost_breakdown["anthropic"]["calls"] == 2
    finally:
        db.close()


def test_generate_valid_manim_code_retries_rate_limited_call_without_consuming_parse_budget(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
        db.add(job)
        db.commit()
        db.refresh(job)
        calls = {"count": 0}
        sleep_calls: list[float] = []

        class RateLimitedProvider(FakeProvider):
            def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
                calls["count"] += 1
                if calls["count"] < 3:
                    raise RateLimitError("7")
                return LLMResponse(text=VALID_SCENE_CODE, truncated=False, input_tokens=10, output_tokens=10)

        monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: sleep_calls.append(seconds))
        provider = RateLimitedProvider(name="openai", model="gpt-5.5")
        beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
        timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

        code = pipeline.generate_valid_manim_code(
            db=db,
            job_id=job.id,
            provider=provider,
            storyboard='[0-1] ON SCREEN: Show x | VO: "x"',
            scene_name="TestScene",
            timed_beats=timed,
            orientation="portrait",
            attempt_start_time=pipeline.time.monotonic(),
            render_attempt=1,
            render_error_feedback=None,
            previous_render_code=None,
        )

        assert "class TestScene" in code
        assert calls["count"] == 3
        assert sleep_calls == [7.0, 7.0]
        db.refresh(job)
        assert job.attempt_number == 1
    finally:
        db.close()


def test_generate_valid_manim_code_raises_after_rate_limit_backoff_budget(monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0)
        db.add(job)
        db.commit()
        db.refresh(job)

        class AlwaysRateLimitedProvider(FakeProvider):
            def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
                raise RateLimitError()

        monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
        provider = AlwaysRateLimitedProvider(name="openai", model="gpt-5.5")
        beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
        timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

        try:
            pipeline.generate_valid_manim_code(
                db=db,
                job_id=job.id,
                provider=provider,
                storyboard='[0-1] ON SCREEN: Show x | VO: "x"',
                scene_name="TestScene",
                timed_beats=timed,
                orientation="portrait",
                attempt_start_time=pipeline.time.monotonic(),
                render_attempt=1,
                render_error_feedback=None,
                previous_render_code=None,
            )
        except pipeline.RateLimitExhausted as exc:
            assert "rate limit" in str(exc).lower()
        else:
            raise AssertionError("Expected RateLimitExhausted")
    finally:
        db.close()


def test_validate_generated_python_rejects_invented_compound_color_names():
    code = VALID_SCENE_CODE.replace("Text(\"x\")", "Dot(color=GREEN_YELLOW)")

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "GREEN_YELLOW" in str(exc)
    else:
        raise AssertionError("Expected invented color name to fail validation")


def test_validate_generated_python_rejects_unsupported_font_family_kwarg():
    code = VALID_SCENE_CODE.replace(
        "Text(\"x\")",
        "MathTex(r\"B = \\\\frac{\\\\mu_0 I}{2R}\", font_family=\"Arial\")",
    )

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "font_family" in str(exc)
    else:
        raise AssertionError("Expected unsupported font_family kwarg to fail validation")


def test_validate_generated_python_rejects_latex_passed_to_text():
    code = VALID_SCENE_CODE.replace('Text("x")', 'Text(r"\\frac{x}{2}")')

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "Text() with LaTeX syntax" in str(exc)
        assert "MathTex" in str(exc)
    else:
        raise AssertionError("Expected LaTeX passed to Text to fail validation")


def test_validate_generated_python_rejects_every_strict_text_math_marker():
    for value in ("$x^2$", r"\Sigma", "f^(n)(0)"):
        code = VALID_SCENE_CODE.replace('Text("x")', f"Text({value!r})")
        try:
            pipeline.validate_generated_python(code)
        except SyntaxError as exc:
            assert "Text() with LaTeX syntax" in str(exc)
        else:
            raise AssertionError(f"Expected Text({value!r}) to fail strict math validation")


def test_validate_generated_python_rejects_duplicate_rendered_connector_and_letter_o():
    duplicate_code = VALID_SCENE_CODE.replace('Text("x")', 'Text("then then")')
    zero_typo_code = VALID_SCENE_CODE.replace('Text("x")', 'MathTex(r"f^{(n)}(o)")')

    try:
        pipeline.validate_generated_python(duplicate_code)
    except SyntaxError as exc:
        assert "duplicate connector" in str(exc)
    else:
        raise AssertionError("Expected duplicate rendered connector to fail validation")

    try:
        pipeline.validate_generated_python(zero_typo_code)
    except SyntaxError as exc:
        assert "numeral 0" in str(exc)
    else:
        raise AssertionError("Expected Maclaurin letter o to fail validation")


def test_validate_generated_python_rejects_incomplete_latex_delimiters():
    code = VALID_SCENE_CODE.replace(
        'Text("x")',
        'MathTex(r"T = \\frac{2m_1m_2g}{(")',
    )

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "truncated mid-string" in str(exc)
        assert "incomplete LaTeX" in str(exc)
        assert "T =" in str(exc)
    else:
        raise AssertionError("Expected incomplete LaTeX delimiters to fail validation")


def test_validate_generated_python_accepts_complete_tension_equation():
    code = VALID_SCENE_CODE.replace(
        'Text("x")',
        'MathTex(r"T = \\frac{2m_1m_2g}{m_1+m_2}")',
    )

    pipeline.validate_generated_python(code)


def test_validate_generated_python_enforces_text_write_runtime():
    too_fast = VALID_SCENE_CODE.replace("FadeIn(diagram)", "Write(diagram)")

    try:
        pipeline.validate_generated_python(too_fast)
    except SyntaxError as exc:
        assert "0.05s per character" in str(exc)
        assert "1.5s minimum" in str(exc)
    else:
        raise AssertionError("Expected a one-second Write animation to fail validation")

    long_enough = too_fast.replace("beat1_speed = 1.0", "beat1_speed = 1.5")
    pipeline.validate_generated_python(long_enough)


def test_validate_generated_python_rejects_wait_after_nonfinal_all_fadeout():
    code = """from manim import *

def avoid_overlap(mobj, others, min_gap=0.3):
    return mobj

class ContinuityScene(Scene):
    def construct(self):
        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 1.0
        beat1_speed = 1.5
        # --- Beat 1 ---
        diagram1 = VGroup(Text("First"))
        diagram1.scale_to_fit_height(config.frame_height * 0.55)
        diagram1.move_to(ORIGIN)
        self.play(FadeIn(diagram1), run_time=beat1_speed)
        self.play(FadeOut(diagram1), run_time=0.5)
        self.wait(0.5)
        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 1.0
        beat2_speed = 1.5
        # --- Beat 2 ---
        diagram2 = VGroup(Text("Second"))
        diagram2.scale_to_fit_height(config.frame_height * 0.55)
        diagram2.move_to(ORIGIN)
        self.play(FadeIn(diagram2), run_time=beat2_speed)
        self.play(FadeOut(diagram2), run_time=0.5)
"""


    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "Beat 1 removes all visible content" in str(exc)
        assert "leaving a blank frame" in str(exc)
    else:
        raise AssertionError("Expected a non-final blank-frame transition to fail validation")


def test_narration_timeline_rejects_short_render():
    with pytest.raises(RuntimeError, match="shorter than the narration timeline"):
        pipeline.validate_render_duration_for_narration(9.0, 10.0)


def test_narration_timeline_allows_render_with_hold_time():
    pipeline.validate_render_duration_for_narration(10.0, 9.0)


def test_pendulum_fact_check_rejects_restoring_force_toward_pivot():
    storyboard = (
        '[0-4] ON SCREEN: Pendulum bob and force vectors | '
        'VO: "The restoring force points toward the pivot."\n'
    )
    with pytest.raises(ValueError, match="tension points toward the pivot"):
        pipeline.validate_storyboard_or_raise(storyboard)


def test_pendulum_fact_check_rejects_towards_variant():
    storyboard = (
        '[0-4] ON SCREEN: Pendulum restoring force | '
        'VO: "The restoring force pulls the bob back towards the pivot."\n'
    )
    with pytest.raises(ValueError, match="tension points toward the pivot"):
        pipeline.validate_storyboard_or_raise(storyboard)


def test_pendulum_fact_check_requires_equilibrium_direction():
    storyboard = (
        '[0-4] ON SCREEN: Pendulum bob and restoring force | '
        'VO: "The restoring force brings the bob back."\n'
    )
    with pytest.raises(ValueError, match="equilibrium position"):
        pipeline.validate_storyboard_or_raise(storyboard)


def test_pendulum_fact_check_accepts_equilibrium_and_pivot_claims_separately():
    storyboard = (
        '[0-4] ON SCREEN: Pendulum tension and restoring force | '
        'VO: "Tension points toward the pivot, while the restoring force points toward equilibrium at theta=0."\n'
    )
    beats = pipeline.validate_storyboard_or_raise(storyboard)
    assert len(beats) == 1


def test_rendered_beat_windows_scale_to_actual_video_duration():
    beats = [
        pipeline.TimedBeat(SimpleNamespace(index=1), None, 4.0, 0.0),
        pipeline.TimedBeat(SimpleNamespace(index=2), None, 6.0, 0.0),
    ]
    windows = pipeline.timed_beat_windows(beats, rendered_duration=12.0)
    assert windows == [
        {"beat_number": 1, "start": 0.0, "end": 4.8},
        {"beat_number": 2, "start": 4.8, "end": 12.0},
    ]


def test_narration_pacing_rejects_fast_clip():
    with pytest.raises(RuntimeError, match="Narration is too fast"):
        pipeline.validate_narration_pacing("one two three four five six", 1.0)


def test_narration_pacing_accepts_teaching_rate():
    wpm = pipeline.validate_narration_pacing("one two three four five six", 3.0)
    assert wpm == pytest.approx(120.0)


def test_validate_generated_python_rejects_direct_text_mount():
    code = VALID_SCENE_CODE.replace(
        "self.play(FadeIn(diagram), run_time=beat1_speed)",
        'self.add(Text("sudden caption"))',
    )
    with pytest.raises(SyntaxError, match="mounts rendered text with self.add"):
        pipeline.validate_generated_python(code)


def test_validate_generated_python_rejects_operational_spec_copied_as_caption():
    on_screen = "Compare the graph of sin x with its linear and cubic approximations near the origin"
    storyboard = f'[0-4] ON SCREEN: {on_screen} | VO: "Compare the curves."'
    code = VALID_SCENE_CODE.replace(
        'label = Text("x")',
        f"label = Text({on_screen!r})",
    )

    try:
        pipeline.validate_generated_python(code, storyboard)
    except SyntaxError as exc:
        assert "copies its operational ON SCREEN spec" in str(exc)
        assert "word overlap" in str(exc)
    else:
        raise AssertionError("Expected copied operational caption to fail validation")

    math_caption = code.replace(f"Text({on_screen!r})", f"MathTex({on_screen!r})")
    try:
        pipeline.validate_generated_python(math_caption, storyboard)
    except SyntaxError as exc:
        assert "copies its operational ON SCREEN spec" in str(exc)
    else:
        raise AssertionError("Expected copied operational MathTex caption to fail validation")


def test_validate_generated_python_allows_requested_equation_as_mathtex_object():
    equation = r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^n"
    storyboard = f'[0-4] ON SCREEN: Build Taylor formula `{equation}` | VO: "Build the series."'
    code = VALID_SCENE_CODE.replace('Text("x")', f"MathTex({equation!r})")

    pipeline.validate_generated_python(code, storyboard)


def test_validate_generated_python_requires_overlap_check_for_every_named_text_mobject():
    storyboard = '[0-4] ON SCREEN: Compare the graph with two approximations | VO: "Compare the curves."'
    unchecked = VALID_SCENE_CODE.replace('        avoid_overlap(label, existing_mobjects)\n', '')

    try:
        pipeline.validate_generated_python(unchecked, storyboard)
    except SyntaxError as exc:
        assert "without calling avoid_overlap(label" in str(exc)
    else:
        raise AssertionError("Expected missing text collision check to fail validation")

    pipeline.validate_generated_python(VALID_SCENE_CODE, storyboard)

    inline = VALID_SCENE_CODE.replace(
        'label = Text("x")\n        avoid_overlap(label, existing_mobjects)\n        diagram = VGroup(label)',
        'diagram = VGroup(Text("x"))',
    )
    try:
        pipeline.validate_generated_python(inline, storyboard)
    except SyntaxError as exc:
        assert "creates Text() inline" in str(exc)
    else:
        raise AssertionError("Expected inline text construction to fail storyboard-aware validation")


def test_validate_generated_python_rejects_duplicate_substantial_content_in_one_beat():
    storyboard = '[0-4] ON SCREEN: Present one Taylor approximation formula | VO: "Show the formula."'
    code = VALID_SCENE_CODE.replace(
        'label = Text("x")\n        avoid_overlap(label, existing_mobjects)\n        diagram = VGroup(label)',
        'label = Text("Taylor approximation formula")\n'
        '        avoid_overlap(label, existing_mobjects)\n'
        '        existing_mobjects.append(label)\n'
        '        duplicate = Text("Taylor approximation formula")\n'
        '        avoid_overlap(duplicate, existing_mobjects)\n'
        '        diagram = VGroup(label, duplicate)',
    )

    try:
        pipeline.validate_generated_python(code, storyboard)
    except SyntaxError as exc:
        assert "recreates the same substantial on-screen content" in str(exc)
    else:
        raise AssertionError("Expected duplicate substantial content to fail validation")


def test_validate_generated_python_rejects_revealing_same_mobject_twice():
    code = VALID_SCENE_CODE.replace(
        "self.play(FadeIn(diagram), run_time=beat1_speed)",
        "self.play(FadeIn(diagram), run_time=beat1_speed)\n"
        "        self.play(Write(diagram), run_time=1.5)",
    )

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "reveals mobject 'diagram' more than once" in str(exc)
        assert "continuous creation animation" in str(exc)
    else:
        raise AssertionError("Expected repeated reveal of one mobject to fail validation")


def test_validate_generated_python_rejects_raw_animated_scale():
    code = VALID_SCENE_CODE.replace(
        "self.play(FadeIn(diagram), run_time=beat1_speed)",
        "self.play(diagram.animate.scale(1.4), run_time=beat1_speed)",
    )

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "safe_scale" in str(exc)
    else:
        raise AssertionError("Expected raw animated scale to fail validation")


def test_validate_generated_python_rejects_rendered_stage_direction():
    code = VALID_SCENE_CODE.replace('Text("x")', 'Text("Draw a pulley with m1 and m2")')

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "imperative construction instruction" in str(exc)
    else:
        raise AssertionError("Expected rendered construction instruction to fail validation")


def test_validate_generated_python_requires_composition_contract():
    code = "from manim import *\n\nclass MissingHelper(Scene):\n    def construct(self):\n        self.wait(1)\n"

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "avoid_overlap" in str(exc)
    else:
        raise AssertionError("Expected missing helper SyntaxError")


def test_validate_generated_python_rejects_transforming_copied_equation():
    code = VALID_SCENE_CODE.replace(
        "self.play(FadeIn(diagram), run_time=beat1_speed)",
        "eq1 = MathTex('x')\n        eq2 = MathTex('y')\n        self.play(Transform(eq1.copy(), eq2), run_time=beat1_speed)",
    )

    try:
        pipeline.validate_generated_python(code)
    except SyntaxError as exc:
        assert "copied equation" in str(exc)
    else:
        raise AssertionError("Expected copied equation transform SyntaxError")


def test_replace_beat_block_splices_only_target_beat():
    code = """from manim import *

class TestScene(Scene):
    def construct(self):
        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 1.0
        beat1_speed = 1.0
        # --- Beat 1 ---
        self.wait(1)
        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 1.0
        beat2_speed = 1.0
        # --- Beat 2 ---
        self.wait(2)
"""

    replacement = """# --- Beat 2 params ---
beat2_scale = 1.5
beat2_gap = 0.8
beat2_speed = 0.7
# --- Beat 2 ---
self.wait(3)
"""
    patched = pipeline.replace_beat_block(code, 2, replacement)

    assert "beat1_scale = 1.0" in patched
    assert "beat2_scale = 1.5" in patched
    assert "self.wait(3)" in patched
    assert "self.wait(2)" not in patched


def test_beat_number_from_traceback_uses_code_line_numbers():
    code = """from manim import *

class TestScene(Scene):
    def construct(self):
        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 1.0
        beat1_speed = 1.0
        # --- Beat 1 ---
        self.wait(1)
        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 1.0
        beat2_speed = 1.0
        # --- Beat 2 ---
        self.wait(2)
"""
    traceback = 'File "scene.py", line 13, in construct\nTypeError: boom'

    assert pipeline.beat_number_from_traceback(code, traceback) == 2


def test_generate_manim_code_normalizes_storyboard_before_prompt():
    provider = FakeProvider()
    corrupted_storyboard = '[0-3] ON SCREEN: MathTex r"Î£ F = m g at Î¸ = 30Â° â€” clean" | VO: "Show it."'
    beat = pipeline.StoryboardBeat(1, 0, 3, "Show equation", "Show it.")
    timed = [pipeline.TimedBeat(beat, None, 3.0, 0.0)]

    pipeline.generate_manim_code(provider, corrupted_storyboard, "UnicodePromptScene", timed)

    user_message = provider.calls[0]["user_message"]
    assert "Σ F = m g at θ = 30° — clean" in user_message
    assert "Î£" not in user_message
    assert "Â°" not in user_message
    assert "â€”" not in user_message


def test_generate_manim_code_uses_fast_model_on_first_attempt_and_primary_after(monkeypatch):
    provider = FakeProvider(name="openai", model="gpt-5.5", responses=[VALID_SCENE_CODE, VALID_SCENE_CODE])
    provider.fast_model = "gpt-5-mini"
    beat = pipeline.StoryboardBeat(1, 0, 1, "Show x", "x")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]

    pipeline.generate_manim_code(provider, '[0-1] ON SCREEN: Show x | VO: "x"', "TestScene", timed, attempt_number=1)
    pipeline.generate_manim_code(provider, '[0-1] ON SCREEN: Show x | VO: "x"', "TestScene", timed, attempt_number=2)

    assert provider.calls[0]["model"] == "gpt-5-mini"
    assert provider.calls[1]["model"] == "gpt-5.5"


def test_vision_quality_check_defaults_to_deterministic_sample(monkeypatch):
    monkeypatch.setattr(pipeline, "VISION_QUALITY_CHECK_MODE", "sample")
    monkeypatch.setattr(pipeline, "VISION_QUALITY_SAMPLE_RATE", 0.0)
    assert pipeline.should_run_vision_quality_check("job-1") is False

    monkeypatch.setattr(pipeline, "VISION_QUALITY_SAMPLE_RATE", 1.0)
    assert pipeline.should_run_vision_quality_check("job-1") is True

    monkeypatch.setattr(pipeline, "VISION_QUALITY_CHECK_MODE", "manual")
    assert pipeline.should_run_vision_quality_check("job-1") is False
    assert pipeline.should_run_vision_quality_check("job-1", manual_requested=True) is True


def test_reference_scene_selection_uses_storyboard_keywords():
    force_refs = pipeline.selected_reference_scenes(
        '[0-4] ON SCREEN: Draw a frictionless incline force diagram with normal and derive the equation | VO: "Forces."'
    )
    curve_refs = pipeline.selected_reference_scenes(
        '[0-4] ON SCREEN: Plot the sine curve on axes and mark the tangent | VO: "Curve."'
    )

    assert "ForceTriangleIncline" in force_refs
    assert "AlgebraStepTransform" in force_refs
    assert "ParabolaPlot" in curve_refs
    assert "ForceTriangleIncline" not in curve_refs


def test_frame_quality_score_records_cost_and_job_scores(tmp_path: Path):
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0, quality_scores=[])
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id

        frame = tmp_path / "frame.png"
        frame.write_bytes(b"fake image")
        beat = pipeline.StoryboardBeat(3, 8, 12, "Two labels and an arrow appear", "Look here.")

        score = pipeline.assess_frame_quality(FakeProvider(name="openai", model="gpt-5.5"), frame, beat, 9.0, db, job_id)
        db.refresh(job)

        assert score.beat_index == 3
        assert score.accuracy == 5
        assert score.element_layout == 5
        assert job.quality_scores[0]["accuracy"] == 5
        assert job.cost_breakdown["openai"]["calls"] == 1
        assert job.cost_breakdown["openai"]["input_tokens"] == 500
    finally:
        db.close()


def test_quality_feedback_mentions_failed_dimensions(tmp_path: Path):
    finding = pipeline.FrameQualityScore(
        timestamp=12.0,
        frame_path=tmp_path / "frame.png",
        beat_index=4,
        accuracy=2,
        depth=5,
        logical_flow=5,
        visual_relevance=5,
        element_layout=3,
        summary="Equation mismatch and cramped labels.",
    )

    feedback = pipeline.build_quality_feedback(finding)

    assert "Beat 4" in feedback
    assert "accuracy=2/5" in feedback
    assert "element_layout=3/5" in feedback


def test_beat_params_parse_and_patch_numeric_assignments():
    code = """
from manim import *

def avoid_overlap(mobj, others, min_gap=0.3):
    return mobj

class TestScene(Scene):
    def construct(self):
        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 2.3
        beat2_speed = 1.0
        # --- Beat 2 ---
        title = Text("x").scale(beat2_scale)
        diagram = VGroup(title)
        diagram.scale_to_fit_height(config.frame_height * 0.55)
        diagram.move_to(ORIGIN)
        self.play(FadeIn(diagram), run_time=beat2_speed)
"""

    params = pipeline.beat_params_from_code(code, 2)
    patched = pipeline.patch_beat_params_in_code(code, 2, {"scale": 1.25, "gap": 1.8, "speed": 0.7})

    assert params == {"scale": 1.0, "gap": 2.3, "speed": 1.0}
    assert "beat2_scale = 1.25" in patched
    assert "beat2_gap = 1.8" in patched
    assert "beat2_speed = 0.7" in patched
    assert "Text(\"x\")" in patched


def test_patch_beat_params_rejects_missing_param():
    code = "beat1_scale = 1.0\n"

    try:
        pipeline.patch_beat_params_in_code(code, 1, {"speed": 1.2})
    except ValueError as exc:
        assert "beat1_speed" in str(exc)
    else:
        raise AssertionError("Expected missing param to raise")


def test_render_only_cost_bucket_updates_job():
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0, progress_message="Rendering")
        db.add(job)
        db.commit()
        db.refresh(job)

        pipeline.record_render_only_edit(db, job.id)
        db.refresh(job)

        assert job.cost_breakdown["render_only"]["calls"] == 1
        assert job.cost_breakdown["render_only"]["cost_usd"] == 0.0
        assert job.estimated_cost_usd == 0.0
    finally:
        db.close()


def test_cost_accounting_updates_job_progress():
    init_db()
    db = SessionLocal()
    try:
        job = Job(cost_breakdown=pipeline.empty_cost_breakdown(), estimated_cost_usd=0.0, progress_message="Generating")
        db.add(job)
        db.commit()
        db.refresh(job)

        pipeline.add_llm_cost(db, job.id, "anthropic", "claude-sonnet-4-6", input_tokens=1_000, output_tokens=100)
        pipeline.add_llm_cost(db, job.id, "openai", "gpt-5.5", input_tokens=1_000, output_tokens=100)
        pipeline.add_openai_tts_cost(db, job.id, "tts-1-hd", characters=500)
        db.refresh(job)

        assert job.estimated_cost_usd > 0
        assert job.cost_breakdown["anthropic"]["calls"] == 1
        assert job.cost_breakdown["anthropic"]["input_tokens"] == 1_000
        assert job.cost_breakdown["openai"]["calls"] == 1
        assert job.cost_breakdown["openai"]["model"] == "gpt-5.5"
        assert job.cost_breakdown["openai_tts"]["characters"] == 500
        assert "$" in job.progress_message
    finally:
        db.close()


def test_model_specific_cost_rates_are_used():
    assert pipeline.llm_token_rates("anthropic", "claude-haiku-4-5") == {"input": 1.0, "output": 5.0}
    assert pipeline.llm_token_rates("openai", "gpt-5.4-mini") == {"input": 0.75, "output": 4.5}
    assert pipeline.llm_token_rates("gemini", "gemini-2.5-flash-lite") == {"input": 0.1, "output": 0.4}
