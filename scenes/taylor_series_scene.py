"""
Crystal-clear Taylor Series scene.
Plots actual sin(x) vs P1 and P3 Taylor approximations.
"""
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import BACKGROUND_COLOR

config.background_color = BACKGROUND_COLOR
config.frame_rate = 60


class TaylorSeriesScene(VivacityScene):
    def construct(self):
        # ─── Step 1: Title ──────────────────────────────────────────────
        title = self.safe_title("Taylor Series Expansion")
        self.play(Write(title))
        self.wait(1.5)
        self.play(FadeOut(title))

        # ─── Step 2: The Formula ─────────────────────────────────────────
        formula_title = self.safe_text("The Formula", font_size=36)
        formula = MathTex(
            r"f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(a)}{n!} (x-a)^n",
            font_size=42, color=BLUE_C
        )
        formula_group = VGroup(formula_title, formula).arrange(DOWN, buff=0.4)
        self.play(Write(formula_title), Write(formula))
        self.wait(2)
        self.play(FadeOut(formula_group))

        # ─── Step 3: Maclaurin (a=0) ─────────────────────────────────────
        mac_title = self.safe_text("Maclaurin Series (a = 0)", font_size=36)
        mac_formula = MathTex(
            r"f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(0)}{n!} x^n",
            font_size=42, color=PURPLE_C
        )
        mac_group = VGroup(mac_title, mac_formula).arrange(DOWN, buff=0.4)
        self.play(Write(mac_title), Write(mac_formula))
        self.wait(2)
        self.play(FadeOut(mac_group))

        # ─── Step 4: sin(x) expansion term by term ──────────────────────
        sin_title = self.safe_text("Expand sin(x) term by term", font_size=34)

        sin_intro = MathTex(r"\sin x", font_size=48, color=YELLOW_C)
        eq1 = MathTex(r"\sin x \approx x", font_size=40, color=BLUE_C)
        eq2 = MathTex(r"\sin x \approx x - \frac{x^{3}}{6}", font_size=40, color=GREEN_C)
        eq3 = MathTex(r"\sin x \approx x - \frac{x^{3}}{6} + \frac{x^{5}}{120}", font_size=38, color=TEAL_C)

        # Align equations at the & marker
        eq1.align_to(eq2, LEFT)
        eq3.align_to(eq2, LEFT)

        sin_group = VGroup(sin_title, sin_intro).arrange(DOWN, buff=0.3)
        sin_group.to_edge(UP)

        eq1.next_to(sin_group, DOWN, buff=0.5)
        eq1.align_to(sin_group, LEFT)
        eq2.next_to(eq1, DOWN, buff=0.2)
        eq2.align_to(eq1, LEFT)
        eq3.next_to(eq2, DOWN, buff=0.2)
        eq3.align_to(eq2, LEFT)

        self.play(Write(sin_title))
        self.play(Write(sin_intro))
        self.wait(0.5)

        # P1 - linear
        p1_label = self.safe_text("P1 (linear)", font_size=24, color=BLUE_C)
        p1_label.next_to(eq1, RIGHT, buff=0.3)
        self.play(Write(eq1), Write(p1_label))
        self.wait(1.5)

        # P2
        p2_label = self.safe_text("P3 (cubic)", font_size=24, color=GREEN_C)
        p2_label.next_to(eq2, RIGHT, buff=0.3)
        self.play(Write(eq2), Write(p2_label))
        self.wait(1.5)

        # P3
        p3_label = self.safe_text("P5 (quintic)", font_size=24, color=TEAL_C)
        p3_label.next_to(eq3, RIGHT, buff=0.3)
        self.play(Write(eq3), Write(p3_label))
        self.wait(2)

        self.play(FadeOut(VGroup(sin_group, eq1, eq2, eq3, p1_label, p2_label, p3_label)))

        # ─── Step 5: Graph — plot sin(x) vs Taylor approximations ──────
        graph_title = self.safe_text("sin(x) vs Taylor Approximations", font_size=34)

        axes = Axes(
            x_range=[-PI, PI, PI / 2],
            y_range=[-1.5, 1.5, 0.5],
            x_length=7,
            y_length=5,
            axis_config={"color": GREY_B, "include_numbers": True, "font_size": 18},
            x_axis_config={"numbers_to_include": [-PI, -PI/2, 0, PI/2, PI],
                           "decimal_number_config": {"num_decimal_places": 0}},
        )
        labels = axes.get_axis_labels(x_label="x", y_label="y")

        # Shift axes down to make room for title
        axes_group = VGroup(axes, labels)
        axes_group.next_to(graph_title, DOWN, buff=0.3)

        # sin(x) — the actual curve
        sin_curve = axes.plot(lambda x: np.sin(x), x_range=[-PI, PI], color=WHITE, stroke_width=2.5)
        sin_label = MathTex(r"\sin x", font_size=24, color=WHITE)
        sin_label.next_to(sin_curve.get_end(), RIGHT, buff=0.1)

        # P1: x
        p1_curve = axes.plot(lambda x: x, x_range=[-PI, PI], color=BLUE_C, stroke_width=2)
        p1_label_g = MathTex(r"P_{1}(x)=x", font_size=22, color=BLUE_C)
        p1_label_g.next_to(axes.c2p(PI*0.6, PI*0.6), UP, buff=0.1)

        # P3: x - x^3/6
        p3_curve = axes.plot(lambda x: x - x**3/6, x_range=[-PI, PI], color=GREEN_C, stroke_width=2)
        p3_label_g = MathTex(r"P_{3}(x)=x-\frac{x^{3}}{6}", font_size=22, color=GREEN_C)
        p3_label_g.next_to(axes.c2p(PI*0.7, PI*0.7 - (PI*0.7)**3/6), DOWN, buff=0.1)

        # P5: x - x^3/6 + x^5/120
        p5_curve = axes.plot(lambda x: x - x**3/6 + x**5/120, x_range=[-PI, PI], color=TEAL_C, stroke_width=2)
        p5_label_g = MathTex(r"P_{5}(x)=x-\frac{x^{3}}{6}+\frac{x^{5}}{120}", font_size=20, color=TEAL_C)
        p5_label_g.next_to(axes.c2p(PI*0.5, PI*0.5 - (PI*0.5)**3/6 + (PI*0.5)**5/120), UR, buff=0.1)

        self.play(Write(graph_title))
        self.play(Create(axes), Write(labels))
        self.wait(0.3)

        # Animate curves appearing one by one
        self.play(Create(sin_curve), Write(sin_label), run_time=1.2)
        self.wait(0.5)

        self.play(Create(p1_curve), Write(p1_label_g), run_time=1)
        self.wait(1)

        self.play(Create(p3_curve), Write(p3_label_g), run_time=1)
        self.wait(1)

        self.play(Create(p5_curve), Write(p5_label_g), run_time=1)
        self.wait(2.5)

        self.play(FadeOut(VGroup(graph_title, axes_group, sin_curve, sin_label,
                                  p1_curve, p1_label_g, p3_curve, p3_label_g,
                                  p5_curve, p5_label_g)))

        # ─── Step 6: Active Recall ──────────────────────────────────────
        recall_title = self.safe_title("Active Recall")
        self.play(Write(recall_title))
        self.wait(0.5)
        self.play(FadeOut(recall_title))

        recall_q = self.safe_text(
            "Write the first 3 non-zero terms of the\nMaclaurin series for cos(x)",
            font_size=32
        )
        recall_hint = self.safe_text(
            "(Hint: cos(0)=1, cos'(0)=0, cos''(0)=-1, cos'''(0)=0, cos''''(0)=1)",
            font_size=20, color=GREY_B
        )
        recall_group = VGroup(recall_q, recall_hint).arrange(DOWN, buff=0.3)

        self.play(Write(recall_q))
        self.play(Write(recall_hint))
        self.wait(1)

        # Countdown
        for sec in range(10, 0, -1):
            counter = self.safe_text(str(sec), font_size=56, color=YELLOW_C)
            counter.next_to(recall_group, DOWN, buff=0.5)
            self.play(TransformMatchingShapes(
                self.safe_text(str(sec + 1), font_size=56, color=YELLOW_C) if sec < 10 else self.safe_text("", font_size=1),
                counter
            ), run_time=0.3)
            self.wait(0.7)
            if sec > 1:
                self.remove(counter)

        self.wait(0.5)
        self.play(FadeOut(recall_group))

        # Reveal answer
        answer_title = self.safe_text("Answer:", font_size=32, color=GREEN_C)
        answer = MathTex(
            r"\cos x \approx 1 - \frac{x^{2}}{2} + \frac{x^{4}}{24}",
            font_size=40, color=GREEN_C
        )
        answer_group = VGroup(answer_title, answer).arrange(DOWN, buff=0.3)
        self.play(Write(answer_title))
        self.wait(0.3)
        self.play(Write(answer))
        self.wait(3)

        self.play(FadeOut(answer_group))
        self.wait(0.5)


if __name__ == "__main__":
    from manim import config as manim_config
    manim_config.pixel_height = 1920
    manim_config.pixel_width = 1080
    manim_config.frame_height = 16
    manim_config.frame_width = 9
    scene = TaylorSeriesScene()
    scene.render()
