import sys
sys.path.insert(0, r'C:\PROJECTS\newmanim')
from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import BACKGROUND_COLOR
from app.craft_library import ensure_contrast
import numpy as np
import re

# --- Video semantic color palette (defined once, reused by every beat) ---
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
    for _ in range(24):
        left = mobj.get_left()[0] - min_gap
        right = mobj.get_right()[0] + min_gap
        bottom = mobj.get_bottom()[1] - min_gap
        top = mobj.get_top()[1] + min_gap
        collision = None
        for other in others:
            separated = (right < other.get_left()[0] or left > other.get_right()[0] or
                         top < other.get_bottom()[1] or bottom > other.get_top()[1])
            if not separated:
                collision = other
                break
        if collision is None:
            return mobj
        direction = mobj.get_center() - collision.get_center()
        if np.linalg.norm(direction) < 1e-6:
            direction = UP
        mobj.shift(direction / np.linalg.norm(direction) * 0.16)
    return mobj

def fitted_text(value, font_size=34, color=SECONDARY_COLOR, max_width=None):
    ensure_contrast(color, BACKGROUND_COLOR)
    item = Text(value, font_size=font_size, color=color)
    # Keep a generous horizontal safety margin for emphasis animations.
    width_limit = max_width or config.frame_width * 0.76
    if item.width > width_limit:
        item.scale_to_fit_width(width_limit)
    return item

def safe_math(value, font_size=42, color=SECONDARY_COLOR):
    ensure_contrast(color, BACKGROUND_COLOR)
    value = re.sub(r'\\displaystyle\b', '', str(value)).strip()
    item = MathTex(value, font_size=font_size, color=color)
    if item.width > config.frame_width * 0.76:
        item.scale_to_fit_width(config.frame_width * 0.76)
    return item

def safe_scale(mobj, scale_factor, max_width_pct=0.85, max_height_pct=0.75):
    if mobj.width <= 1e-6 or mobj.height <= 1e-6:
        return mobj.animate.scale(scale_factor)
    max_w = config.frame_width * max_width_pct
    max_h = config.frame_height * max_height_pct
    allowed_scale = min(max_w / mobj.width, max_h / mobj.height)
    return mobj.animate.scale(min(scale_factor, allowed_scale))

def place_graph_title(title, axes, min_buffer=0.4, min_clearance=0.3):
    # Position relative to the actual axes, then enforce numeric clearance.
    title.next_to(axes, UP, buff=max(0.4, min_buffer))
    axis_line_y = axes.x_axis.get_center()[1]
    minimum_title_bottom = axis_line_y + max(0.3, min_clearance)
    if title.get_bottom()[1] <= minimum_title_bottom:
        title.shift(UP * (minimum_title_bottom - title.get_bottom()[1] + 0.02))
    return title

def make_visual(kind, labels, portrait=True):
    if kind == 'pendulum':
        pivot = Dot(UP * 1.35, radius=0.06, color=PRIMARY_COLOR)
        angle_tracker = ValueTracker(0.0)
        def build_pendulum():
            angle = angle_tracker.get_value()
            pivot_point = UP * 1.35
            bob_point = pivot_point + RIGHT * (2.25 * np.sin(angle)) + DOWN * (2.25 * np.cos(angle))
            string = Line(pivot_point, bob_point, color=STRUCTURE_COLOR)
            bob = Circle(radius=0.22, color=PRIMARY_COLOR, fill_opacity=0.35).move_to(bob_point)
            toward_pivot = (pivot_point - bob_point) / np.linalg.norm(pivot_point - bob_point)
            tension = Arrow(bob_point, bob_point + toward_pivot * 0.82, buff=0, color=SECONDARY_COLOR)
            gravity = Arrow(bob_point, bob_point + DOWN * 0.78, buff=0, color=NEGATIVE_COLOR)
            tangent = RIGHT * np.cos(angle) + UP * np.sin(angle)
            restoring_direction = -np.sign(angle) * tangent if abs(angle) > 1e-5 else LEFT
            restoring = Arrow(bob_point, bob_point + restoring_direction * (0.18 + 0.62 * abs(np.sin(angle))), buff=0, color=RELATION_COLOR)
            angle_arc = Arc(radius=0.48, start_angle=-PI / 2, angle=angle, color=HIGHLIGHT_COLOR).move_to(pivot_point)
            theta_label = safe_math(r'\theta', font_size=26, color=HIGHLIGHT_COLOR).next_to(angle_arc, RIGHT, buff=0.10)
            tension_label = safe_math('T', font_size=22, color=SECONDARY_COLOR).next_to(tension, UP, buff=0.08)
            gravity_label = safe_math('mg', font_size=22, color=NEGATIVE_COLOR).next_to(gravity, RIGHT, buff=0.08)
            restoring_label = safe_math('F_r', font_size=22, color=RELATION_COLOR).next_to(restoring, DOWN, buff=0.08)
            return VGroup(string, bob, tension, gravity, restoring, angle_arc, theta_label, tension_label, gravity_label, restoring_label)
        pendulum_group = always_redraw(build_pendulum)
        visual = VGroup(pivot, pendulum_group)
        visual.angle_tracker = angle_tracker
        return visual
    return VGroup()

