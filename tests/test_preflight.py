"""Unit tests for the automated pre-flight gate checks (app/preflight.py)."""

from pathlib import Path
import pytest
from app.preflight import (
    check_animation_timing,
    check_content_completeness,
    check_latex_leaks,
    PreflightResult,
)


# ---------------------------------------------------------------------------
# check_animation_timing
# ---------------------------------------------------------------------------

class TestCheckAnimationTiming:
    def test_passes_when_no_beats(self):
        result = check_animation_timing("# no beats", [])
        assert result.passed

    def test_passes_when_within_budget(self):
        code = "# Beat 1 - INTRODUCE_CONCEPT\n    self.play(Write(title), run_time=1.5)\n    self.wait(1.0)\n"
        beats = [{"index": 1, "target_duration_seconds": 8.0}]
        result = check_animation_timing(code, beats)
        assert result.passed

    def test_fails_when_over_budget(self):
        # 3 run_times summing to 12 seconds for a 5-second beat
        code = (
            "# Beat 1 - INTRODUCE_CONCEPT\n"
            "    self.play(Write(title), run_time=5.0)\n"
            "    self.play(FadeIn(mob), run_time=4.0)\n"
            "    self.play(Transform(a, b), run_time=3.0)\n"
        )
        beats = [{"index": 1, "target_duration_seconds": 5.0}]
        result = check_animation_timing(code, beats)
        assert not result.passed
        assert "Beat 1" in result.details

    def test_grace_period_applies(self):
        # Total run_time = 5.4s, budget = 5.0s → within 0.5s grace
        code = (
            "# Beat 1 - INTRODUCE_CONCEPT\n"
            "    self.play(Write(title), run_time=5.4)\n"
        )
        beats = [{"index": 1, "target_duration_seconds": 5.0}]
        result = check_animation_timing(code, beats)
        assert result.passed

    def test_ignores_unknown_beats(self):
        # Beat 99 not in timed_beats → no failure
        code = "# Beat 99 - NONE\n    self.wait(30.0)\n"
        beats = [{"index": 1, "target_duration_seconds": 4.0}]
        result = check_animation_timing(code, beats)
        assert result.passed


# ---------------------------------------------------------------------------
# check_latex_leaks
# ---------------------------------------------------------------------------

class TestCheckLatexLeaks:
    def test_passes_clean_code(self):
        code = 'MathTex(r"\\frac{1}{2}")\nText("Hello world")\n'
        result = check_latex_leaks(code)
        assert result.passed

    def test_fails_on_frac_in_text(self):
        code = 'Text("\\\\frac{a}{b}")\n'
        result = check_latex_leaks(code)
        assert not result.passed

    def test_fails_on_subscript_in_text(self):
        code = 'Text("x_{n}")\n'
        result = check_latex_leaks(code)
        assert not result.passed

    def test_fails_on_int_in_text(self):
        # r-string means the actual Python source has \int literally in it
        code = r'Text("\int_0^1 x dx")' + "\n"
        result = check_latex_leaks(code)
        assert not result.passed

    def test_passes_dollar_wrapped_mixed(self):
        # create_mixed_text expects plain strings with $ delimiters — not raw \frac
        code = 'create_mixed_text("Area = $\\\\frac{27}{4}$")\n'
        result = check_latex_leaks(code)
        assert result.passed


# ---------------------------------------------------------------------------
# check_content_completeness
# ---------------------------------------------------------------------------

class TestCheckContentCompleteness:
    def test_passes_when_storyboard_has_no_keywords(self):
        storyboard = "Introduce the concept of limits."
        code = 'introduce_concept(ctx, title="Limits")\n'
        result = check_content_completeness(storyboard, code)
        assert result.passed

    def test_passes_when_integral_present(self):
        storyboard = "Evaluate the integral to find the area."
        code = 'MathTex(r"\\int_{-1}^{2} f(x) dx")\n'
        result = check_content_completeness(storyboard, code)
        assert result.passed

    def test_fails_when_integral_missing(self):
        storyboard = "Set up the integral for the enclosed area."
        code = 'introduce_concept(ctx, title="Area setup")\n'
        result = check_content_completeness(storyboard, code)
        assert not result.passed
        assert "integral evaluation" in result.details

    def test_passes_when_circle_present(self):
        storyboard = "Construct the inscribed circle of radius r."
        code = 'Circle(radius=2.0, color=PURPLE)\n'
        result = check_content_completeness(storyboard, code)
        assert result.passed

    def test_fails_when_circle_missing(self):
        storyboard = "Find the inscribed circle and its radius."
        code = 'introduce_concept(ctx, title="Circle")\n'
        result = check_content_completeness(storyboard, code)
        assert not result.passed
        assert "circle construction" in result.details

    def test_multiple_missing_items_reported(self):
        storyboard = "Evaluate the integral. Construct the tangent line. Find the inscribed circle."
        code = 'introduce_concept(ctx, title="Intro")\n'
        result = check_content_completeness(storyboard, code)
        assert not result.passed
        # At least integral evaluation and circle should be flagged
        assert len(result.details) > 0


# ---------------------------------------------------------------------------
# PreflightResult str representation
# ---------------------------------------------------------------------------

class TestPreflightResult:
    def test_pass_str(self):
        r = PreflightResult(check_name="boundary_pixels", passed=True, summary="No overflow.")
        assert "[PASS]" in str(r)

    def test_fail_str(self):
        r = PreflightResult(check_name="latex_leaks", passed=False, summary="Found leak.")
        assert "[FAIL]" in str(r)
