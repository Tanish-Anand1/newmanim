import math
import json
import subprocess
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Sequence

from PIL import Image
import numpy as np


@dataclass(frozen=True)
class OverflowFinding:
    timestamp: float
    frame_path: Path
    border_pixel_ratio: float


@dataclass(frozen=True)
class TextOverlapFinding:
    timestamp: float
    frame_path: Path
    overlap_ratio: float


@dataclass(frozen=True)
class SparseFrameFinding:
    timestamp: float
    frame_path: Path
    foreground_pixel_ratio: float


@dataclass(frozen=True)
class TemporalCutFinding:
    timestamp: float
    mean_frame_delta: float


@dataclass(frozen=True)
class RenderVerification:
    overflow: list[OverflowFinding]
    text_overlap: list[TextOverlapFinding]
    sparse: list[SparseFrameFinding]
    temporal_cuts: list[TemporalCutFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.overflow or self.text_overlap or self.sparse or self.temporal_cuts)

    def failure_summary(self) -> str:
        parts: list[str] = []
        if self.overflow:
            parts.append(f"frame overflow at {self.overflow[0].timestamp:.2f}s")
        if self.text_overlap:
            parts.append(f"text/element overlap at {self.text_overlap[0].timestamp:.2f}s")
        if self.sparse:
            parts.append(f"nearly empty frame at {self.sparse[0].timestamp:.2f}s")
        if self.temporal_cuts:
            parts.append(f"abrupt frame transition at {self.temporal_cuts[0].timestamp:.2f}s")
        return "; ".join(parts) or "passed"


@dataclass(frozen=True)
class DeliveryVerification:
    passed: bool
    message: str
    video_fps: float | None = None
    audio_duration: float | None = None
    video_duration: float | None = None


def _parse_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else None
    return float(value)


