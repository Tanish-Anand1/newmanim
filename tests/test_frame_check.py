from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import app.frame_check as frame_check
from app.frame_check import beat_quality_timestamps, extract_frames_at_timestamps, foreground_pixel_ratio


def test_beat_quality_samples_are_after_reveal_not_mid_animation():
    timestamps = beat_quality_timestamps(12.0, [(0.0, 6.0), (6.0, 12.0)], sample_count=8)

    assert timestamps == pytest.approx([4.8, 10.8])
    assert all(0.7 * end <= timestamp < end for timestamp, (_, end) in zip(timestamps, [(0, 6), (6, 12)]))


def test_beat_quality_sampling_is_bounded_for_many_beats():
    windows = [(index * 3.0, (index + 1) * 3.0) for index in range(10)]
    timestamps = beat_quality_timestamps(30.0, windows, sample_count=8)

    assert len(timestamps) == 8
    assert all(start < timestamp < end for timestamp, (start, end) in zip(timestamps, [windows[index] for index in [0, 1, 3, 4, 5, 6, 8, 9]]))


def test_foreground_pixel_ratio_distinguishes_empty_and_visible_frames(tmp_path: Path):
    blank = tmp_path / "blank.png"
    visible = tmp_path / "visible.png"
    Image.new("RGB", (160, 240), "black").save(blank)
    image = Image.new("RGB", (160, 240), "black")
    ImageDraw.Draw(image).rectangle((40, 80, 120, 160), fill="white")
    image.save(visible)

    assert foreground_pixel_ratio(blank) == 0.0
    assert foreground_pixel_ratio(visible) > 0.10


def test_detect_sparse_frames_requires_sustained_empty_samples(monkeypatch, tmp_path: Path):
    blank = tmp_path / "blank.png"
    visible = tmp_path / "visible.png"
    Image.new("RGB", (80, 120), "black").save(blank)
    image = Image.new("RGB", (80, 120), "black")
    ImageDraw.Draw(image).rectangle((20, 30, 60, 90), fill="white")
    image.save(visible)
    samples = [(1.0, blank), (2.0, visible), (3.0, blank), (4.0, blank)]
    monkeypatch.setattr(frame_check, "extract_sample_frames", lambda *_args, **_kwargs: samples)

    findings = frame_check.detect_sparse_frames(tmp_path / "video.mp4", tmp_path)

    assert len(findings) == 1
    assert findings[0].timestamp == 4.0
    assert findings[0].foreground_pixel_ratio == 0.0


def test_frame_extraction_uses_accurate_post_input_seek(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> None:
        calls.append(command)

    monkeypatch.setattr(frame_check.subprocess, "run", fake_run)

    frames = extract_frames_at_timestamps(tmp_path / "video.mp4", tmp_path / "frames", [4.8])

    assert frames == [(4.8, tmp_path / "frames" / "sample_01_4.80s.png")]
    command = calls[0]
    assert command.index("-i") < command.index("-ss")
    assert command[command.index("-ss") + 1] == "4.800"
