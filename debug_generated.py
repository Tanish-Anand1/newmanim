from manim import *
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
    item = Text(value, font_size=font_size, color=color)
    # Keep a generous horizontal safety margin for emphasis animations.
    width_limit = max_width or config.frame_width * 0.76
    if item.width > width_limit:
        item.scale_to_fit_width(width_limit)
    return item

def safe_math(value, font_size=42, color=SECONDARY_COLOR):
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
    title.next_to(axes, UP, buff=max(0.4, min_buffer))
    axis_line_y = axes.x_axis.get_center()[1]
    minimum_title_bottom = axis_line_y + max(0.3, min_clearance)
    if title.get_bottom()[1] <= minimum_title_bottom:
        title.shift(UP * (minimum_title_bottom - title.get_bottom()[1] + 0.01))
    return title

def make_visual(kind, labels, portrait=True):
    if kind == 'geometry':
        circle = Circle(radius=1.2, color=PRIMARY_COLOR)
        radius = Line(circle.get_center(), circle.get_right(), color=STRUCTURE_COLOR)
        label = fitted_text(labels[0] if labels else 'r', font_size=27, color=PRIMARY_COLOR)
        label.next_to(radius, UP, buff=0.3)
        avoid_overlap(label, [circle, radius], min_gap=0.3)
        return VGroup(circle, radius, label)
    if kind == 'vsepr_compare':
        molecule_scale = 0.92 if portrait else 0.72
        ch4 = make_visual('vsepr_ch4', [], portrait=portrait).scale(molecule_scale)
        nh3 = make_visual('vsepr_nh3', [], portrait=portrait).scale(molecule_scale)
        ch4_label = safe_math(r'CH_4', font_size=26, color=CENTRAL_ATOM_COLOR)
        nh3_label = safe_math(r'NH_3', font_size=26, color=CENTRAL_ATOM_COLOR)
        ch4_descriptor = fitted_text('tetrahedral', font_size=17, color=STRUCTURE_COLOR)
        nh3_descriptor = fitted_text('trigonal pyramidal', font_size=17, color=STRUCTURE_COLOR, max_width=2.4)
        ch4_group = VGroup(ch4_label, ch4, ch4_descriptor).arrange(DOWN, buff=0.16)
        nh3_group = VGroup(nh3_label, nh3, nh3_descriptor).arrange(DOWN, buff=0.16)
        comparison = VGroup(ch4_group, nh3_group).arrange(DOWN if portrait else RIGHT, buff=0.56 if portrait else 0.72)
        return comparison
    if kind in ('vsepr_ch4', 'vsepr_nh3'):
        center_symbol = 'C' if kind == 'vsepr_ch4' else 'N'
        center_atom = Circle(radius=0.34, color=CENTRAL_ATOM_COLOR, fill_color=CENTRAL_ATOM_COLOR, fill_opacity=0.22)
        center_label = safe_math(center_symbol, font_size=31, color=SURROUNDING_ATOM_COLOR).move_to(center_atom)
        if kind == 'vsepr_ch4':
            plane_left = LEFT * 1.35 + UP * 0.38
            plane_right = RIGHT * 1.35 + UP * 0.38
            front = RIGHT * 0.88 + DOWN * 1.08
            back = LEFT * 0.88 + DOWN * 1.08
            plane_bonds = VGroup(Line(ORIGIN, plane_left, color=BOND_COLOR), Line(ORIGIN, plane_right, color=BOND_COLOR))
            wedge = Polygon(ORIGIN + DOWN * 0.04, front + LEFT * 0.16, front + RIGHT * 0.16, color=BOND_COLOR, fill_color=BOND_COLOR, fill_opacity=0.78)
            dashed_bond = DashedLine(ORIGIN, back, dash_length=0.13, color=BOND_COLOR)
            atom_positions = [plane_left, plane_right, front, back]
            atom_offsets = [LEFT * 0.26 + UP * 0.12, RIGHT * 0.26 + UP * 0.12, RIGHT * 0.18 + DOWN * 0.20, LEFT * 0.18 + DOWN * 0.20]
            angle_arc = Arc(radius=0.58, start_angle=-2.25, angle=1.36, color=ANGLE_COLOR)
            angle_label = safe_math(r'109.5^\circ', font_size=24, color=ANGLE_COLOR).move_to(DOWN * 0.82)
            lone_pair = VGroup()
        else:
            plane = DOWN * 1.32
            front = RIGHT * 1.08 + UP * 0.18
            back = LEFT * 1.08 + UP * 0.18
            plane_bonds = VGroup(Line(ORIGIN, plane, color=BOND_COLOR))
            wedge = Polygon(ORIGIN + RIGHT * 0.03, front + UP * 0.15, front + DOWN * 0.15, color=BOND_COLOR, fill_color=BOND_COLOR, fill_opacity=0.78)
            dashed_bond = DashedLine(ORIGIN, back, dash_length=0.13, color=BOND_COLOR)
            atom_positions = [plane, front, back]
            atom_offsets = [DOWN * 0.24, RIGHT * 0.24, LEFT * 0.24]
            angle_arc = Arc(radius=0.60, start_angle=-2.98, angle=1.68, color=ANGLE_COLOR)
            angle_label = safe_math(r'107^\circ', font_size=24, color=ANGLE_COLOR).move_to(LEFT * 0.12 + DOWN * 0.73)
            lone_pair = VGroup(Dot(LEFT * 0.10 + UP * 0.58, radius=0.055, color=LONE_PAIR_COLOR), Dot(RIGHT * 0.10 + UP * 0.58, radius=0.055, color=LONE_PAIR_COLOR))
        bonds = VGroup(plane_bonds, wedge, dashed_bond)
        atom_labels = VGroup(center_label)
        placed_labels = [center_label]
        for atom_position, atom_offset in zip(atom_positions, atom_offsets):
            atom_label = safe_math('H', font_size=29, color=SURROUNDING_ATOM_COLOR).move_to(atom_position + atom_offset)
            avoid_overlap(atom_label, placed_labels, min_gap=0.3)
            atom_labels.add(atom_label)
            placed_labels.append(atom_label)
        avoid_overlap(angle_label, placed_labels, min_gap=0.3)
        angle_group = VGroup(angle_arc, angle_label)
        return VGroup(bonds, VGroup(center_atom, atom_labels), lone_pair, angle_group)
    return VGroup()