def animate_visual(scene, kind, visual, duration, stagger=False):
    duration = max(0.08, duration)
    if len(visual) == 0:
        return
    if kind == 'pendulum':
        if not getattr(scene, '_pendulum_anchor_mounted', False):
            scene.safe_add(visual, zone='anchor', animation=AnimationGroup(Create(visual[0]), FadeIn(visual[1]), lag_ratio=0.18))
            scene._pendulum_anchor_mounted = True
        scene.play(visual.angle_tracker.animate.set_value(0.52), run_time=duration * 0.38)
        scene.play(visual.angle_tracker.animate.set_value(-0.52), run_time=duration * 0.62)
        return
    scene.play(FadeIn(visual), run_time=duration)

class PendulumTestScene(VivacityScene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR

        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 0.3
        beat1_speed = 0.3200
        # --- Beat 1 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat1_heading = fitted_text('Pendulum bob pivot string angle theta', font_size=24, color=TITLE_COLOR)
        beat1_items = VGroup()
        if len(beat1_items) > 0:
            beat1_items.arrange(DOWN, buff=beat1_gap, aligned_edge=LEFT)
        beat1_visual = make_visual('pendulum', [], portrait=True)
        beat1_content = VGroup(beat1_items, beat1_visual)
        beat1_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat1_diagram = VGroup(beat1_heading, beat1_content).arrange(DOWN, buff=0.38)
        beat1_diagram.scale(beat1_scale)
        beat1_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat1_diagram.width > config.frame_width * 0.76:
            beat1_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat1_diagram.move_to(ORIGIN)
        beat1_overlap_obstacles = [beat1_visual] if len(beat1_visual) > 0 else []
        avoid_overlap(beat1_heading, beat1_overlap_obstacles, min_gap=0.0)
        beat1_overlap_obstacles.append(beat1_heading)
        if beat1_diagram.height > config.frame_height * 0.55:
            beat1_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat1_diagram.width > config.frame_width * 0.76:
            beat1_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat1_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat1_heading), run_time=beat1_speed)
        if len(beat1_visual) > 0:
            animate_visual(self, 'pendulum', beat1_visual, 1.2800, stagger=False)
        else:
            pass
        self.wait(1.9200)
        self.play(FadeOut(VGroup(beat1_heading, beat1_items)), run_time=0.4800)

        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 0.3
        beat2_speed = 0.3200
        # --- Beat 2 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=True
        beat2_heading = fitted_text('Tension gravity restoring force vectors updating', font_size=24, color=TITLE_COLOR)
        beat2_items = VGroup()
        if len(beat2_items) > 0:
            beat2_items.arrange(DOWN, buff=beat2_gap, aligned_edge=LEFT)
        beat2_visual = make_visual('pendulum', [], portrait=True)
        beat2_content = VGroup(beat2_items, beat2_visual)
        beat2_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat2_diagram = VGroup(beat2_heading, beat2_content).arrange(DOWN, buff=0.38)
        beat2_diagram.scale(beat2_scale)
        beat2_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat2_diagram.width > config.frame_width * 0.76:
            beat2_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat2_diagram.move_to(ORIGIN)
        beat2_overlap_obstacles = [beat2_visual] if len(beat2_visual) > 0 else []
        avoid_overlap(beat2_heading, beat2_overlap_obstacles, min_gap=0.0)
        beat2_overlap_obstacles.append(beat2_heading)
        if beat2_diagram.height > config.frame_height * 0.55:
            beat2_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat2_diagram.width > config.frame_width * 0.76:
            beat2_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat2_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat2_heading), run_time=beat2_speed)
        if len(beat2_visual) > 0:
            self.safe_visual_transform(beat1_visual, beat2_visual, run_time=1.2800)
        else:
            pass
        self.play(beat2_visual.angle_tracker.animate.set_value(-0.52), run_time=0.7040)
        self.wait(1.9200)
        self.play(FadeOut(beat2_diagram), run_time=0.4800)
