from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import (
    BACKGROUND_COLOR, EQUATION_COLOR, MUTED_COLOR, PRIMARY_COLOR,
    SECONDARY_COLOR,
)


class ManyDiceChapter(VivacityScene):
    def construct(self):
        self.camera.background_color = BACKGROUND_COLOR
        title = self.safe_title("Many dice: a distribution emerges")
        self.safe_add(title)

        axes = Axes(
            x_range=[2, 20, 2], y_range=[0, 1, 0.2],
            x_length=6.0, y_length=3.4,
            axis_config={"color": MUTED_COLOR, "stroke_width": 2}, tips=False,
        ).shift(DOWN * 0.28)
        bars = VGroup()
        for index, height in enumerate([0.16, 0.28, 0.46, 0.68, 0.86, 0.98, 0.86, 0.68, 0.46, 0.28, 0.16]):
            x = 5 + index * 1.35
            rect = Rectangle(
                width=0.72, height=height * 2.7,
                stroke_color=PRIMARY_COLOR, stroke_width=2,
                fill_color=PRIMARY_COLOR, fill_opacity=0.7,
            )
            rect.move_to(axes.c2p(x, height / 2))
            bars.add(rect)
        diagram = VGroup(axes, bars)
        diagram.scale_to_fit_height(config.frame_height * 0.48)
        diagram.move_to(ORIGIN + DOWN * 0.05)
        self.play(Create(axes), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(bar, shift=UP * 0.16) for bar in bars], lag_ratio=0.08), run_time=1.8)

        label = self.safe_text(r"\text{more trials}\ \Longrightarrow\ \text{stable probabilities}", zone=None, font_size=31, color=EQUATION_COLOR)
        label.next_to(diagram, DOWN, buff=0.35)
        self.play(Write(label), run_time=1.5)
        self.wait(1.2)
        self.play(FadeOut(label), FadeOut(diagram), run_time=0.8)

