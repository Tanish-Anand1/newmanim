from manim import Axes, ValueTracker

from app.craft_library import LiveHistogram
from app.craft_pipeline import generate_dice_rolls


def test_dice_rolls_are_deterministic_and_valid():
    first = generate_dice_rolls(seed="clt-test-job")
    second = generate_dice_rolls(seed="clt-test-job")
    assert first == second
    assert len(first) == 6
    assert all(1 <= value <= 6 for value in first)


def test_live_histogram_rebuilds_bars_from_tracker():
    axes = Axes(x_range=[0, 42, 6], y_range=[0, 8, 2], x_length=4, y_length=3)
    tracker = ValueTracker(0)
    histogram = LiveHistogram(axes, tracker)
    first_heights = [bar.height for bar in histogram._bars]
    tracker.set_value(3)
    histogram.update(0)
    final_heights = [bar.height for bar in histogram._bars]
    assert final_heights != first_heights