def animate_visual(scene, kind, visual, duration, stagger=False):
    duration = max(0.08, duration)
    if len(visual) == 0:
        return
    if kind == 'geometry':
        scene.play(Create(visual[0]), Create(visual[1]), FadeIn(visual[2]), run_time=duration)
        return
    if kind == 'vsepr_compare':
        def reveal_molecule(group, portion):
            molecule = group[1]
            scene.play(FadeIn(group[0]), run_time=portion * 0.12)
            scene.play(Create(molecule[0]), GrowFromCenter(molecule[1][0]), run_time=portion * 0.30)
            scene.play(LaggedStart(*[FadeIn(label) for label in molecule[1][1]], lag_ratio=0.14), run_time=portion * 0.24)
            if len(molecule[2]) > 0:
                scene.play(FadeIn(molecule[2]), run_time=portion * 0.10)
            scene.play(FadeIn(molecule[3]), FadeIn(group[2]), run_time=portion * 0.24)
        reveal_molecule(visual[0], duration * 0.48)
        reveal_molecule(visual[1], duration * 0.52)
        return
    if kind in ('vsepr_ch4', 'vsepr_nh3'):
        scene.play(FadeIn(visual[0]), GrowFromCenter(visual[1][0]), LaggedStart(*[FadeIn(label) for label in visual[1][1]], lag_ratio=0.14), run_time=duration * 0.58)
        if len(visual[2]) > 0:
            scene.play(FadeIn(visual[2]), run_time=duration * 0.16)
        # Keep the angle arc and its numeric label in one animation state.
        scene.play(FadeIn(visual[3]), run_time=duration * (0.26 if len(visual[2]) > 0 else 0.42))
        return
    scene.play(FadeIn(visual), run_time=duration)

