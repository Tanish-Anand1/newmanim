from __future__ import annotations

from manim import *
from vivacity_base_scene import VivacityScene

class VivacityCharacter(VGroup):
    """
    Reusable mascot for Vivacity scenes.
    Built from simple geometric shapes (circles, lines) to avoid
    resemblance to the Pi Creature.
    """

    # Available expressions
    EXPRESSIONS = ["neutral", "thinking", "excited", "confused", "celebrating"]

    def __init__(self, expression: str = "neutral", scale: float = 0.8, **kwargs):
        super().__init__(**kwargs)
        self.scale_factor = scale
        self._build_base_shape()
        self.set_expression(expression)

    def _build_base_shape(self):
        """Construct the original geometric mascot."""
        # Head
        head = Circle(radius=0.5, color=WHITE, fill_opacity=0.9)
        head.set_fill(BLUE_E, opacity=0.8)

        # Body (simple rounded rectangle)
        body = RoundedRectangle(
            width=0.6,
            height=0.8,
            corner_radius=0.1,
            color=WHITE,
            fill_opacity=0.9,
        )
        body.set_fill(GREEN_E, opacity=0.7)
        body.next_to(head, DOWN, buff=0.1)

        # Arms (simple lines)
        left_arm = Line(
            start=body.get_left() + UP * 0.2,
            end=body.get_left() + LEFT * 0.3 + UP * 0.1,
            color=WHITE,
            stroke_width=4,
        )
        right_arm = Line(
            start=body.get_right() + UP * 0.2,
            end=body.get_right() + RIGHT * 0.3 + UP * 0.1,
            color=WHITE,
            stroke_width=4,
        )

        # Legs
        left_leg = Line(
            start=body.get_bottom() + DOWN * 0.05,
            end=body.get_bottom() + DOWN * 0.4 + LEFT * 0.1,
            color=WHITE,
            stroke_width=4,
        )
        right_leg = Line(
            start=body.get_bottom() + DOWN * 0.05,
            end=body.get_bottom() + DOWN * 0.4 + RIGHT * 0.1,
            color=WHITE,
            stroke_width=4,
        )

        # Placeholder for facial features (will be replaced by set_expression)
        self.eyes = VGroup()
        self.mouth = VGroup()

        # Add all parts
        self.add(head, body, left_arm, right_arm, left_leg, right_leg)
        # Store parts for reference
        self.head = head
        self.body = body
        self.left_arm = left_arm
        self.right_arm = right_arm
        self.left_leg = left_leg
        self.right_leg = right_leg

        # Facial features will be added in set_expression
        self.eyes = VGroup()
        self.mouth = VGroup()
        self.add(self.eyes, self.mouth)

    def _build_features(self, expression: str):
        """Create eyes and mouth for the given expression."""
        # Clear existing features
        self.eyes.submobjects = []
        self.mouth.submobjects = []

        # Eyes: two circles
        left_eye = Circle(radius=0.07, color=BLACK, fill_opacity=1).shift(LEFT * 0.15 + UP * 0.05)
        right_eye = Circle(radius=0.07, color=BLACK, fill_opacity=1).shift(RIGHT * 0.15 + UP * 0.05)
        self.eyes.add(left_eye, right_eye)

        if expression == "neutral":
            # Simple straight line mouth
            mouth = Line(
                start=LEFT * 0.1,
                end=RIGHT * 0.1,
                color=BLACK,
                stroke_width=3,
            ).shift(DOWN * 0.1)
            self.mouth.add(mouth)

        elif expression == "thinking":
            # Eyes looking up (small arcs)
            left_eye = Arc(
                start_angle=0,
                angle=PI,
                radius=0.07,
                color=BLACK,
                stroke_width=2,
            ).shift(LEFT * 0.15 + UP * 0.05)
            right_eye = Arc(
                start_angle=0,
                angle=PI,
                radius=0.07,
                color=BLACK,
                stroke_width=2,
            ).shift(RIGHT * 0.15 + UP * 0.05)
            self.eyes.submobjects = [left_eye, right_eye]
            # Thinking: a small dot above head
            thought = Dot(radius=0.05, color=YELLOW).shift(UP * 0.3 + RIGHT * 0.2)
            self.eyes.add(thought)  # reuse eyes container for simplicity

        elif expression == "excited":
            # Eyes as stars (simple star shape approximated)
            from functools import reduce
            def star_points(n, r1, r2):
                pts = []
                for i in range(2 * n):
                    r = r1 if i % 2 == 0 else r2
                    angle = i * PI / n
                    pts.append([r * np.cos(angle), r * np.sin(angle), 0])
                return pts
            star1 = Polygon(*star_points(5, 0.08, 0.04), color=YELLOW, fill_opacity=1).shift(LEFT * 0.15 + UP * 0.05)
            star2 = Polygon(*star_points(5, 0.08, 0.04), color=YELLOW, fill_opacity=1).shift(RIGHT * 0.15 + UP * 0.05)
            self.eyes = VGroup(star1, star2)
            # Mouth: wide smile
            mouth = Arc(
                start_angle=0,
                angle=PI,
                radius=0.15,
                color=BLACK,
                stroke_width=3,
            ).shift(DOWN * 0.05)
            self.mouth.add(mouth)

        elif expression == "confused":
            # Eyes as ellipses tilted
            left_eye = Ellipse(width=0.1, height=0.06, color=BLACK, fill_opacity=1).shift(LEFT * 0.15 + UP * 0.05).rotate(30 * DEGREES)
            right_eye = Ellipse(width=0.1, height=0.06, color=BLACK, fill_opacity=1).shift(RIGHT * 0.15 + UP * 0.05).rotate(-30 * DEGREES)
            self.eyes = VGroup(left_eye, right_eye)
            # Mouth: flat line
            mouth = Line(
                start=LEFT * 0.1,
                end=RIGHT * 0.1,
                color=BLACK,
                stroke_width=3,
            ).shift(DOWN * 0.15)
            self.mouth.add(mouth)

        elif expression == "celebrating":
            # Eyes: simple circles
            left_eye = Circle(radius=0.07, color=BLACK, fill_opacity=1).shift(LEFT * 0.15 + UP * 0.05)
            right_eye = Circle(radius=0.07, color=BLACK, fill_opacity=1).shift(RIGHT * 0.15 + UP * 0.05)
            self.eyes = VGroup(left_eye, right_eye)
            # Mouth: big smile with teeth
            mouth = Arc(
                start_angle=0,
                angle=PI,
                radius=0.2,
                color=BLACK,
                stroke_width=3,
            ).shift(DOWN * 0.1)
            # Add two small lines for teeth
            tooth1 = Line(
                start=LEFT * 0.05 + DOWN * 0.1,
                end=LEFT * 0.05 + DOWN * 0.15,
                color=WHITE,
                stroke_width=2,
            )
            tooth2 = Line(
                start=RIGHT * 0.05 + DOWN * 0.1,
                end=RIGHT * 0.05 + DOWN * 0.15,
                color=WHITE,
                stroke_width=2,
            )
            self.mouth = VGroup(mouth, tooth1, tooth2)

        else:
            # fallback neutral
            self._build_features("neutral")

        # Ensure features are correctly positioned relative to head
        self.eyes.move_to(self.head.get_center())
        self.mouth.move_to(self.head.get_center() + DOWN * 0.1)

    def set_expression(self, expression: str):
        """Set the character's facial expression."""
        assert expression in self.expressions, f"Unknown expression: {expression}"
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
        }
        expr = mapping.get(event, "neutral")
        self.set_expression(expr)

# Ensure the class can be imported standalone
if __name__ == "__main__":
    # Quick test when run directly
    from manim import config
    config.media_width = "75%"
    config.media_height="40%"
    config.pixel_width=800
    config.pixel_height=450
    scene = Scene()
    char = VivacityExpression("neutral")
    scene.add(char)
    scene.render()