from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import (
    BACKGROUND_COLOR, EQUATION_COLOR, MUTED_COLOR, PRIMARY_COLOR,
    SECONDARY_COLOR,
)


class TwoDiceChapter(VivacityScene):
    def _die(self, value: int, color: str):
        die = RoundedRectangle(
            width=1.7, height=1.7, corner_radius=0.14,
            stroke_color=color, stroke_width=4,
            fill_color="#1a2742", fill_opacity=1,
        )
        positions = {
            1: [ORIGIN],
            2: [UL * 0.46, DR * 0.46],
            3: [UL * 0.46, ORIGIN, DR * 0.46],
            4: [UL * 0.46, UR * 0.46, DL * 0.46, DR * 0.46],
            5: [UL * 0.46, UR * 0.46, ORIGIN, DL * 0.46, DR * 0.46],
            6: [UL * 0.46, UR * 0.46, LEFT * 0.46, RIGHT * 0.46, DL * 0.46, DR * 0.46],
        }
        dots = VGroup(*[Dot(p, radius=0.09, color=SECONDARY_COLOR) for p in positions[value]])
        return VGroup(die, dots)

    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        title = self.safe_title("Two dice: outcomes combine into sums")
        self.safe_add(title)

        left = self._die(3, PRIMARY_COLOR)
        right = self._die(4, EQUATION_COLOR)
        dice = VGroup(left, right).arrange(RIGHT, buff=0.55)
        dice.scale_to_fit_height(config.frame_height * 0.42)
        dice.move_to(ORIGIN + UP * 0.15)
        plus = self.safe_text("+", zone=None, font_size=40, color=MUTED_COLOR)
        plus.next_to(left, RIGHT, buff=0.18)
        self.play(FadeIn(left, shift=LEFT * 0.2), FadeIn(right, shift=RIGHT * 0.2), Write(plus), run_time=1.3)

        equation = self.safe_text(r"P(\text{sum}=7)=\frac{6}{36}=\frac{1}{6}", zone=None, font_size=34, color=EQUATION_COLOR)
        equation.next_to(dice, DOWN, buff=0.4)
        self.play(Write(equation), run_time=1.7)
        self.wait(1.0)
        self.play(FadeOut(equation), FadeOut(plus), FadeOut(dice), run_time=0.7)

