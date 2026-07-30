"""Shared visual constants for multi-scene Vivacity deliveries."""

BACKGROUND_COLOR = "#0b1020"
EQUATION_COLOR = "#69d2ff"
PRIMARY_COLOR = "#f7c948"
SECONDARY_COLOR = "#ff9f68"
MUTED_COLOR = "#cbd5e1"
FONT = "DejaVu Sans"
FPS = 60
WIDTH = 1920
HEIGHT = 1080
CROSSFADE_SECONDS = 0.6

# Named output presets. Manim derives frame dimensions from these consistently
# when a delivery target is selected; scene code should not embed magic sizes.
OUTPUT_PRESETS = {
    "reels_shorts": {"width": 1080, "height": 1920, "frame_width": 9.0, "frame_height": 16.0},
    "youtube_landscape": {"width": 1920, "height": 1080, "frame_width": 16.0, "frame_height": 9.0},
    "instagram_square": {"width": 1080, "height": 1080, "frame_width": 12.0, "frame_height": 12.0},
    "instagram_portrait": {"width": 1080, "height": 1350, "frame_width": 4.0, "frame_height": 5.0},
}
