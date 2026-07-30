"""
Professional Taylor Series — built on the proven portrait layout.
Same exact positioning as the verified working version, plus pro animations.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manim import *
from vivacity_constants import BACKGROUND_COLOR
from vivacity_base_scene import VivacityScene

config.background_color = BACKGROUND_COLOR
config.frame_rate = 30
config.pixel_height = 1280
config.pixel_width = 720
config.frame_height = 16.0
config.frame_width = 9.0

C_TITLE  = "#ffffff"
C_SUBTLE = "#6b7280"
C_ACCENT = "#60a5fa"
C_PURPLE = "#a78bfa"
C_GREEN  = "#34d399"
C_TEAL   = "#2dd4bf"
C_GOLD   = "#fbbf24"
C_ROSE   = "#fb7185"


class TaylorProScene(VivacityScene):
    """Pro Taylor Series — all the quality, zero overlap."""

    def _glow(self, mobj, color=C_ACCENT, radius=0.4, run=1.5):
        glow = Circle(
            radius=mobj.width * 0.5 + radius,
            color=color, stroke_width=0, fill_opacity=0.07
        )
        glow.move_to(mobj.get_center())
        self.add(glow)
        self.play(glow.animate.scale(1.15).set_opacity(0.15),
                  rate_func=there_and_back, run_time=run)
        self.remove(glow)

    def construct(self):
        # ═══════════════════════════════════════════════════════════════
        # STEP 1 — TITLE (proven positioning from portrait scene)
        # ═══════════════════════════════════════════════════════════════
        title = Text("Taylor Series", font_size=52, color=C_TITLE, weight=BOLD)
        title.move_to(UP * 5.5)
        subtitle = Text("Approximating functions with polynomials",
                         font_size=26, color=C_SUBTLE)
        subtitle.next_to(title, DOWN, buff=0.3)

        tg = Circle(radius=3.5, color=C_ACCENT, stroke_width=0, fill_opacity=0.05)
        tg.move_to(title)

        self.play(FadeIn(tg, scale=0.3, rate_func=rush_into), run_time=0.5)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.2), run_time=1.2)
        self.play(tg.animate.scale(1.3).set_opacity(0.01), rate_func=there_and_back, run_time=1.2)
        self.wait(2.0)
        self.play(FadeOut(VGroup(title, subtitle, tg)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 2 — FORMULA (proven positioning)
        # ═══════════════════════════════════════════════════════════════
        fh = Text("The Taylor Series Formula", font_size=34,
                   color=C_TITLE, weight=BOLD)
        fh.move_to(UP * 5.5)

        fe = MathTex(
            r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(a)}{n!}(x-a)^{n}",
            font_size=40, color=C_ACCENT
        )
        fe.next_to(fh, DOWN, buff=0.4)

        fn = Text("Infinite polynomial sum centered at x = a",
                   font_size=22, color=C_SUBTLE)
        fn.next_to(fe, DOWN, buff=0.3)

        self.play(Write(fh), run_time=0.4)
        self.play(Write(fe, rate_func=rate_functions.ease_out_cubic), run_time=1.8)
        self.play(FadeIn(fn, shift=UP * 0.15), run_time=0.4)
        self._glow(fe, C_ACCENT, 0.5, 1.5)
        self.wait(2.5)
        self.play(FadeOut(VGroup(fh, fe, fn)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 3 — MACLAURIN with morph (proven positioning)
        # ═══════════════════════════════════════════════════════════════
        mh = Text("Maclaurin Series (a = 0)", font_size=34,
                   color=C_TITLE, weight=BOLD)
        mh.move_to(UP * 5.5)

        me = MathTex(
            r"f(x)=\sum_{n=0}^{\infty}\frac{f^{(n)}(0)}{n!}x^{n}",
            font_size=40, color=C_PURPLE
        )
        me.next_to(mh, DOWN, buff=0.4)

        mn = Text("Simplified Taylor series centered at the origin",
                   font_size=22, color=C_SUBTLE)
        mn.next_to(me, DOWN, buff=0.3)

        self.play(Write(mh), run_time=0.5)
        self.play(TransformMatchingTex(fe.copy(), me), run_time=1.2)
        self.wait(0.3)
        self.play(FadeIn(mn, shift=UP * 0.15), run_time=0.4)
        self._glow(me, C_PURPLE, 0.5, 1.5)
        self.wait(2.5)
        self.play(FadeOut(VGroup(mh, me, mn)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 4 — SIN X term-by-term (proven positioning)
        # ═══════════════════════════════════════════════════════════════
        sh = Text("Expand sin(x) step by step", font_size=32,
                   color=C_TITLE, weight=BOLD)
        sh.move_to(UP * 5.8)

        e1 = MathTex(r"\sin x \approx x", font_size=40, color=C_ACCENT)
        e2 = MathTex(r"\sin x \approx x-\frac{x^{3}}{6}",
                      font_size=38, color=C_GREEN)
        e3 = MathTex(r"\sin x \approx x-\frac{x^{3}}{6}+\frac{x^{5}}{120}",
                      font_size=34, color=C_TEAL)

        e1.move_to(LEFT * 2.0 + UP * 3.5)
        e2.next_to(e1, DOWN, buff=0.5, aligned_edge=LEFT)
        e3.next_to(e2, DOWN, buff=0.5, aligned_edge=LEFT)

        t1 = Text("P1 (linear)", font_size=20, color=C_ACCENT)
        t2 = Text("P3 (cubic)", font_size=20, color=C_GREEN)
        t3 = Text("P5 (quintic)", font_size=20, color=C_TEAL)
        t1.next_to(e1, RIGHT, buff=0.35)
        t2.next_to(e2, RIGHT, buff=0.35)
        t3.next_to(e3, RIGHT, buff=0.35)

        self.play(Write(sh))
        for eq, tag, col in [(e1, t1, C_ACCENT), (e2, t2, C_GREEN), (e3, t3, C_TEAL)]:
            self.play(Write(eq), Write(tag), run_time=0.8)
            self._glow(eq, col, 0.3, 1.0)
            self.wait(1.5)

        self.wait(1.0)
        self.play(FadeOut(VGroup(sh, e1, e2, e3, t1, t2, t3)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 5 — GRAPH (proven positioning from portrait scene)
        # ═══════════════════════════════════════════════════════════════
        gh = Text("sin(x) vs Taylor Approximations", font_size=30,
                   color=C_TITLE, weight=BOLD)
        gh.move_to(UP * 6.0)

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

        xl = MathTex("x", font_size=20, color=C_SUBTLE)
        yl = MathTex("y", font_size=20, color=C_SUBTLE)
        xl.next_to(axes.c2p(PI + 0.3, 0), DOWN, buff=0.05)
        yl.next_to(axes.c2p(0, 1.7), LEFT, buff=0.05)

        sc = axes.plot(
            lambda x: np.sin(x), x_range=[-PI, PI],
            color=C_TITLE, stroke_width=3.0
        )
        sl = MathTex(r"\sin x", font_size=22, color=C_TITLE)
        sl.next_to(axes.c2p(PI * 0.85, np.sin(PI * 0.85)), UR, buff=0.05)

        p1c = axes.plot(
            lambda x: x, x_range=[-PI, PI],
            color=C_ACCENT, stroke_width=2.5
        )
        p1l = MathTex(r"P_{1}(x)=x", font_size=20, color=C_ACCENT)
        p1l.next_to(axes.c2p(PI * 0.6, PI * 0.6), UL, buff=0.05)

        p3c = axes.plot(
            lambda x: x - x**3 / 6, x_range=[-PI, PI],
            color=C_GREEN, stroke_width=2.5
        )
        p3l = MathTex(r"P_{3}(x)=x-\frac{x^{3}}{6}",
                       font_size=18, color=C_GREEN)
        p3l.next_to(axes.c2p(PI * 0.7, PI * 0.7 - (PI * 0.7)**3 / 6),
                     DOWN, buff=0.05)

        p5c = axes.plot(
            lambda x: x - x**3 / 6 + x**5 / 120, x_range=[-PI, PI],
            color=C_TEAL, stroke_width=2.5
        )
        p5l = MathTex(
            r"P_{5}(x)=x-\frac{x^{3}}{6}+\frac{x^{5}}{120}",
            font_size=17, color=C_TEAL
        )
        p5l.next_to(axes.c2p(PI * 0.3,
                               PI * 0.3 - (PI * 0.3)**3 / 6
                               + (PI * 0.3)**5 / 120),
                      UR, buff=0.05)

        self.play(Write(gh))
        self.play(Create(axes), Write(xl), Write(yl), run_time=1.0)
        self.wait(0.2)
        self.play(Create(sc), Write(sl), run_time=1.2)
        self.wait(0.5)
        self.play(Create(p1c), Write(p1l), run_time=0.8)
        self.wait(0.5)
        self.play(Create(p3c), Write(p3l), run_time=0.8)
        self.wait(0.5)
        self.play(Create(p5c), Write(p5l), run_time=0.8)
        self.wait(3.5)
        self.play(FadeOut(VGroup(gh, axes, xl, yl, sc, sl,
                                  p1c, p1l, p3c, p3l, p5c, p5l)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 6 — ACTIVE RECALL (proven positioning)
        # ═══════════════════════════════════════════════════════════════
        rh = Text("Active Recall", font_size=42, color=C_TITLE, weight=BOLD)
        rh.move_to(UP * 5.5)
        self.play(Write(rh))
        self.wait(0.5)
        self.play(FadeOut(rh))

        q = Text(
            "Write the first 3 non-zero terms\n"
            "of the Maclaurin series for cos(x)",
            font_size=30, color=C_TITLE, line_spacing=1.3
        )
        q.move_to(UP * 3.0)

        h = Text(
            "cos(0)=1, cos'(0)=0, cos''(0)=-1, cos'''(0)=0",
            font_size=22, color=C_SUBTLE
        )
        h.next_to(q, DOWN, buff=0.3)

        self.play(Write(q))
        self.play(Write(h))
        self.wait(0.5)

        cd_pos = DOWN * 3.0
        for sec in range(10, 0, -1):
            c = MathTex(str(sec), font_size=64, color=C_GOLD)
            c.move_to(cd_pos)
            self.play(FadeIn(c, scale=0.6), run_time=0.12)
            self.wait(0.7)
            if sec > 1:
                self.play(FadeOut(c), run_time=0.08)

        self.play(FadeOut(VGroup(q, h, c)))

        ah = Text("Answer:", font_size=32, color=C_GREEN, weight=BOLD)
        ah.move_to(UP * 4.5)

        af = MathTex(
            r"\cos x \approx 1-\frac{x^{2}}{2}+\frac{x^{4}}{24}",
            font_size=42, color=C_GREEN
        )
        af.next_to(ah, DOWN, buff=0.4)

        an = Text(
            "Same pattern: even powers, alternating signs",
            font_size=24, color=C_SUBTLE
        )
        an.next_to(af, DOWN, buff=0.3)

        self.play(Write(ah))
        self.play(Write(af), run_time=1.2)
        self.play(FadeIn(an, shift=UP * 0.15))
        self._glow(af, C_GREEN, 0.5, 2.0)
        self.wait(3.5)
        self.play(FadeOut(VGroup(ah, af, an)))
        self.wait(0.5)


if __name__ == "__main__":
    scene = TaylorProScene()
    scene.render()
