from __future__ import annotations

from manim import *
import numpy as np


class VivacityCharacter(VGroup):
    """
    Reusable mascot for Vivacity scenes.
    Original geometric design distinct from Pi Creature.
    Built from simple shapes for easy manipulation and expression changes.
    """

    # Available expressions
    EXPRESSIONS = ["neutral", "thinking", "excited", "confused", "celebrating"]

    def __init__(self, expression: str = "neutral", scale: float = 0.8, **kwargs):
        super().__init__(**kwargs)
        self.scale_factor = scale
        self._build_base_shape()
        self.set_expression(expression)

    def _build_base_shape(self):
        """Construct the original geometric mascot using simple shapes."""
        # Body proportions: head 1:1, torso 1.6:1, limbs 0.4:1

        # Head - slightly flattened circle for uniqueness
        head = Ellipse(
            width=0.6,
            height=0.5,
            color=WHITE,
            fill_opacity=0.9
        )
        head.set_fill("#4FC3F7", opacity=0.9)  # Light blue, distinct from equation colors

        # torso - rounded rectangle with subtle curve
        torso = RoundedRectangle(
            width=0.5,
            height=0.8,
            corner_radius=0.08,
            color=WHITE,
            fill_opacity=0.9
        )
        torso.set_fill("#81C784", opacity=0.8)  # Light green
        torso.next_to(head, DOWN, buff=0.05)

        # Arms - tapered rectangles for friendlier look
        left_upper_arm = Rectangle(
            width=0.08,
            height=0.3,
            color=WHITE,
            fill_opacity=0.9
        )
        left_upper_arm.set_fill("#81C784", opacity=0.8)
        left_upper_arm.rotate(30 * DEGREES, about_point=LEFT * 0.25 + UP * 0.1)
        left_upper_arm.next_to(torso.get_left(), LEFT, buff=0.02)

        left_forearm = Rectangle(
            width=0.06,
            height=0.25,
            color=WHITE,
            fill_opacity=0.9
        )
        left_forearm.set_fill("#81C784", opacity=0.8)
        left_forearm.rotate(-20 * DEGREES, about_point=LEFT * 0.05 + DOWN * 0.1)
        left_forearm.next_to(left_upper_arm, DOWN, buff=0.02)

        right_upper_arm = Rectangle(
            width=0.08,
            height=0.3,
            color=WHITE,
            fill_opacity=0.9
        )
        right_upper_arm.set_fill("#81C784", opacity=0.8)
        right_upper_arm.rotate(-30 * DEGREES, about_point=RIGHT * 0.25 + UP * 0.1)
        right_upper_arm.next_to(torso.get_right(), RIGHT, buff=0.02)

        right_forearm = Rectangle(
            width=0.06,
            height=0.25,
            color=WHITE,
            fill_opacity=0.9
        )
        right_forearm.set_fill("#81C784", opacity=0.8)
        right_forearm.rotate(20 * DEGREES, about_point=RIGHT * 0.05 + DOWN * 0.1)

        # Legs - simple tapered Design
        left_thigh = Rectangle(
            width=0.07,
            height=0.3,
            color=WHITE,
            fill_opacity=0.9
        )
        left_thigh.set_fill("#81C784", opacity=0.8)
        left_thigh.next_to(torso.get_bottom(), DOWN, buff=0.02)

        left_shin = Rectangle(
            width=0.05,
            height=0.25,
            color=WHITE,
            fill_opacity=0.9
        )
        left_shin.set_fill("#81C784", opacity=0.8)
        left_shin.next_to(left_thigh, DOWN, buff=0.02)

        right_thigh = Rectangle(
            width=0.07,
            height=0.3,
            color=WHITE,
            fill_opacity=0.9
        )
        right_thigh.set_fill("#81C784", opacity=0.8)
        right_thigh.next_to(torso.get_bottom(), DOWN, buff=0.02).shift(RIGHT * 0.01)

        right_shin = Rectangle(
            width=0.05,
            height=0.25,
            color=WHITE,
            fill_opacity=0.9
        )
        right_shin.set_fill("#81C784", opacity=0.8)
        right_shin.next_to(right_thigh, DOWN, buff=0.02)

        # Feet - small triangles
        left_foot = Polygon(
            left_shin.get_left() + DOWN * 0.02,
            left_shin.get_right() + DOWN * 0.02,
            left_shin.get_right() + DOWN * 0.05,
            left_shin.get_left() + DOWN * 0.05,
            color=WHITE,
            fill_opacity=0.9
        )
        left_foot.set_fill("#66BB6A", opacity=0.8)

        right_foot = Polygon(
            right_shin.get_left() + DOWN * 0.02,
            right_shin.get_right() + DOWN * 0.02,
            right_shin.get_right() + DOWN * 0.05,
            right_shin.get_left() + DOWN * 0.05,
            color=WHITE,
            fill_opacity=0.9
        )
        right_foot.set_fill("#66BB6A", opacity=0.8)

        # Antennae (distinctive feature)
        left_antenna = Line(
            start=LEFT * 0.15 + UP * 0.25,
            end=LEFT * 0.25 + UP * 0.5,
            color=WHITE,
            stroke_width=3
        )
        left_antenna_tip = Dot(radius=0.03, color=YELLOW)
        left_antenna_tip.move_to(left_antenna.get_end())

        right_antenna = Line(
            start=RIGHT * 0.15 + UP * 0.25,
            end=RIGHT * 0.25 + UP * 0.5,
            color=WHITE,
            stroke_width=3
        )
        right_antenna_tip = Dot(radius=0.03, color=YELLOW)
        right_antenna_tip.move_to(right_antenna.get_end())

        # Store parts for reference
        self.head = head
        self.torso = torso
        self.left_upper_arm = left_upper_arm
        self.left_forearm = left_forearm
        self.right_upper_arm = right_upper_arm
        self.right_forearm = right_forearm
        self.left_thigh = left_thigh
        self.left_shin = left_shin
        self.right_thigh = right_thigh
        self.right_shin = right_shin
        self.left_foot = left_foot
        self.right_foot = right_foot
        self.left_antenna = left_antenna
        self.left_antenna_tip = left_antenna_tip
        self.right_antenna = right_antenna
        self.right_antenna_tip = right_antenna_tip

        # Face features (will be updated by set_expression)
        self.eyes = VGroup()
        self.mouth = VGroup()
        self.eyebrows = VGroup()

        # Add all parts to the group
        self.add(
            head, torso,
            left_upper_arm, left_forearm,
            right_upper_arm, right_forearm,
            left_thigh, left_shin, right_thigh, right_shin,
            left_foot, right_foot,
            left_antenna, left_antenna_tip,
            right_antenna, right_antenna_tip,
            self.eyes, self.mouth, self.eyebrows
        )

        # Scale the entire character
        self.scale(self.scale_factor)

    def _build_features(self, expression: str):
        """Create facial features for the given expression."""
        # Clear existing features
        self.eyes.submobjects = []
        self.mouth.submobjects = []
        self.eyebrows.submobjects = []

        # Position reference points
        face_center = self.head.get_center()
        eye_level = face_center + UP * 0.05
        mouth_level = face_center + DOWN * 0.1
        brow_level = face_center + UP * 0.15

        # Eyes - always two elliptical shapes
        left_eye_base = Ellipse(
            width=0.12,
            height=0.08,
            color=BLACK,
            fill_opacity=1
        ).shift(LEFT * 0.15 + UP * 0.05)

        right_eye_base = Ellipse(
            width=0.12,
            height=0.08,
            color=BLACK,
            fill_opacity=1
        ).shift(RIGHT * 0.15 + UP * 0.05)

        if expression == "neutral":
            # Neutral: half-closed eyes, straight mouth
            left_eye = Arc(
                start_angle=0,
                angle=PI,
                radius=0.06,
                color=BLACK,
                stroke_width=2
            ).shift(LEFT * 0.15 + UP * 0.05)

            right_eye = Arc(
                start_angle=0,
                angle=PI,
                radius=0.06,
                color=BLACK,
                stroke_width=2
            ).shift(RIGHT * 0.15 + UP * 0.05)

            self.eyes = VGroup(left_eye, right_eye)

            # Straight mouth
            mouth = Line(
                start=LEFT * 0.1,
                end=RIGHT * 0.1,
                color=BLACK,
                stroke_width=3
            ).shift(DOWN * 0.1)
            self.mouth.add(mouth)

            # Neutral eyebrows
            left_brow = Line(
                start=LEFT * 0.2 + UP * 0.18,
                end=LEFT * 0.05 + UP * 0.18,
                color=BLACK,
                stroke_width=2
            )
            right_brow = Line(
                start=RIGHT * 0.05 + UP * 0.18,
                end=RIGHT * 0.2 + UP * 0.18,
                color=BLACK,
                stroke_width=2
            )
            self.eyebrows = VGroup(left_brow, right_brow)

        elif expression == "thinking":
            # Thinking: looking up, thoughtful expression
            left_eye = Circle(
                radius=0.06,
                color=BLACK,
                fill_opacity=1
            ).shift(LEFT * 0.15 + UP * 0.1)

            right_eye = Circle(
                radius=0.06,
                color=BLACK,
                fill_opacity=1
            ).shift(RIGHT * 0.15 + UP * 0.1)

            self.eyes = VGroup(left_eye, right_eye)

            # Small thinking curve (like a tiny thought bubble indicator)
            thought_indicator = Dot(radius=0.04, color=YELLOW)
            thought_indicator.shift(UP * 0.25 + RIGHT * 0.2)
            self.eyes.add(thought_indicator)

            # Flat, thoughtful mouth
            mouth = Line(
                start=LEFT * 0.08,
                end=RIGHT * 0.08,
                color=BLACK,
                stroke_width=2
            ).shift(DOWN * 0.12)
            self.mouth.add(mouth)

            # Raised, curved eyebrows
            left_brow = Arc(
                start_angle=30*DEGREES,
                angle=120*DEGREES,
                radius=0.08,
                color=BLACK,
                stroke_width=2
            ).shift(LEFT * 0.1 + UP * 0.2)

            right_brow = Arc(
                start_angle=60*DEGREES,
                angle=120*DEGREES,
                radius=0.08,
                color=BLACK,
                stroke_width=2
            ).shift(RIGHT * 0.1 + UP * 0.2)
            self.eyebrows = VGroup(left_brow, right_brow)

        elif expression == "excited":
            # Excited: wide eyes, big smile
            left_eye = Circle(
                radius=0.08,
                color=BLACK,
                fill_opacity=1
            ).shift(LEFT * 0.12 + UP * 0.02)

            right_eye = Circle(
                radius=0.08,
                color=BLACK,
                fill_opacity=1
            ).shift(RIGHT * 0.12 + UP * 0.02)

            self.eyes = VGroup(left_eye, right_eye)

            # Wide smile
            mouth = Arc(
                start_angle=0,
                angle=PI,
                radius=0.18,
                color=BLACK,
                stroke_width=3
            ).shift(DOWN * 0.05)
            self.mouth.add(mouth)

            # Raised, excited eyebrows
            left_brow = Arc(
                start_angle=20*DEGREES,
                angle=140*DEGREES,
                radius=0.09,
                color=BLACK,
                stroke_width=2
            ).shift(LEFT * 0.1 + UP * 0.22)

            right_brow = Arc(
                start_angle=-20*DEGREES,
                angle=140*DEGREES,
                radius=0.09,
                color=BLACK,
                stroke_width=2
            ).shift(RIGHT * 0.1 + UP * 0.22)
            self.eyebrows = VGroup(left_brow, right_brow)

        elif expression == "confused":
            # Confused: asymmetrical eyes, wavy mouth
            left_eye = Ellipse(
                width=0.14,
                height=0.07,
                color=BLACK,
                fill_opacity=1
            ).shift(LEFT * 0.18 + UP * 0.06).rotate(15*DEGREES)

            right_eye = Ellipse(
                width=0.1,
                height=0.06,
                color=BLACK,
                fill_opacity=1
            ).shift(RIGHT * 0.12 + UP * 0.04).rotate(-10*DEGREES)

            self.eyes = VGroup(left_eye, right_eye)

            # Wavy, confused mouth
            mouth = VMobject()
            points = [
                LEFT * 0.12 + DOWN * 0.08,
                LEFT * 0.06 + DOWN * 0.04,
                ORIGIN + DOWN * 0.06,
                RIGHT * 0.06 + DOWN * 0.1,
                RIGHT * 0.12 + DOWN * 0.08
            ]
            mouth.set_points_smoothly(points)
            mouth.set_color(BLACK)
            mouth.set_stroke(width=2)
            self.mouth.add(mouth)

            # Confused eyebrows - one up, one down
            left_brow = Line(
                start=LEFT * 0.22 + UP * 0.22,
                end=LEFT * 0.08 + UP * 0.18,
                color=BLACK,
                stroke_width=2
            )
            right_brow = Line(
                start=RIGHT * 0.08 + UP * 0.12,
                end=RIGHT * 0.22 + UP * 0.16,
                color=BLACK,
                stroke_width=2
            )
            self.eyebrows = VGroup(left_brow, right_brow)

        elif expression == "celebrating":
            # Celebrating: star eyes, open mouth smile
            # Star-like eyes (simplified as polygons)
            left_eye = RegularPolygon(
                n=5,
                radius=0.07,
                color=YELLOW,
                fill_opacity=1
            ).shift(LEFT * 0.12 + UP * 0.02)

            right_eye = RegularPolygon(
                n=5,
                radius=0.07,
                color=YELLOW,
                fill_opacity=1
            ).shift(RIGHT * 0.12 + UP * 0.02)

            self.eyes = VGroup(left_eye, right_eye)

            # Big open smile
            mouth = Arc(
                start_angle=0,
                angle=PI,
                radius=0.22,
                color=BLACK,
                stroke_width=3
            ).shift(DOWN * 0.1)
            self.mouth.add(mouth)

            # Raised, curved eyebrows
            left_brow = Arc(
                start_angle=10*DEGREES,
                angle=160*DEGREES,
                radius=0.1,
                color=BLACK,
                stroke_width=2
            ).shift(LEFT * 0.12 + UP * 0.25)

            right_brow = Arc(
                start_angle=-10*DEGREES,
                angle=160*DEGREES,
                radius=0.1,
                color=BLACK,
                stroke_width=2
            ).shift(RIGHT * 0.12 + UP * 0.25)
            self.eyebrows = VGroup(left_brow, right_brow)

        # Position features relative to face
        self.eyes.move_to(eye_level)
        self.mouth.move_to(mouth_level)
        self.eyebrows.move_to(brow_level)

    def set_expression(self, expression: str):
        """Set the character's facial expression."""
        assert expression in self.EXPRESSIONS, f"Unknown expression: {expression}"
        self._build_features(expression)

    def react_to(self, event: str):
        """Map pedagogical events to expressions."""
        mapping = {
            "question_posed": "thinking",
            "recall_checkpoint": "thinking",
            "correct_answer": "celebrating",
            "incorrect_answer": "confused",
            "explanation_start": "excited",
            "edge_case_reveal": "confused",
            "resolution": "excited",
            "encouragement": "excited",
            "praise": "celebrating"
        }
        expr = mapping.get(event, "neutral")
        self.set_expression(expr)

    def blink(self):
        """Create a blinking animation."""
        # Simple blink: squint eyes then reopen
        original_eyes = self.eyes.copy()

        # Squinted eyes
        squint_left = Line(
            start=LEFT * 0.18 + UP * 0.05,
            end=LEFT * 0.12 + UP * 0.05,
            color=BLACK,
            stroke_width=3
        )
        squint_right = Line(
            start=RIGHT * 0.12 + UP * 0.05,
            end=RIGHT * 0.18 + UP * 0.05,
            color=BLACK,
            stroke_width=3
        )
        squint_eyes = VGroup(squint_left, squint_right)
        squint_eyes.move_to(self.eyes.get_center())

        animation = AnimationGroup(
            Transform(self.eyes, squint_eyes, run_time=0.1),
            Transform(self.eyes, original_eyes, run_time=0.1),
            lag_ratio=0
        )
        return animation

# For testing when run directly
if __name__ == "__main__":
    from manim import config, tempconfig

    class TestCharacter(Scene):
        def construct(self):
            char = VivianCharacter()  # Fixed typo in class name reference
            self.add(char)
            self.wait(1)

    with tempconfig({"preview": True, "quality": "low_quality"}):
        scene = TestCharacter()
        scene.render()