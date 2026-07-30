"""Stitch three Manim chapter clips with synchronized video/audio crossfades.

Usage:
  python scripts/stitch_multi_scene.py \
    --video chapter1.mp4 --video chapter2.mp4 --video chapter3.mp4 \
    --audio chapter1.mp3 --audio chapter2.mp3 --audio chapter3.mp3 \
    --output final.mp4

All offsets and duration checks come from ffprobe; no expected duration is
used for the filter graph.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RuntimeError(f"{path} has no video stream")
    duration = float(video.get("duration") or data.get("format", {}).get("duration"))
    return {"path": path, "duration": duration, "video": video, "audio": audio}


def rate(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def validate_inputs(videos: list[dict], audios: list[Path]) -> None:
    first = videos[0]["video"]
    signature = (first.get("width"), first.get("height"), rate(first["r_frame_rate"]), first.get("codec_name"))
    for item in videos:
        stream = item["video"]
        current = (stream.get("width"), stream.get("height"), rate(stream["r_frame_rate"]), stream.get("codec_name"))
        if current != signature:
            raise RuntimeError(f"Chapter media mismatch: expected {signature}, got {current} for {item['path']}")
        if item["audio"] is None:
            raise RuntimeError(f"{item['path']} has no embedded audio stream")
    if len(videos) != 3 or len(audios) != 3:
        raise ValueError("Exactly three video and three audio inputs are required.")
    for audio in audios:
        if not audio.is_file():
            raise FileNotFoundError(audio)


def build_filter(durations: list[float], fade: float) -> tuple[str, float, float]:
    if any(duration <= fade for duration in durations):
        raise RuntimeError(f"Each chapter must be longer than the {fade:.2f}s crossfade.")
    offset_one = durations[0] - fade
    offset_two = durations[0] + durations[1] - 2 * fade
    filter_graph = (
        f"[0:v][1:v]xfade=transition=fade:duration={fade:.6f}:offset={offset_one:.6f}[v01];"
        f"[v01][2:v]xfade=transition=fade:duration={fade:.6f}:offset={offset_two:.6f}[vout];"
        "[0:a][1:a]acrossfade=d=0.6:c1=tri:c2=tri[a01];"
        "[a01][2:a]acrossfade=d=0.6:c1=tri:c2=tri[aout]"
    )
    return filter_graph, offset_one, offset_two


def stitch(videos: list[Path], audios: list[Path], output: Path, fade: float = 0.6) -> dict:
    metadata = [probe(path) for path in videos]
    validate_inputs(metadata, audios)
    graph, offset_one, offset_two = build_filter([item["duration"] for item in metadata], fade)
    args = ["ffmpeg", "-y"]
    for video, audio in zip(videos, audios):
        args += ["-i", str(video), "-i", str(audio)]
    args += [
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "str(60)",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ]
    # Replace the literal construction above with the numeric option; keeping
    # it explicit makes the constant-frame-rate requirement easy to audit.
    args[args.index("str(60)")] = "60"
    subprocess.run(args, check=True)
    return {"output": str(output), "durations": [item["duration"] for item in metadata], "offsets": [offset_one, offset_two], "fade": fade}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", action="append", required=True)
    parser.add_argument("--audio", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fade", type=float, default=0.6)
    args = parser.parse_args()
    if len(args.video) != 3 or len(args.audio) != 3:
        parser.error("pass exactly three --video and three --audio arguments")
    print(json.dumps(stitch([Path(p) for p in args.video], [Path(p) for p in args.audio], Path(args.output), args.fade), indent=2))


if __name__ == "__main__":
    main()
