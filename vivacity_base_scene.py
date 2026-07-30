"""Shared enforcement surface for maintained Vivacity Manim scenes."""

from __future__ import annotations

import numpy as np
from manim import *
from manim.utils.color.core import color_to_rgb


class VivacityScene(Scene):
    """Base class for maintained scenes.

    Text creation, title fitting, tracked labels, and text transitions belong
    here so scene-level checks can enforce the same behavior across videos.
    """

    EQUATION_COLOR = WHITE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mounted_mobjects: set[int] = set()
        self._zone_mobjects = {"top": [], "bottom": [], "anchor": []}

    def _bounding_boxes_intersect(self, first, second) -> bool:
        return not (
            first.get_right()[0] < second.get_left()[0]
            or first.get_left()[0] > second.get_right()[0]
            or first.get_top()[1] < second.get_bottom()[1]
            or first.get_bottom()[1] > second.get_top()[1]
        )

    def _check_overlap(self, mobject, zone):
        if zone not in self._zone_mobjects:
            raise ValueError(f"Unknown overlap zone: {zone}")
        for existing in self._zone_mobjects[zone]:
            if existing is mobject:
                continue
            if self._bounding_boxes_intersect(mobject, existing):
                raise AssertionError(
                    f"Overlap detected in '{zone}' zone: new mobject overlaps "
                    f"'{existing}' - remove/fade the old mobject via safe_swap "
                    "before adding this, or reposition so bounding boxes do not intersect."
                )
        self._zone_mobjects[zone].append(mobject)

    def _remove_from_zone(self, mobject, zone):
        if zone in self._zone_mobjects and mobject in self._zone_mobjects[zone]:
            self._zone_mobjects[zone].remove(mobject)

    def safe_position(self, mobject, zone):
        """Re-check a text object after its caller has positioned it."""
        if zone is not None:
            self._remove_from_zone(mobject, zone)
            self._check_overlap(mobject, zone)
        return mobject

    def safe_title(self, text: str) -> Tex:
        title = Tex(text)
        title.scale_to_fit_width(config.frame_width - 1.2)
        title.to_edge(UP, buff=0.4)
        assert title.width <= config.frame_width - 0.5, (
            f"safe_title: '{text}' still exceeds frame after scaling"
        )
        return title

    def safe_text(self, *tex_strings: str, zone=None, color=None, **kwargs) -> MathTex:
        """Create fitted, contrast-checked MathTex with stable parts."""
        color = color or self.EQUATION_COLOR
        mobject = MathTex(*tex_strings, color=color, **kwargs)
        self._fit_to_frame(mobject)
        self._ensure_contrast(mobject)
        if zone is not None:
            self._check_overlap(mobject, zone)
        return mobject

    def safe_swap(self, old_mobject, new_mobject, zone="top"):
        """Transition text/equation states through one controlled path."""
        self._remove_from_zone(old_mobject, zone)
        if isinstance(old_mobject, (Tex, MathTex)) and isinstance(new_mobject, (Tex, MathTex)):
            def discrete_handoff(t):
                return 0.0 if t < 0.5 else 1.0

            self.play(
                TransformMatchingTex(
                    old_mobject,
                    new_mobject,
                    transform_mismatches=True,
                    rate_func=discrete_handoff,
                )
            )
        else:
            self.play(FadeOut(old_mobject, run_time=0.2))
            self.play(FadeIn(new_mobject, run_time=0.3))
        self._check_overlap(new_mobject, zone)

    def safe_visual_transform(self, old_mobject, new_mobject, *animations, zone=None, **kwargs):
        """Controlled non-text transform for diagrams and geometry."""
        # Atwood diagrams are persistent anchors. Their generated beat targets
        # describe the same pulley/mass system, so rebuilding them would create
        # concentric pulley rings during interpolation. Reuse the mounted
        # tracker instead of transforming a second diagram into the scene.
        tracker_name = next(
            (name for name in ("motion_tracker", "angle_tracker")
             if hasattr(old_mobject, name) and hasattr(new_mobject, name)),
            None,
        )
        if zone == "anchor" and tracker_name:
            setattr(new_mobject, tracker_name, getattr(old_mobject, tracker_name))
            self.wait(float(kwargs.get("run_time", 0.0)))
            return
        if zone is not None:
            self._remove_from_zone(old_mobject, zone)
            self._check_overlap(new_mobject, zone)
        self.play(Transform(old_mobject, new_mobject), *animations, **kwargs)
        if zone is not None:
            self._remove_from_zone(new_mobject, zone)
            # The rendered object is `old_mobject`, but subsequent generated
            # beats refer to the target object. Track that logical target so
            # chained handoffs do not look like duplicate anchor content.
            self._zone_mobjects[zone].append(new_mobject)

    def safe_add(self, mobject, zone=None, animation=None):
        """Mount a mobject and record it for scene compliance diagnostics."""
        if zone is not None:
            self._check_overlap(mobject, zone)
        if animation is not None:
            self.play(animation)
        elif isinstance(mobject, (Tex, MathTex, Text)):
            self.play(Write(mobject))
        else:
            self.add(mobject)
        self._mounted_mobjects.add(id(mobject))

    def live_value_label(self, tracker: ValueTracker, position_updater, fmt="{:.1f}"):
        """Create a label whose value and position follow a tracker."""
        return always_redraw(
            lambda: MathTex(fmt.format(tracker.get_value())).move_to(position_updater())
        )

    def _fit_to_frame(self, mobject, max_width_ratio=0.9, max_height_ratio=0.9):
        max_width = config.frame_width * max_width_ratio
        max_height = config.frame_height * max_height_ratio
        if mobject.width > max_width:
            mobject.scale_to_fit_width(max_width)
        if mobject.height > max_height:
            mobject.scale_to_fit_height(max_height)

    def _ensure_contrast(self, mobject):
        foreground = np.asarray(color_to_rgb(mobject.get_color()), dtype=float)
        background = np.asarray(color_to_rgb(self.camera.background_color), dtype=float)
        luminance_delta = abs(
            float(np.dot(foreground, np.array([0.2126, 0.7152, 0.0722])))
            - float(np.dot(background, np.array([0.2126, 0.7152, 0.0722])))
        )
        assert luminance_delta >= 0.12, (
            f"Text contrast is too low: luminance delta={luminance_delta:.3f}"
        )