class DebugScene(Scene):
    def construct(self):
        self.camera.background_color = BLACK

        # --- Beat 1 params ---
        beat1_scale = 1.0
        beat1_gap = 0.3
        beat1_speed = 0.6400
        # --- Beat 1 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=1.5000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat1_heading = fitted_text('CH4 tetrahedral geometry', font_size=24, color=TITLE_COLOR)
        beat1_items = VGroup()
        beat1_equation1 = safe_math('bond angle = 109.5°', font_size=42)
        beat1_items.add(beat1_equation1)
        if len(beat1_items) > 0:
            beat1_items.arrange(DOWN, buff=beat1_gap, aligned_edge=LEFT)
        beat1_visual = make_visual('vsepr_ch4', [], portrait=True)
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
        avoid_overlap(beat1_equation1, beat1_overlap_obstacles, min_gap=0.3)
        beat1_overlap_obstacles.append(beat1_equation1)
        if beat1_diagram.height > config.frame_height * 0.55:
            beat1_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat1_diagram.width > config.frame_width * 0.76:
            beat1_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat1_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat1_heading), run_time=0.3200)
        self.play(FadeIn(beat1_equation1), run_time=0.6400)
        if len(beat1_visual) > 0:
            animate_visual(self, 'vsepr_ch4', beat1_visual, 1.2800, stagger=False)
        else:
            pass
        self.wait(1.2800)
        self.wait(4.0000)
        self.play(FadeOut(VGroup(beat1_heading, beat1_items)), run_time=0.4800)

        # --- Beat 2 params ---
        beat2_scale = 1.0
        beat2_gap = 0.3
        beat2_speed = 0.3200
        # --- Beat 2 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=True
        beat2_heading = fitted_text('CH4 tetrahedral geometry', font_size=24, color=TITLE_COLOR)
        beat2_items = VGroup()
        if len(beat2_items) > 0:
            beat2_items.arrange(DOWN, buff=beat2_gap, aligned_edge=LEFT)
        beat2_visual = make_visual('vsepr_ch4', [], portrait=True)
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
            self.play(ReplacementTransform(beat1_visual, beat2_visual), run_time=1.2800)
        else:
            pass
        self.wait(1.9200)
        self.wait(8.0000)
        self.play(FadeOut(beat2_diagram), run_time=0.4800)

        # --- Beat 3 params ---
        beat3_scale = 1.0
        beat3_gap = 0.3
        beat3_speed = 0.4000
        # --- Beat 3 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat3_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat3_items = VGroup()
        if len(beat3_items) > 0:
            beat3_items.arrange(DOWN, buff=beat3_gap, aligned_edge=LEFT)
        beat3_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat3_content = VGroup(beat3_items, beat3_visual)
        beat3_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat3_diagram = VGroup(beat3_heading, beat3_content).arrange(DOWN, buff=0.38)
        beat3_diagram.scale(beat3_scale)
        beat3_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat3_diagram.width > config.frame_width * 0.76:
            beat3_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat3_diagram.move_to(ORIGIN)
        beat3_overlap_obstacles = [beat3_visual] if len(beat3_visual) > 0 else []
        avoid_overlap(beat3_heading, beat3_overlap_obstacles, min_gap=0.0)
        beat3_overlap_obstacles.append(beat3_heading)
        if beat3_diagram.height > config.frame_height * 0.55:
            beat3_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat3_diagram.width > config.frame_width * 0.76:
            beat3_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat3_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat3_heading), run_time=beat3_speed)
        if len(beat3_visual) > 0:
            animate_visual(self, 'vsepr_nh3', beat3_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(13.0000)
        self.play(FadeOut(VGroup(beat3_heading, beat3_items)), run_time=0.5000)

        # --- Beat 4 params ---
        beat4_scale = 1.0
        beat4_gap = 0.3
        beat4_speed = 0.4000
        # --- Beat 4 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=True
        beat4_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat4_items = VGroup()
        if len(beat4_items) > 0:
            beat4_items.arrange(DOWN, buff=beat4_gap, aligned_edge=LEFT)
        beat4_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat4_content = VGroup(beat4_items, beat4_visual)
        beat4_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat4_diagram = VGroup(beat4_heading, beat4_content).arrange(DOWN, buff=0.38)
        beat4_diagram.scale(beat4_scale)
        beat4_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat4_diagram.width > config.frame_width * 0.76:
            beat4_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat4_diagram.move_to(ORIGIN)
        beat4_overlap_obstacles = [beat4_visual] if len(beat4_visual) > 0 else []
        avoid_overlap(beat4_heading, beat4_overlap_obstacles, min_gap=0.0)
        beat4_overlap_obstacles.append(beat4_heading)
        if beat4_diagram.height > config.frame_height * 0.55:
            beat4_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat4_diagram.width > config.frame_width * 0.76:
            beat4_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat4_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat4_heading), run_time=beat4_speed)
        if len(beat4_visual) > 0:
            self.play(ReplacementTransform(beat3_visual, beat4_visual), run_time=1.6000)
        else:
            pass
        self.wait(2.5000)
        self.wait(18.0000)
        self.play(FadeOut(beat4_diagram), run_time=0.5000)

        # --- Beat 5 params ---
        beat5_scale = 1.0
        beat5_gap = 0.3
        beat5_speed = 0.3200
        # --- Beat 5 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat5_heading = fitted_text('General claim unused electron pairs compress', font_size=24, color=TITLE_COLOR)
        beat5_items = VGroup()
        if len(beat5_items) > 0:
            beat5_items.arrange(DOWN, buff=beat5_gap, aligned_edge=LEFT)
        beat5_visual = make_visual('geometry', [], portrait=True)
        beat5_content = VGroup(beat5_items, beat5_visual)
        beat5_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat5_diagram = VGroup(beat5_heading, beat5_content).arrange(DOWN, buff=0.38)
        beat5_diagram.scale(beat5_scale)
        beat5_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat5_diagram.width > config.frame_width * 0.76:
            beat5_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat5_diagram.move_to(ORIGIN)
        beat5_overlap_obstacles = [beat5_visual] if len(beat5_visual) > 0 else []
        avoid_overlap(beat5_heading, beat5_overlap_obstacles, min_gap=0.0)
        beat5_overlap_obstacles.append(beat5_heading)
        if beat5_diagram.height > config.frame_height * 0.55:
            beat5_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat5_diagram.width > config.frame_width * 0.76:
            beat5_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat5_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat5_heading), run_time=beat5_speed)
        if len(beat5_visual) > 0:
            animate_visual(self, 'geometry', beat5_visual, 1.2800, stagger=False)
        else:
            pass
        self.wait(1.9200)
        self.wait(22.0000)
        self.play(FadeOut(beat5_diagram), run_time=0.4800)

        # --- Beat 6 params ---
        beat6_scale = 1.0
        beat6_gap = 0.3
        beat6_speed = 0.4000
        # --- Beat 6 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat6_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat6_items = VGroup()
        if len(beat6_items) > 0:
            beat6_items.arrange(DOWN, buff=beat6_gap, aligned_edge=LEFT)
        beat6_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat6_content = VGroup(beat6_items, beat6_visual)
        beat6_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat6_diagram = VGroup(beat6_heading, beat6_content).arrange(DOWN, buff=0.38)
        beat6_diagram.scale(beat6_scale)
        beat6_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat6_diagram.width > config.frame_width * 0.76:
            beat6_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat6_diagram.move_to(ORIGIN)
        beat6_overlap_obstacles = [beat6_visual] if len(beat6_visual) > 0 else []
        avoid_overlap(beat6_heading, beat6_overlap_obstacles, min_gap=0.0)
        beat6_overlap_obstacles.append(beat6_heading)
        if beat6_diagram.height > config.frame_height * 0.55:
            beat6_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat6_diagram.width > config.frame_width * 0.76:
            beat6_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat6_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat6_heading), run_time=beat6_speed)
        if len(beat6_visual) > 0:
            animate_visual(self, 'vsepr_nh3', beat6_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(27.0000)
        self.play(FadeOut(beat6_diagram), run_time=0.5000)

        # --- Beat 7 params ---
        beat7_scale = 1.0
        beat7_gap = 0.3
        beat7_speed = 0.8000
        # --- Beat 7 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=1.7700 stepwise_derivation=True cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat7_heading = fitted_text('CH4 and NH3 compared', font_size=24, color=TITLE_COLOR)
        beat7_items = VGroup()
        beat7_equation1 = safe_math('4 + 0 = 4', font_size=42)
        beat7_items.add(beat7_equation1)
        beat7_equation2 = safe_math('3 + 1 = 4', font_size=42)
        if len(beat7_items) > 0:
            beat7_items.arrange(DOWN, buff=beat7_gap, aligned_edge=LEFT)
        beat7_visual = make_visual('vsepr_compare', [], portrait=True)
        beat7_content = VGroup(beat7_items, beat7_visual)
        beat7_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat7_diagram = VGroup(beat7_heading, beat7_content).arrange(DOWN, buff=0.38)
        beat7_diagram.scale(beat7_scale)
        beat7_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat7_diagram.width > config.frame_width * 0.76:
            beat7_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat7_diagram.move_to(ORIGIN)
        beat7_overlap_obstacles = [beat7_visual] if len(beat7_visual) > 0 else []
        avoid_overlap(beat7_heading, beat7_overlap_obstacles, min_gap=0.0)
        beat7_overlap_obstacles.append(beat7_heading)
        avoid_overlap(beat7_equation1, beat7_overlap_obstacles, min_gap=0.3)
        beat7_overlap_obstacles.append(beat7_equation1)
        avoid_overlap(beat7_equation2, beat7_overlap_obstacles, min_gap=0.3)
        beat7_overlap_obstacles.append(beat7_equation2)
        if beat7_diagram.height > config.frame_height * 0.55:
            beat7_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat7_diagram.width > config.frame_width * 0.76:
            beat7_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat7_diagram.move_to(ORIGIN)
        beat7_equation2.move_to(beat7_equation1)
        if beat7_equation2.width > config.frame_width * 0.76:
            beat7_equation2.scale_to_fit_width(config.frame_width * 0.76)
        self.play(FadeIn(beat7_heading), run_time=0.4000)
        self.play(FadeIn(beat7_equation1), run_time=0.8000)
        if len(beat7_visual) > 0:
            animate_visual(self, 'vsepr_compare', beat7_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(0.2500)
        self.play(FadeOut(beat7_equation1), run_time=0.3360)
        self.play(FadeIn(beat7_equation2), run_time=0.4640)
        self.wait(0.6500)
        self.wait(32.0000)
        self.play(FadeOut(VGroup(beat7_diagram, beat7_equation2)), run_time=0.5000)

        # --- Beat 8 params ---
        beat8_scale = 1.0
        beat8_gap = 0.3
        beat8_speed = 0.4000
        # --- Beat 8 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat8_heading = fitted_text('Same count different visible geometry', font_size=24, color=TITLE_COLOR)
        beat8_items = VGroup()
        if len(beat8_items) > 0:
            beat8_items.arrange(DOWN, buff=beat8_gap, aligned_edge=LEFT)
        beat8_visual = make_visual('geometry', [], portrait=True)
        beat8_content = VGroup(beat8_items, beat8_visual)
        beat8_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat8_diagram = VGroup(beat8_heading, beat8_content).arrange(DOWN, buff=0.38)
        beat8_diagram.scale(beat8_scale)
        beat8_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat8_diagram.width > config.frame_width * 0.76:
            beat8_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat8_diagram.move_to(ORIGIN)
        beat8_overlap_obstacles = [beat8_visual] if len(beat8_visual) > 0 else []
        avoid_overlap(beat8_heading, beat8_overlap_obstacles, min_gap=0.0)
        beat8_overlap_obstacles.append(beat8_heading)
        if beat8_diagram.height > config.frame_height * 0.55:
            beat8_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat8_diagram.width > config.frame_width * 0.76:
            beat8_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat8_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat8_heading), run_time=beat8_speed)
        if len(beat8_visual) > 0:
            animate_visual(self, 'geometry', beat8_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(37.0000)
        self.play(FadeOut(beat8_diagram), run_time=0.5000)

        # --- Beat 9 params ---
        beat9_scale = 1.0
        beat9_gap = 0.3
        beat9_speed = 0.4000
        # --- Beat 9 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat9_heading = fitted_text('Edge case same four groups does', font_size=24, color=TITLE_COLOR)
        beat9_items = VGroup()
        if len(beat9_items) > 0:
            beat9_items.arrange(DOWN, buff=beat9_gap, aligned_edge=LEFT)
        beat9_visual = make_visual('geometry', [], portrait=True)
        beat9_content = VGroup(beat9_items, beat9_visual)
        beat9_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat9_diagram = VGroup(beat9_heading, beat9_content).arrange(DOWN, buff=0.38)
        beat9_diagram.scale(beat9_scale)
        beat9_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat9_diagram.width > config.frame_width * 0.76:
            beat9_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat9_diagram.move_to(ORIGIN)
        beat9_overlap_obstacles = [beat9_visual] if len(beat9_visual) > 0 else []
        avoid_overlap(beat9_heading, beat9_overlap_obstacles, min_gap=0.0)
        beat9_overlap_obstacles.append(beat9_heading)
        if beat9_diagram.height > config.frame_height * 0.55:
            beat9_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat9_diagram.width > config.frame_width * 0.76:
            beat9_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat9_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat9_heading), run_time=beat9_speed)
        if len(beat9_visual) > 0:
            animate_visual(self, 'geometry', beat9_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(42.0000)
        self.play(FadeOut(beat9_diagram), run_time=0.5000)

        # --- Beat 10 params ---
        beat10_scale = 1.0
        beat10_gap = 0.3
        beat10_speed = 0.4000
        # --- Beat 10 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat10_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat10_items = VGroup()
        if len(beat10_items) > 0:
            beat10_items.arrange(DOWN, buff=beat10_gap, aligned_edge=LEFT)
        beat10_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat10_content = VGroup(beat10_items, beat10_visual)
        beat10_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat10_diagram = VGroup(beat10_heading, beat10_content).arrange(DOWN, buff=0.38)
        beat10_diagram.scale(beat10_scale)
        beat10_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat10_diagram.width > config.frame_width * 0.76:
            beat10_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat10_diagram.move_to(ORIGIN)
        beat10_overlap_obstacles = [beat10_visual] if len(beat10_visual) > 0 else []
        avoid_overlap(beat10_heading, beat10_overlap_obstacles, min_gap=0.0)
        beat10_overlap_obstacles.append(beat10_heading)
        if beat10_diagram.height > config.frame_height * 0.55:
            beat10_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat10_diagram.width > config.frame_width * 0.76:
            beat10_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat10_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat10_heading), run_time=beat10_speed)
        if len(beat10_visual) > 0:
            animate_visual(self, 'vsepr_nh3', beat10_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(47.0000)
        self.play(FadeOut(beat10_diagram), run_time=0.5000)

        # --- Beat 11 params ---
        beat11_scale = 1.0
        beat11_gap = 0.3
        beat11_speed = 0.4000
        # --- Beat 11 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat11_heading = fitted_text('CH4 tetrahedral geometry', font_size=24, color=TITLE_COLOR)
        beat11_items = VGroup()
        if len(beat11_items) > 0:
            beat11_items.arrange(DOWN, buff=beat11_gap, aligned_edge=LEFT)
        beat11_visual = make_visual('vsepr_ch4', [], portrait=True)
        beat11_content = VGroup(beat11_items, beat11_visual)
        beat11_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat11_diagram = VGroup(beat11_heading, beat11_content).arrange(DOWN, buff=0.38)
        beat11_diagram.scale(beat11_scale)
        beat11_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat11_diagram.width > config.frame_width * 0.76:
            beat11_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat11_diagram.move_to(ORIGIN)
        beat11_overlap_obstacles = [beat11_visual] if len(beat11_visual) > 0 else []
        avoid_overlap(beat11_heading, beat11_overlap_obstacles, min_gap=0.0)
        beat11_overlap_obstacles.append(beat11_heading)
        if beat11_diagram.height > config.frame_height * 0.55:
            beat11_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat11_diagram.width > config.frame_width * 0.76:
            beat11_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat11_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat11_heading), run_time=beat11_speed)
        if len(beat11_visual) > 0:
            animate_visual(self, 'vsepr_ch4', beat11_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(52.0000)
        self.play(FadeOut(beat11_diagram), run_time=0.5000)

        # --- Beat 12 params ---
        beat12_scale = 1.0
        beat12_gap = 0.3
        beat12_speed = 0.4000
        # --- Beat 12 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat12_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat12_items = VGroup()
        if len(beat12_items) > 0:
            beat12_items.arrange(DOWN, buff=beat12_gap, aligned_edge=LEFT)
        beat12_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat12_content = VGroup(beat12_items, beat12_visual)
        beat12_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat12_diagram = VGroup(beat12_heading, beat12_content).arrange(DOWN, buff=0.38)
        beat12_diagram.scale(beat12_scale)
        beat12_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat12_diagram.width > config.frame_width * 0.76:
            beat12_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat12_diagram.move_to(ORIGIN)
        beat12_overlap_obstacles = [beat12_visual] if len(beat12_visual) > 0 else []
        avoid_overlap(beat12_heading, beat12_overlap_obstacles, min_gap=0.0)
        beat12_overlap_obstacles.append(beat12_heading)
        if beat12_diagram.height > config.frame_height * 0.55:
            beat12_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat12_diagram.width > config.frame_width * 0.76:
            beat12_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat12_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat12_heading), run_time=beat12_speed)
        if len(beat12_visual) > 0:
            animate_visual(self, 'vsepr_nh3', beat12_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.wait(57.0000)
        self.play(FadeOut(VGroup(beat12_heading, beat12_items)), run_time=0.5000)

        # --- Beat 13 params ---
        beat13_scale = 1.0
        beat13_gap = 0.3
        beat13_speed = 0.4000
        # --- Beat 13 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=True
        beat13_heading = fitted_text('NH3 trigonal pyramidal geometry', font_size=24, color=TITLE_COLOR)
        beat13_items = VGroup()
        if len(beat13_items) > 0:
            beat13_items.arrange(DOWN, buff=beat13_gap, aligned_edge=LEFT)
        beat13_visual = make_visual('vsepr_nh3', [], portrait=True)
        beat13_content = VGroup(beat13_items, beat13_visual)
        beat13_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat13_diagram = VGroup(beat13_heading, beat13_content).arrange(DOWN, buff=0.38)
        beat13_diagram.scale(beat13_scale)
        beat13_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat13_diagram.width > config.frame_width * 0.76:
            beat13_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat13_diagram.move_to(ORIGIN)
        beat13_overlap_obstacles = [beat13_visual] if len(beat13_visual) > 0 else []
        avoid_overlap(beat13_heading, beat13_overlap_obstacles, min_gap=0.0)
        beat13_overlap_obstacles.append(beat13_heading)
        if beat13_diagram.height > config.frame_height * 0.55:
            beat13_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat13_diagram.width > config.frame_width * 0.76:
            beat13_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat13_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat13_heading), run_time=beat13_speed)
        if len(beat13_visual) > 0:
            self.play(ReplacementTransform(beat12_visual, beat13_visual), run_time=1.6000)
        else:
            pass
        self.wait(2.5000)
        self.wait(62.0000)
        self.play(FadeOut(beat13_diagram), run_time=0.5000)

        # --- Beat 14 params ---
        beat14_scale = 1.0
        beat14_gap = 0.3
        beat14_speed = 0.4000
        # --- Beat 14 ---
        # text_reveal=fade min_post_reveal_hold=0.6500 required_write_time=0.0000 stepwise_derivation=False cross_beat_substitution=False cross_beat_equation_transition=False same_equation_continuation=False matching_transform=False visual_handoff_from_previous=False
        beat14_heading = fitted_text('Result PCl3 angle is smaller than', font_size=24, color=TITLE_COLOR)
        beat14_items = VGroup()
        if len(beat14_items) > 0:
            beat14_items.arrange(DOWN, buff=beat14_gap, aligned_edge=LEFT)
        beat14_visual = make_visual('geometry', [], portrait=True)
        beat14_content = VGroup(beat14_items, beat14_visual)
        beat14_content.arrange(DOWN if True else RIGHT, buff=0.45)
        beat14_diagram = VGroup(beat14_heading, beat14_content).arrange(DOWN, buff=0.38)
        beat14_diagram.scale(beat14_scale)
        beat14_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat14_diagram.width > config.frame_width * 0.76:
            beat14_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat14_diagram.move_to(ORIGIN)
        beat14_overlap_obstacles = [beat14_visual] if len(beat14_visual) > 0 else []
        avoid_overlap(beat14_heading, beat14_overlap_obstacles, min_gap=0.0)
        beat14_overlap_obstacles.append(beat14_heading)
        if beat14_diagram.height > config.frame_height * 0.55:
            beat14_diagram.scale_to_fit_height(config.frame_height * 0.55)
        if beat14_diagram.width > config.frame_width * 0.76:
            beat14_diagram.scale_to_fit_width(config.frame_width * 0.76)
        beat14_diagram.move_to(ORIGIN)
        self.play(FadeIn(beat14_heading), run_time=beat14_speed)
        if len(beat14_visual) > 0:
            animate_visual(self, 'geometry', beat14_visual, 1.6000, stagger=False)
        else:
            pass
        self.wait(2.5000)
        self.play(FadeOut(beat14_diagram), run_time=0.5000)
