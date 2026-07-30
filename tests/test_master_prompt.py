from app.vivacity_prompts import (
    build_manim_codegen_addon,
    build_script_generation_system_prompt,
    load_master_system_prompt,
)
from app.llm_provider import LLMResponse
import app.pipeline as pipeline


def test_canonical_master_prompt_contains_nonnegotiable_sections():
    prompt = load_master_system_prompt()
    for marker in ("Technical Foundation", "Teaching Sequence", "Portrait Safe Zone", "Multi-Scene Delivery", "Delivery Evidence"):
        assert marker in prompt
    assert "VivacityScene" in prompt
    assert "TransformMatchingTex" in prompt
    assert "acrossfade" in prompt


def test_storyboard_and_codegen_prompts_include_same_canonical_prompt():
    canonical = load_master_system_prompt()
    script = build_script_generation_system_prompt(
        topic="integration by parts",
        exam_context="JEE",
        flagged_as_weak_topic=False,
        unconfirmed_prerequisites=[],
    )
    codegen = build_manim_codegen_addon()
    assert canonical in script
    assert canonical in codegen


def test_master_prompt_cache_rereads_when_file_changes(tmp_path, monkeypatch):
    import app.vivacity_prompts as prompts

    path = tmp_path / "master.md"
    path.write_text("version one", encoding="utf-8")
    monkeypatch.setattr(prompts, "MASTER_PROMPT_PATH", path)
    prompts._master_prompt_cache = None
    assert prompts.load_master_system_prompt() == "version one"
    path.write_text("version two with a changed size", encoding="utf-8")
    assert prompts.load_master_system_prompt() == "version two with a changed size"


def test_real_storyboard_provider_call_receives_canonical_prompt():
    class CapturingProvider:
        name = "test"
        model = "test-model"

        def __init__(self):
            self.systems = []

        def generate(self, *, system, user_message, max_tokens, model=None):
            self.systems.append(system)
            return LLMResponse(
                text=pipeline.build_local_storyboard_draft("Taylor series", 30, "students"),
                truncated=False,
                input_tokens=10,
                output_tokens=20,
            )

    provider = CapturingProvider()
    pipeline.generate_storyboard_draft("Taylor series", 30, "students", provider=provider)
    assert provider.systems
    assert load_master_system_prompt() in provider.systems[0]


def test_real_manim_codegen_provider_call_receives_canonical_prompt():
    class CapturingProvider:
        name = "test"
        model = "test-model"

        def __init__(self):
            self.systems = []

        def generate(self, *, system, user_message, max_tokens, model=None):
            self.systems.append(system)
            return LLMResponse(
                text="from manim import *\nclass TestScene(Scene):\n    def construct(self):\n        pass",
                truncated=False,
                input_tokens=10,
                output_tokens=20,
            )

    beat = pipeline.StoryboardBeat(1, 0, 1, "Plot a curve", "Plot it.")
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]
    provider = CapturingProvider()
    pipeline.generate_manim_code(
        provider,
        '[0-1] ON SCREEN: Plot a curve | VO: "Plot it."',
        "TestScene",
        timed,
    )
    assert provider.systems
    assert load_master_system_prompt() in provider.systems[0]
