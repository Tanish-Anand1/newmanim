from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import (
    BACKGROUND_COLOR, EQUATION_COLOR, MUTED_COLOR, PRIMARY_COLOR,
    SECONDARY_COLOR,
)


class OneDieChapter(VivacityScene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        title = self.safe_title("Why are die outcomes equally likely?")
        self.safe_add(title)

        die = RoundedRectangle(
            width=2.2, height=2.2, corner_radius=0.18,
            stroke_color=PRIMARY_COLOR, stroke_width=5,
            fill_color="#1a2742", fill_opacity=1,
        )
        dots = VGroup(*[
            Dot(point, radius=0.12, color=SECONDARY_COLOR)
            for point in [UL * 0.62, UR * 0.62, ORIGIN, DL * 0.62, DR * 0.62]
        ])
        diagram = VGroup(die, dots)
        diagram.scale_to_fit_height(config.frame_height * 0.48)
        diagram.move_to(ORIGIN + UP * 0.15)
        self.play(FadeIn(diagram, shift=UP * 0.18), run_time=1.2)

        label = self.safe_text(r"P(1)=P(2)=\cdots=P(6)=\frac{1}{6}", zone=None, font_size=34, color=EQUATION_COLOR)
        label.next_to(diagram, DOWN, buff=0.38)
        self.play(Write(label), run_time=1.8)
        self.wait(1.0)
        self.play(FadeOut(label), run_time=0.45)
        self.play(FadeOut(diagram), run_time=0.6)

