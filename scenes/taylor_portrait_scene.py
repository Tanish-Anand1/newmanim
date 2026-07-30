"""
Portrait-mode Taylor Series scene — optimized for mobile/YouTube/Instagram (9:16).
No overlapping text. Rendered directly with Manim (not through template pipeline).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import BACKGROUND_COLOR

config.background_color = BACKGROUND_COLOR
config.frame_rate = 60
config.pixel_height = 1920
config.pixel_width = 1080
config.frame_height = 16.0
config.frame_width = 9.0

SAFE_TOP = 7.0
SAFE_BOTTOM = -7.0
SAFE_LEFT = -3.8
SAFE_RIGHT = 3.8


class TaylorPortraitScene(VivacityScene):
    """Crystal-clear Taylor Series in portrait 9:16 for mobile/YT/IG."""

    def _center(self, mobj):
        """Shift a mobject into the portrait safe zone."""
        mobj.shift(RIGHT * max(SAFE_LEFT - mobj.get_left()[0], 0))
        mobj.shift(LEFT * max(mobj.get_right()[0] - SAFE_RIGHT, 0))
        return mobj

    def construct(self):
        # ─── Step 1: Title ──────────────────────────────────────────────
        title = Text("Taylor Series", font_size=52, color=WHITE, weight=BOLD)
        title.move_to(UP * 5.5)
        subtitle = Text("Approximating functions with polynomials",
                         font_size=26, color="#8892a0")
        subtitle.next_to(title, DOWN, buff=0.3)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.2))
        self.wait(2.0)
        self.play(FadeOut(VGroup(title, subtitle)))

        # ─── Step 2: The Formula ─────────────────────────────────────────
        f_header = Text("The Taylor Series Formula", font_size=34,
                         color=WHITE, weight=BOLD)
        f_header.move_to(UP * 5.5)

        formula = MathTex(
            r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^{n}",
            font_size=40, color=BLUE_C
        )
        formula.next_to(f_header, DOWN, buff=0.4)
        self._center(formula)

        f_note = Text(
            "Infinite polynomial sum centered at x = a",
            font_size=22, color="#8892a0"
        )
        f_note.next_to(formula, DOWN, buff=0.3)

        self.play(Write(f_header))
        self.wait(0.2)
        self.play(Write(formula), run_time=1.8)
        self.wait(0.3)
        self.play(FadeIn(f_note, shift=UP * 0.15))
        self.wait(2.5)
        self.play(FadeOut(VGroup(f_header, formula, f_note)))

        # ─── Step 3: Maclaurin ───────────────────────────────────────────
        m_header = Text("Maclaurin Series (a = 0)", font_size=34,
                         color=WHITE, weight=BOLD)
        m_header.move_to(UP * 5.5)

        m_formula = MathTex(
            r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(0)}{n!}x^{n}",
            font_size=40, color=PURPLE_C
        )
        m_formula.next_to(m_header, DOWN, buff=0.4)
        self._center(m_formula)

        m_note = Text(
            "Simplified Taylor series centered at the origin",
            font_size=22, color="#8892a0"
        )
        m_note.next_to(m_formula, DOWN, buff=0.3)

        self.play(Write(m_header), run_time=0.5)
        self.play(TransformMatchingTex(formula.copy(), m_formula),
                  run_time=1.2)
        self.wait(0.3)
        self.play(FadeIn(m_note, shift=UP * 0.15))
        self.wait(2.5)
        self.play(FadeOut(VGroup(m_header, m_formula, m_note)))

        # ─── Step 4: sin(x) term-by-term ─────────────────────────────────
        s_header = Text("Expand sin(x) step by step", font_size=32,
                         color=WHITE, weight=BOLD)
        s_header.move_to(UP * 5.8)

        eq1 = MathTex(r"\sin x \approx x", font_size=40, color=BLUE_C)
        eq2 = MathTex(r"\sin x \approx x-\frac{x^{3}}{6}",
                       font_size=38, color=GREEN_C)
        eq3 = MathTex(r"\sin x \approx x-\frac{x^{3}}{6}+\frac{x^{5}}{120}",
                       font_size=34, color=TEAL_C)

        eq1.move_to(LEFT * 2.0 + UP * 3.5)
        eq2.next_to(eq1, DOWN, buff=0.5, aligned_edge=LEFT)
        eq3.next_to(eq2, DOWN, buff=0.5, aligned_edge=LEFT)

        t1 = Text("P1 (linear)", font_size=20, color=BLUE_C)
        t2 = Text("P3 (cubic)", font_size=20, color=GREEN_C)
        t3 = Text("P5 (quintic)", font_size=20, color=TEAL_C)
        t1.next_to(eq1, RIGHT, buff=0.35)
        t2.next_to(eq2, RIGHT, buff=0.35)
        t3.next_to(eq3, RIGHT, buff=0.35)

        self.play(Write(s_header))
        self.play(Write(eq1), Write(t1), run_time=0.8)
        self.wait(1.0)
        self.play(Write(eq2), Write(t2), run_time=0.8)
        self.wait(1.0)
        self.play(Write(eq3), Write(t3), run_time=0.8)
        self.wait(2.5)

        self.play(FadeOut(VGroup(s_header, eq1, eq2, eq3, t1, t2, t3)))

        # ─── Step 5: Graph ───────────────────────────────────────────────
        g_header = Text("sin(x) vs Taylor Approximations", font_size=30,
                         color=WHITE, weight=BOLD)
        g_header.move_to(UP * 6.0)

        axes = Axes(
            x_range=[-PI, PI, PI / 2],
            y_range=[-1.6, 1.6, 0.5],
            x_length=7.0,
            y_length=5.0,
            axis_config={"color": "#555555", "include_numbers": True,
                         "font_size": 15},
            x_axis_config={
                "numbers_to_include": [-3, -2, -1, 0, 1, 2, 3],
                "decimal_number_config": {"num_decimal_places": 0},
            },
            y_axis_config={
                "numbers_to_include": [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5],
            },
        )
        axes.center()
        axes.shift(DOWN * 0.5)

        xl = MathTex("x", font_size=20, color="#8892a0")
        yl = MathTex("y", font_size=20, color="#8892a0")
        xl.next_to(axes.c2p(PI + 0.3, 0), DOWN, buff=0.05)
        yl.next_to(axes.c2p(0, 1.7), LEFT, buff=0.05)

        sin_c = axes.plot(
            lambda x: np.sin(x), x_range=[-PI, PI],
            color=WHITE, stroke_width=3.0
        )
        sin_l = MathTex(r"\sin x", font_size=22, color=WHITE)
        sin_l.next_to(axes.c2p(PI * 0.85, np.sin(PI * 0.85)), UR, buff=0.05)

        p1_c = axes.plot(
            lambda x: x, x_range=[-PI, PI],
            color=BLUE_C, stroke_width=2.5
        )
        p1_l = MathTex(r"P_{1}(x)=x", font_size=20, color=BLUE_C)
        p1_l.next_to(axes.c2p(PI * 0.6, PI * 0.6), UL, buff=0.05)

        p3_c = axes.plot(
            lambda x: x - x**3 / 6, x_range=[-PI, PI],
            color=GREEN_C, stroke_width=2.5
        )
        p3_l = MathTex(r"P_{3}(x)=x-\frac{x^{3}}{6}",
                        font_size=18, color=GREEN_C)
        p3_l.next_to(axes.c2p(PI * 0.7, PI * 0.7 - (PI * 0.7)**3 / 6),
                      DOWN, buff=0.05)

        p5_c = axes.plot(
            lambda x: x - x**3 / 6 + x**5 / 120, x_range=[-PI, PI],
            color=TEAL_C, stroke_width=2.5
        )
        p5_l = MathTex(
            r"P_{5}(x)=x-\frac{x^{3}}{6}+\frac{x^{5}}{120}",
            font_size=17, color=TEAL_C
        )
        p5_l.next_to(axes.c2p(PI * 0.3,
                               PI * 0.3 - (PI * 0.3)**3 / 6
                               + (PI * 0.3)**5 / 120),
                      UR, buff=0.05)

        self.play(Write(g_header))
        self.play(Create(axes), Write(xl), Write(yl), run_time=1.0)
        self.wait(0.2)

        self.play(Create(sin_c), Write(sin_l), run_time=1.2)
        self.wait(0.5)
        self.play(Create(p1_c), Write(p1_l), run_time=0.8)
        self.wait(0.5)
        self.play(Create(p3_c), Write(p3_l), run_time=0.8)
        self.wait(0.5)
        self.play(Create(p5_c), Write(p5_l), run_time=0.8)
        self.wait(3.5)

        self.play(FadeOut(VGroup(
            g_header, axes, xl, yl,
            sin_c, sin_l, p1_c, p1_l, p3_c, p3_l, p5_c, p5_l,
        )))

        # ─── Step 6: Active Recall ──────────────────────────────────────
        rh = Text("Active Recall", font_size=42, color=WHITE, weight=BOLD)
        rh.move_to(UP * 5.5)
        self.play(Write(rh))
        self.wait(0.5)
        self.play(FadeOut(rh))

        q = Text(
            "Write the first 3 non-zero terms\nof the Maclaurin series for cos(x)",
            font_size=30, color=WHITE, line_spacing=1.3
        )
        q.move_to(UP * 3.0)

        h = Text(
            "cos(0)=1, cos'(0)=0, cos''(0)=-1, cos'''(0)=0",
            font_size=22, color="#8892a0"
        )
        h.next_to(q, DOWN, buff=0.3)

        self.play(Write(q))
        self.play(Write(h))
        self.wait(0.5)

        # Countdown 10 → 1
        cd_pos = DOWN * 3.0
        for sec in range(10, 0, -1):
            c = MathTex(str(sec), font_size=64, color=YELLOW_C)
            c.move_to(cd_pos)
            self.play(FadeIn(c, scale=0.6), run_time=0.12)
            self.wait(0.7)
            if sec > 1:
                self.play(FadeOut(c), run_time=0.08)

        self.play(FadeOut(VGroup(q, h, c)))

        # Answer
        ah = Text("Answer:", font_size=32, color=GREEN_C, weight=BOLD)
        ah.move_to(UP * 4.5)

        af = MathTex(
            r"\cos x \approx 1-\frac{x^{2}}{2}+\frac{x^{4}}{24}",
            font_size=42, color=GREEN_C
        )
        af.next_to(ah, DOWN, buff=0.4)

        an = Text(
            "Same pattern: even powers, alternating signs",
            font_size=24, color="#8892a0"
        )
        an.next_to(af, DOWN, buff=0.3)

        self.play(Write(ah))
        self.play(Write(af), run_time=1.2)
        self.play(FadeIn(an, shift=UP * 0.15))
        self.wait(3.5)

        self.play(FadeOut(VGroup(ah, af, an)))
        self.wait(0.5)


if __name__ == "__main__":
    scene = TaylorPortraitScene()
    scene.render()
