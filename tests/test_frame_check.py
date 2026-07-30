import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import app.frame_check as frame_check
from app.frame_check import (
    RenderVerification,
    beat_quality_timestamps,
    extract_frames_at_timestamps,
    foreground_pixel_ratio,
    detect_temporal_cuts,
    verify_delivery_file,
)


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


def test_render_verification_report_aggregates_failures(tmp_path: Path):
    clean = RenderVerification([], [], [])
    assert clean.passed
    assert clean.failure_summary() == "passed"

    overflow = frame_check.OverflowFinding(1.5, tmp_path / "frame.png", 0.2)
    failed = RenderVerification([overflow], [], [])
    assert not failed.passed
    assert failed.failure_summary() == "frame overflow at 1.50s"


def test_verify_delivery_file_requires_cfr_audio_and_matching_duration(monkeypatch, tmp_path: Path):
    payload = {
        "streams": [
            {"codec_type": "video", "r_frame_rate": "60/1", "avg_frame_rate": "60/1", "duration": "24.75"},
            {"codec_type": "audio", "duration": "24.746"},
        ]
    }

    class Result:
        stdout = __import__("json").dumps(payload)

    monkeypatch.setattr(frame_check.subprocess, "run", lambda *args, **kwargs: Result())
    report = verify_delivery_file(tmp_path / "delivery.mp4")

    assert report.passed
    assert report.video_fps == 60.0
    assert report.audio_duration == pytest.approx(24.746)


def test_detect_temporal_cuts_ignores_identical_frames(monkeypatch, tmp_path: Path):
    class Result:
        def __init__(self, stdout=b"", text_stdout=""):
            self.stdout = stdout
            self.stdout = text_stdout if text_stdout else stdout

    def fake_run(command, **_kwargs):
        if command[0] == "ffprobe":
            return Result(text_stdout=json.dumps({"streams": [{"width": 100, "height": 100, "duration": "1"}]}))
        return Result(stdout=bytes(160 * 160 * 2))

    monkeypatch.setattr(frame_check.subprocess, "run", fake_run)
    assert detect_temporal_cuts(tmp_path / "stable.mp4") == []


def test_detect_temporal_cuts_flags_a_hard_cut(monkeypatch, tmp_path: Path):
    class Result:
        def __init__(self, stdout=b"", text_stdout=""):
            self.stdout = text_stdout if text_stdout else stdout

    def fake_run(command, **_kwargs):
        if command[0] == "ffprobe":
            return Result(text_stdout=json.dumps({"streams": [{"width": 100, "height": 100, "duration": "1"}]}))
        return Result(stdout=bytes(160 * 160) + bytes([255]) * (160 * 160))

    monkeypatch.setattr(frame_check.subprocess, "run", fake_run)
    findings = detect_temporal_cuts(tmp_path / "cut.mp4")
    assert len(findings) == 1
    assert findings[0].mean_frame_delta == pytest.approx(1.0)