def verify_delivery_file(
    media_path: Path,
    min_fps: float = 45.0,
    max_fps: float = 60.0,
    duration_tolerance: float = 0.15,
) -> DeliveryVerification:
    """Validate the final muxed file's cadence and audio/video alignment."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-of", "json",
            "-show_entries", "stream=codec_type,r_frame_rate,avg_frame_rate,duration",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None:
        return DeliveryVerification(False, "missing video stream")

    frame_rate = _parse_rate(video.get("r_frame_rate"))
    average_rate = _parse_rate(video.get("avg_frame_rate"))
    video_duration = float(video["duration"]) if video.get("duration") else None
    if frame_rate is None or average_rate is None:
        return DeliveryVerification(False, "missing video frame-rate metadata", frame_rate, None, video_duration)
    if frame_rate < min_fps or frame_rate > max_fps:
        return DeliveryVerification(False, f"video frame rate {frame_rate:.3f} is outside {min_fps:.0f}-{max_fps:.0f} fps", frame_rate, None, video_duration)
    if abs(frame_rate - average_rate) > 0.01:
        return DeliveryVerification(False, f"variable frame rate detected ({frame_rate:.3f} vs {average_rate:.3f})", frame_rate, None, video_duration)
    if audio is None:
        return DeliveryVerification(False, "missing audio stream", frame_rate, None, video_duration)

    audio_duration = float(audio["duration"]) if audio.get("duration") else None
    if video_duration is None or audio_duration is None:
        return DeliveryVerification(False, "missing audio/video duration metadata", frame_rate, audio_duration, video_duration)
    if abs(video_duration - audio_duration) > duration_tolerance:
        return DeliveryVerification(
            False,
            f"audio/video duration mismatch ({audio_duration:.3f}s vs {video_duration:.3f}s)",
            frame_rate,
            audio_duration,
            video_duration,
        )
    return DeliveryVerification(True, "passed", frame_rate, audio_duration, video_duration)


def assert_delivery_file_clean(media_path: Path) -> DeliveryVerification:
    report = verify_delivery_file(media_path)
    if not report.passed:
        raise RuntimeError(f"Final delivery verification failed: {report.message}")
    return report


def get_media_duration(media_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def sample_timestamps(duration: float, sample_count: int = 8) -> list[float]:
    if duration <= 0:
        return []
    count = max(5, min(sample_count, 120))
    if duration < count:
        count = max(1, math.floor(duration))
    return [duration * (i + 1) / (count + 1) for i in range(count)]


def extract_sample_frames(video_path: Path, out_dir: Path, sample_count: int = 8) -> list[tuple[float, Path]]:
    return extract_frames_at_timestamps(video_path, out_dir, sample_timestamps(get_media_duration(video_path), sample_count))


def beat_quality_timestamps(
    duration: float,
    beat_windows: Sequence[tuple[float, float]],
    sample_count: int = 8,
) -> list[float]:
    """Choose post-reveal frames, avoiding arbitrary mid-animation samples."""
    if duration <= 0 or not beat_windows:
        return []
    count = min(max(1, sample_count), len(beat_windows))
    if len(beat_windows) <= count:
        selected = list(beat_windows)
    else:
        indexes = [round(index * (len(beat_windows) - 1) / (count - 1)) for index in range(count)]
        selected = [beat_windows[index] for index in indexes]

    timestamps: list[float] = []
    for start, end in selected:
        start = max(0.0, float(start))
        end = min(duration, float(end))
        span = max(0.1, end - start)
        # The final fifth is reserved for beat cleanup. Sampling at 80% gives
        # Write/Create animations time to finish while retaining beat content.
        timestamp = min(end - min(0.35, span * 0.08), start + span * 0.80)
        timestamps.append(max(start + min(0.1, span * 0.2), min(duration - 0.02, timestamp)))
    return timestamps


def extract_beat_quality_frames(
    video_path: Path,
    out_dir: Path,
    beat_windows: Sequence[tuple[float, float]],
    sample_count: int = 8,
) -> list[tuple[float, Path]]:
    duration = get_media_duration(video_path)
    timestamps = beat_quality_timestamps(duration, beat_windows, sample_count)
    return extract_frames_at_timestamps(video_path, out_dir, timestamps)


def beat_content_stability_timestamps(
    duration: float,
    beat_windows: Sequence[tuple[float, float]],
    sample_positions: Sequence[float] = (0.60, 0.80),
) -> list[float]:
    """Sample stable interior points for each beat without inspecting reveal/fade edges."""
    if duration <= 0 or not beat_windows:
        return []

    timestamps: list[float] = []
    for start, end in beat_windows:
        start = max(0.0, float(start))
        end = min(duration, float(end))
        span = end - start
        if span <= 0.15:
            continue
        final_fade_reserve = min(0.35, span * 0.08)
        latest_content_time = max(start + span * 0.50, end - final_fade_reserve)
        for position in sample_positions:
            normalized = min(0.88, max(0.50, float(position)))
            timestamp = min(latest_content_time, start + span * normalized)
            timestamps.append(max(start + min(0.20, span * 0.15), timestamp))

    return timestamps


def extract_frames_at_timestamps(
    video_path: Path,
    out_dir: Path,
    timestamps: Sequence[float],
) -> list[tuple[float, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, Path]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        frame_path = out_dir / f"sample_{index:02d}_{timestamp:.2f}s.png"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                # Seek after opening the input so validation inspects the requested
                # rendered frame instead of an earlier keyframe.
                "-ss",
                f"{timestamp:.3f}",
                "-frames:v",
                "1",
                str(frame_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        frames.append((timestamp, frame_path))
    return frames


def border_content_ratio(
    frame_path: Path,
    border_fraction: float = 0.02,
    background_rgb: tuple[int, int, int] | None = None,
    channel_tolerance: int = 24,
) -> float:
    border_width = 2
    with Image.open(frame_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = rgb.load()
        # Scenes may use a non-black background. Use a corner sample as the
        # local background unless a caller supplies an explicit color.
        background_rgb = background_rgb or pixels[0, 0]
        
        # Scan top and bottom borders
        for y in list(range(border_width)) + list(range(height - border_width, height)):
            for x in range(width):
                r, g, b = pixels[x, y]
                if (abs(r - background_rgb[0]) > channel_tolerance or 
                    abs(g - background_rgb[1]) > channel_tolerance or 
                    abs(b - background_rgb[2]) > channel_tolerance):
                    return 1.0
                    
        # Scan left and right borders
        for y in range(border_width, height - border_width):
            for x in list(range(border_width)) + list(range(width - border_width, width)):
                r, g, b = pixels[x, y]
                if (abs(r - background_rgb[0]) > channel_tolerance or 
                    abs(g - background_rgb[1]) > channel_tolerance or 
                    abs(b - background_rgb[2]) > channel_tolerance):
                    return 1.0
                    
    return 0.0


def foreground_pixel_ratio(
    frame_path: Path,
    background_rgb: tuple[int, int, int] = (0, 0, 0),
    channel_tolerance: int = 32,
) -> float:
    """Return the visible-content fraction on a downsampled frame."""
    with Image.open(frame_path) as image:
        rgb = image.convert("RGB")
        if rgb.width > 360:
            new_height = max(1, int(rgb.height * 360 / rgb.width))
            rgb = rgb.resize((360, new_height), Image.Resampling.BILINEAR)
    pixels = rgb.get_flattened_data()
    foreground = sum(
        1
        for red, green, blue in pixels
            if (
                abs(red - background_rgb[0]) > channel_tolerance
                or abs(green - background_rgb[1]) > channel_tolerance
                or abs(blue - background_rgb[2]) > channel_tolerance
            )
        )
    return foreground / len(pixels) if pixels else 0.0


def detect_sparse_frames(
    video_path: Path,
    work_dir: Path,
    sample_count: int = 8,
    minimum_foreground_ratio: float = 0.002,
    consecutive_samples: int = 2,
    beat_windows: Sequence[tuple[float, float]] | None = None,
) -> list[SparseFrameFinding]:
    """Flag sustained nearly empty output without penalizing a brief intentional transition.

    Whole-video samples are inexpensive but can skip a short broken portion of
    a long beat. When beat windows are available, inspect two post-reveal
    interior points per beat so a diagram or equation cannot disappear during
    the explanatory hold and return before the next global sample.
    """
    findings: list[SparseFrameFinding] = []
    sparse_run = 0
    required_run = max(1, consecutive_samples)
    if beat_windows:
        timestamps = beat_content_stability_timestamps(get_media_duration(video_path), beat_windows)
        samples = extract_frames_at_timestamps(video_path, work_dir, timestamps)
    else:
        samples = extract_sample_frames(video_path, work_dir, sample_count)

    for timestamp, frame_path in samples:
        ratio = foreground_pixel_ratio(frame_path)
        if ratio < minimum_foreground_ratio:
            sparse_run += 1
            if sparse_run >= required_run:
                findings.append(
                    SparseFrameFinding(
                        timestamp=timestamp,
                        frame_path=frame_path,
                        foreground_pixel_ratio=ratio,
                    )
                )
        else:
            sparse_run = 0
    return findings


def detect_frame_overflow(
    video_path: Path,
    work_dir: Path,
    sample_count: int = 8,
    significant_ratio: float = 0.005,
) -> list[OverflowFinding]:
    findings: list[OverflowFinding] = []
    for timestamp, frame_path in extract_sample_frames(video_path, work_dir, sample_count):
        ratio = border_content_ratio(frame_path)
        if ratio >= significant_ratio:
            findings.append(
                OverflowFinding(
                    timestamp=timestamp,
                    frame_path=frame_path,
                    border_pixel_ratio=ratio,
                )
            )
    return findings


def foreground_bounds(
    frame_path: Path,
    background_rgb: tuple[int, int, int] = (0, 0, 0),
    channel_tolerance: int = 32,
    min_pixels: int = 24,
) -> list[tuple[int, int, int, int]]:
    with Image.open(frame_path) as image:
        rgb_image = image.convert("RGB")
        if rgb_image.width > 420:
            new_height = max(1, int(rgb_image.height * 420 / rgb_image.width))
            rgb_image = rgb_image.resize((420, new_height), Image.Resampling.BILINEAR)
        gray = rgb_image
        width, height = gray.size
        pixels = gray.load()
        visited: set[tuple[int, int]] = set()
        bounds: list[tuple[int, int, int, int]] = []

        def is_foreground(x: int, y: int) -> bool:
            r, g, b = pixels[x, y]
            return (
                abs(r - background_rgb[0]) > channel_tolerance
                or abs(g - background_rgb[1]) > channel_tolerance
                or abs(b - background_rgb[2]) > channel_tolerance
            )

        for y in range(height):
            for x in range(width):
                if (x, y) in visited or not is_foreground(x, y):
                    continue

                stack = [(x, y)]
                visited.add((x, y))
                min_x = max_x = x
                min_y = max_y = y
                count = 0

                while stack:
                    cx, cy = stack.pop()
                    count += 1
                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if nx < 0 or nx >= width or ny < 0 or ny >= height:
                            continue
                        if (nx, ny) in visited or not is_foreground(nx, ny):
                            continue
                        visited.add((nx, ny))
                        stack.append((nx, ny))

                if count >= min_pixels:
                    bounds.append((min_x, min_y, max_x + 1, max_y + 1))

    return merge_contained_bounds(merge_text_like_bounds(bounds))


def merge_text_like_bounds(bounds: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for box in sorted(bounds, key=lambda item: (item[1], item[0])):
        x1, y1, x2, y2 = box
        width = x2 - x1
        height = y2 - y1
        if width < 2 or height < 2:
            continue

        matched = False
        for index, current in enumerate(merged):
            cx1, cy1, cx2, cy2 = current
            vertical_overlap = max(0, min(y2, cy2) - max(y1, cy1))
            smaller_height = max(1, min(height, cy2 - cy1))
            horizontal_gap = max(0, max(x1, cx1) - min(x2, cx2))
            same_line = vertical_overlap / smaller_height >= 0.35 and horizontal_gap <= max(20, height * 1.5)
            stacked_equation = abs((x1 + x2) / 2 - (cx1 + cx2) / 2) <= max(width, cx2 - cx1) * 0.35
            close_stack = max(0, max(y1, cy1) - min(y2, cy2)) <= max(height, cy2 - cy1) * 0.45
            if same_line or (stacked_equation and close_stack):
                merged[index] = (min(x1, cx1), min(y1, cy1), max(x2, cx2), max(y2, cy2))
                matched = True
                break
        if not matched:
            merged.append(box)

    return merged


def merge_contained_bounds(bounds: list[tuple[int, int, int, int]], threshold: float = 0.80) -> list[tuple[int, int, int, int]]:
    current = bounds
    while True:
        merged: list[tuple[int, int, int, int]] = []
        changed = False
        for box in current:
            x1, y1, x2, y2 = box
            width = x2 - x1
            height = y2 - y1
            
            matched = False
            for index, existing in enumerate(merged):
                cx1, cy1, cx2, cy2 = existing
                cw = cx2 - cx1
                ch = cy2 - cy1
                
                # Calculate overlap
                overlap_w = max(0, min(x2, cx2) - max(x1, cx1))
                overlap_h = max(0, min(y2, cy2) - max(y1, cy1))
                overlap_area = overlap_w * overlap_h
                
                if overlap_area > 0:
                    area_a = width * height
                    area_b = cw * ch
                    min_area = min(area_a, area_b)
                    
                    # If one is mostly contained in another
                    if overlap_area / min_area >= threshold:
                        merged[index] = (min(x1, cx1), min(y1, cy1), max(x2, cx2), max(y2, cy2))
                        matched = True
                        changed = True
                        break
            if not matched:
                merged.append(box)
        if not changed or len(merged) == len(current):
            break
        current = merged
    return current


def overlap_ratio(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    overlap_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    overlap_h = max(0, min(ay2, by2) - max(ay1, by1))
    overlap_area = overlap_w * overlap_h
    if overlap_area == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))

    # Ignore if either box is extremely small (area < 1000) to avoid false positives on unmerged dots/letters/punctuation
    if area_a < 1000 or area_b < 1000:
        return 0.0

    # If one of the boxes is a huge graph container (e.g. width and height > 120, area > 20000)
    # and the other box is a small element/label (area < 8000), do not treat containment as a collision.
    # A true collision is when two elements of comparable size overlap, or when two labels overlap.
    large_area = max(area_a, area_b)
    small_area = min(area_a, area_b)
    w_a, h_a = ax2 - ax1, ay2 - ay1
    w_b, h_b = bx2 - bx1, by2 - by1
    max_w = max(w_a, w_b)
    max_h = max(h_a, h_b)
    if large_area > 20000 and max_w > 120 and max_h > 120 and small_area < 8000:
        return 0.0

    return overlap_area / min(area_a, area_b)


def max_pair_overlap(bounds: list[tuple[int, int, int, int]]) -> float:
    best = 0.0
    for index, box in enumerate(bounds):
        for other in bounds[index + 1 :]:
            best = max(best, overlap_ratio(box, other))
    return best


def detect_text_overlap(
    video_path: Path,
    work_dir: Path,
    sample_count: int = 8,
    overlap_threshold: float = 0.55,
) -> list[TextOverlapFinding]:
    findings: list[TextOverlapFinding] = []
    consecutive_hits = 0
    for timestamp, frame_path in extract_sample_frames(video_path, work_dir, sample_count):
        ratio = max_pair_overlap(foreground_bounds(frame_path))
        if ratio >= overlap_threshold:
            consecutive_hits += 1
            if consecutive_hits >= 2:
                findings.append(
                    TextOverlapFinding(
                        timestamp=timestamp,
                        frame_path=frame_path,
                        overlap_ratio=ratio,
                    )
                )
        else:
            consecutive_hits = 0
    return findings


def detect_temporal_cuts(
    video_path: Path,
    sample_fps: int = 12,
    threshold: float = 0.28,
) -> list[TemporalCutFinding]:
    """Detect unusually large adjacent-frame changes at a low-cost preview size.

    Normal drawing, transforms, and fades change gradually. A hard cut or an
    inserted blank frame produces a much larger normalized pixel delta. The
    conservative threshold is intentionally limited to severe discontinuities.
    """
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-of", "json",
            "-show_entries", "stream=width,height,duration",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    video = next((stream for stream in streams if stream.get("width") and stream.get("height")), None)
    if video is None:
        return []
    source_width = int(video["width"])
    source_height = int(video["height"])
    width = 160
    height = max(2, int(round(source_height * width / source_width)))
    decoded = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(video_path),
            "-vf", f"fps={sample_fps},scale={width}:{height},format=gray",
            "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    frame_bytes = width * height
    frame_count = len(decoded) // frame_bytes
    if frame_count < 2:
        return []
    frames = np.frombuffer(decoded[: frame_count * frame_bytes], dtype=np.uint8)
    frames = frames.reshape((frame_count, height, width)).astype(np.float32)
    deltas = np.abs(frames[1:] - frames[:-1]).mean(axis=(1, 2)) / 255.0
    duration = float(video.get("duration") or 0.0)
    findings: list[TemporalCutFinding] = []
    for index, delta in enumerate(deltas, start=1):
        if float(delta) >= threshold:
            timestamp = min(duration, index / sample_fps)
            findings.append(TemporalCutFinding(timestamp, float(delta)))
    return findings


def verify_rendered_video(
    video_path: Path,
    work_dir: Path,
    sample_count: int = 8,
    beat_windows: Sequence[tuple[float, float]] | None = None,
) -> RenderVerification:
    """Run the cheap post-render gates before audio mux/upload.

    The checks deliberately inspect extracted frames rather than generated
    source code: clipping and collisions are geometric properties of the
    rendered output and can only be trusted after rasterization.
    """
    overflow = detect_frame_overflow(video_path, work_dir / "overflow_samples", sample_count)
    text_overlap = detect_text_overlap(video_path, work_dir / "overlap_samples", sample_count)
    sparse = detect_sparse_frames(
        video_path,
        work_dir / "sparse_samples",
        sample_count,
        beat_windows=beat_windows,
    )
    temporal_cuts = detect_temporal_cuts(video_path)
    return RenderVerification(
        overflow=overflow,
        text_overlap=text_overlap,
        sparse=sparse,
        temporal_cuts=temporal_cuts,
    )


def assert_rendered_video_clean(
    video_path: Path,
    work_dir: Path,
    sample_count: int = 8,
    beat_windows: Sequence[tuple[float, float]] | None = None,
) -> RenderVerification:
    report = verify_rendered_video(video_path, work_dir, sample_count, beat_windows)
    if not report.passed:
        raise RuntimeError(f"Post-render verification failed: {report.failure_summary()}")
    return report
