"""
Fourier & Laplace Transforms — portrait 9:16 for mobile.
Visualizes how time-domain signals transform into frequency / complex frequency.
All acceptance checks are run at the end of construct().
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manim import *
from vivacity_base_scene import VivacityScene
from vivacity_constants import BACKGROUND_COLOR

config.background_color = BACKGROUND_COLOR
config.frame_rate = 30
config.pixel_height = 1280
config.pixel_width = 720
config.frame_height = 16.0
config.frame_width = 9.0

C_TITLE  = "#ffffff"
C_SUBTLE = "#6b7280" 
C_BLUE   = "#60a5fa"
C_PURPLE = "#a78bfa"
C_GREEN  = "#34d399"
C_GOLD   = "#fbbf24"
C_ROSE   = "#fb7185"


class FourierLaplaceScene(VivacityScene):
    """Transform time-domain signals → frequency (Fourier) → complex frequency (Laplace)."""

    def _glow(self, mobj, color=C_BLUE, radius=0.4, run=1.5):
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
        # STEP 1 — TITLE
        # ═══════════════════════════════════════════════════════════════
        t1 = Text("Fourier & Laplace Transforms", font_size=42,
                   color=C_TITLE, weight=BOLD)
        t1.move_to(UP * 5.0)
        t2 = Text("From time domain to frequency domain",
                   font_size=24, color=C_SUBTLE)
        t2.next_to(t1, DOWN, buff=0.25)
        self.play(Write(t1), FadeIn(t2, shift=UP * 0.2), run_time=1.2)
        self.wait(2.0)
        self.play(FadeOut(VGroup(t1, t2)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 2 — TIME-DOMAIN SIGNAL
        # ═══════════════════════════════════════════════════════════════
        h2 = Text("Time-Domain Signal", font_size=32, color=C_TITLE, weight=BOLD)
        h2.move_to(UP * 5.8)

        ax_t = Axes(
            x_range=[0, 6, 1], y_range=[-1.5, 1.5, 0.5],
            x_length=7, y_length=3.5,
            axis_config={"color": "#555", "include_numbers": True, "font_size": 14},
            x_axis_config={"numbers_to_include": [0, 1, 2, 3, 4, 5],
                           "decimal_number_config": {"num_decimal_places": 0}},
            y_axis_config={"numbers_to_include": [-1, 0, 1]},
        )
        ax_t.center().shift(DOWN * 1.5)
        xl_t = MathTex("t", font_size=20, color=C_SUBTLE)
        yl_t = MathTex("x(t)", font_size=20, color=C_SUBTLE)
        xl_t.next_to(ax_t.c2p(5.5, 0), DOWN, buff=0.05)
        yl_t.next_to(ax_t.c2p(0, 1.6), LEFT, buff=0.05)

        signal = ax_t.plot(
            lambda t: np.exp(-0.3 * t) * np.sin(2 * t),
            x_range=[0, 5.5], color=C_BLUE, stroke_width=3
        )

        sig_label = MathTex(r"x(t)=e^{-at}\sin(\omega t)", font_size=24, color=C_BLUE)
        sig_label.next_to(ax_t.c2p(3.5, 0.6), UR, buff=0.05)

        self.play(Write(h2))
        self.play(Create(ax_t), Write(xl_t), Write(yl_t), run_time=1.0)
        self.play(Create(signal, rate_func=rate_functions.ease_out_cubic),
                  Write(sig_label), run_time=1.5)
        self._glow(signal, C_BLUE, 0.3, 1.2)
        self.wait(2.0)
        self.play(FadeOut(VGroup(h2, ax_t, xl_t, yl_t, signal, sig_label)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 3 — FOURIER TRANSFORM CONCEPT
        # ═══════════════════════════════════════════════════════════════
        h3 = Text("Fourier Transform: Time → Frequency", font_size=30,
                   color=C_TITLE, weight=BOLD)
        h3.move_to(UP * 5.8)

        ft_eq = MathTex(
            r"X(\omega)=\int_{-\infty}^{\infty}x(t)e^{-j\omega t}dt",
            font_size=34, color=C_PURPLE
        )
        ft_eq.next_to(h3, DOWN, buff=0.4)

        ft_desc = Text(
            "Decomposes signal into sinusoidal\nfrequency components",
            font_size=22, color=C_SUBTLE, line_spacing=1.3
        )
        ft_desc.next_to(ft_eq, DOWN, buff=0.35)

        self.play(Write(h3))
        self.play(Write(ft_eq, rate_func=rate_functions.ease_out_cubic), run_time=1.5)
        self.play(FadeIn(ft_desc, shift=UP * 0.15), run_time=0.4)
        self._glow(ft_eq, C_PURPLE, 0.5, 1.5)
        self.wait(2.0)

        ax_f = Axes(
            x_range=[-3, 3, 1], y_range=[0, 1.2, 0.5],
            x_length=7, y_length=2.5,
            axis_config={"color": "#555", "include_numbers": True, "font_size": 14},
            x_axis_config={"numbers_to_include": [-2, -1, 0, 1, 2]},
            y_axis_config={"numbers_to_include": [0, 0.5, 1.0]},
        )
        ax_f.center().shift(DOWN * 1.5)
        xl_f = MathTex(r"\omega", font_size=20, color=C_SUBTLE)
        yl_f = MathTex("|X|", font_size=20, color=C_SUBTLE)
        xl_f.next_to(ax_f.c2p(2.5, 0), DOWN, buff=0.05)
        yl_f.next_to(ax_f.c2p(0, 1.3), LEFT, buff=0.05)

        spec = ax_f.plot(
            lambda w: 0.4 / ((w - 2)**2 + 0.3) + 0.4 / ((w + 2)**2 + 0.3),
            x_range=[-2.5, 2.5], color=C_PURPLE, stroke_width=3
        )
        spec_label = MathTex(r"|\!X(\omega)\!|", font_size=24, color=C_PURPLE)
        spec_label.next_to(ax_f.c2p(2.2, 1.0), UR, buff=0.05)

        self.play(
            FadeOut(ax_t.copy()),
            Create(ax_f), Write(xl_f), Write(yl_f), run_time=0.8
        )
        self.play(
            Create(spec, rate_func=rate_functions.ease_out_cubic),
            Write(spec_label), run_time=1.5
        )
        self._glow(spec, C_PURPLE, 0.3, 1.2)
        self.wait(2.5)
        self.play(FadeOut(VGroup(h3, ft_eq, ft_desc, ax_f, xl_f, yl_f, spec, spec_label)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 4 — LAPLACE TRANSFORM: EXTENSION TO COMPLEX FREQ
        # ═══════════════════════════════════════════════════════════════
        h4 = Text("Laplace Transform: Time → Complex Frequency",
                   font_size=28, color=C_TITLE, weight=BOLD)
        h4.move_to(UP * 5.8)

        s_def = MathTex(r"s = \sigma + j\omega", font_size=36, color=C_GOLD)
        s_def.next_to(h4, DOWN, buff=0.3)

        lt_eq = MathTex(
            r"X(s)=\int_{0}^{\infty}x(t)e^{-st}dt",
            font_size=34, color=C_GREEN
        )
        lt_eq.next_to(s_def, DOWN, buff=0.35)

        lt_desc = Text(
            "Generalizes Fourier — handles transients\n"
            "and stability via real part sigma",
            font_size=20, color=C_SUBTLE, line_spacing=1.3
        )
        lt_desc.next_to(lt_eq, DOWN, buff=0.3)

        self.play(Write(h4))
        self.play(Write(s_def), run_time=0.5)
        self.play(Write(lt_eq, rate_func=rate_functions.ease_out_cubic), run_time=1.5)
        self.play(FadeIn(lt_desc, shift=UP * 0.12), run_time=0.4)
        self._glow(lt_eq, C_GREEN, 0.5, 1.5)
        self.wait(2.0)

        # s-plane (complex plane)
        sp_header = Text("The s-Plane (Complex Frequency)",
                          font_size=26, color=C_TITLE, weight=BOLD)
        sp_header.move_to(UP * 5.8)

        splane = Axes(
            x_range=[-2, 2, 0.5], y_range=[-2, 2, 0.5],
            x_length=5.5, y_length=5.5,
            axis_config={"color": "#555", "include_numbers": True, "font_size": 12},
            x_axis_config={"numbers_to_include": [-1, 0, 1]},
            y_axis_config={"numbers_to_include": [-1, 0, 1]},
        )
        splane.center().shift(DOWN * 0.5)

        sigma_l = MathTex(r"\sigma", font_size=20, color=C_SUBTLE)
        jw_l = MathTex(r"j\omega", font_size=20, color=C_SUBTLE)
        sigma_l.next_to(splane.c2p(1.5, 0), DOWN, buff=0.05)
        jw_l.next_to(splane.c2p(0, 1.5), LEFT, buff=0.05)

        roc = Rectangle(
            width=3.5, height=5.5,
            fill_color=C_GREEN, fill_opacity=0.06,
            stroke_color=C_GREEN, stroke_width=1,
            stroke_opacity=0.3
        )
        roc.move_to(splane.c2p(-0.5, 0))

        pole = Cross(scale_factor=0.3, color=C_ROSE, stroke_width=3)
        pole.move_to(splane.c2p(-0.3, 2))

        fourier_axis = Line(
            splane.c2p(0, -1.5), splane.c2p(0, 1.5),
            color=C_PURPLE, stroke_width=4
        )

        roc_label = Text("ROC", font_size=16, color=C_GREEN)
        roc_label.move_to(splane.c2p(-1.0, -1.2))
        pole_label = Text("pole", font_size=14, color=C_ROSE)
        pole_label.next_to(pole, DOWN, buff=0.08)
        fj_label = Text("Fourier: jw axis", font_size=16, color=C_PURPLE)
        fj_label.next_to(splane.c2p(0.8, 1.2), UR, buff=0.05)

        self.play(FadeOut(VGroup(h4, s_def, lt_eq, lt_desc)))
        self.play(Write(sp_header))
        self.play(Create(splane), Write(sigma_l), Write(jw_l), run_time=0.8)
        self.play(FadeIn(roc), Write(roc_label), run_time=0.6)
        self.play(Create(pole), Write(pole_label), run_time=0.5)
        self.play(Create(fourier_axis), Write(fj_label), run_time=0.6)
        self.wait(2.5)

        # ═══════════════════════════════════════════════════════════════
        # STEP 5 — RELATIONSHIP: Fourier ⊆ Laplace
        # ═══════════════════════════════════════════════════════════════
        h5 = Text("Key Relationship", font_size=30, color=C_TITLE, weight=BOLD)
        h5.move_to(UP * 5.5)

        rel = MathTex(
            r"\mathcal{F}\{x(t)\} = \mathcal{L}\{x(t)\}|_{s=j\omega}",
            font_size=36, color=C_GOLD
        )
        rel.next_to(h5, DOWN, buff=0.4)

        rel_desc = Text(
            "Fourier transform = Laplace transform\nevaluated on the imaginary axis (s = jw)",
            font_size=22, color=C_SUBTLE, line_spacing=1.4
        )
        rel_desc.next_to(rel, DOWN, buff=0.3)

        bracket = MathTex(
            r"\underbrace{\text{Fourier}}_{\text{on }j\omega\text{ axis}} \subset \underbrace{\text{Laplace}}_{\text{entire }s\text{-plane}}",
            font_size=28, color=C_PURPLE
        )
        bracket.next_to(rel_desc, DOWN, buff=0.4)

        self.play(FadeOut(VGroup(sp_header, splane, sigma_l, jw_l,
                                  roc, roc_label, pole, pole_label,
                                  fourier_axis, fj_label)))
        self.play(Write(h5))
        self.play(Write(rel, rate_func=rate_functions.ease_out_cubic), run_time=1.5)
        self.play(FadeIn(rel_desc, shift=UP * 0.12))
        self.play(Write(bracket), run_time=0.8)
        self._glow(rel, C_GOLD, 0.5, 1.8)
        self.wait(3.0)
        self.play(FadeOut(VGroup(h5, rel, rel_desc, bracket)))

        # ═══════════════════════════════════════════════════════════════
        # STEP 6 — ACTIVE RECALL
        # ═══════════════════════════════════════════════════════════════
        rh = Text("Active Recall", font_size=40, color=C_TITLE, weight=BOLD)
        rh.move_to(UP * 5.5)
        self.play(Write(rh))
        self.wait(0.5)
        self.play(FadeOut(rh))

        q = Text(
            "If a Laplace transform has a pole at\n"
            "s = 2 + j3, does its Fourier transform exist?\n"
            "Hint: check the ROC and the jw axis.",
            font_size=26, color=C_TITLE, line_spacing=1.4
        )
        q.move_to(UP * 3.0)
        self.play(Write(q), run_time=0.6)
        self.wait(0.5)

        cd_pos = DOWN * 3.2
        for sec in range(8, 0, -1):
            c = MathTex(str(sec), font_size=64, color=C_GOLD)
            c.move_to(cd_pos)
            if sec == 8:
                self.play(FadeIn(c, scale=0.5), run_time=0.12)
            else:
                pv = MathTex(str(sec + 1), font_size=64, color=C_GOLD)
                pv.move_to(cd_pos)
                self.play(FadeOut(pv)
                self.add(c), run_time=0.15)
                self.remove(pv)
            self.add(c)
            self.wait(0.6)
            if sec > 1:
                self.remove(c)
        self.remove(c)
        self.play(FadeOut(q), run_time=0.3)

        ah = Text("Answer:", font_size=30, color=C_GREEN, weight=BOLD)
        ah.move_to(UP * 4.5)

        af = MathTex(
            r"\text{No: } \sigma=2 \text{ means ROC is } \sigma>2,",
            font_size=32, color=C_GREEN
        )
        af.next_to(ah, DOWN, buff=0.3)

        af2 = MathTex(
            r"\text{so } j\omega\text{ axis }(\sigma=0)\text{ is NOT in the ROC.}",
            font_size=28, color=C_GREEN
        )
        af2.next_to(af, DOWN, buff=0.2)

        an = Text(
            "Fourier exists only when ROC includes the imaginary axis",
            font_size=20, color=C_SUBTLE
        )
        an.next_to(af2, DOWN, buff=0.35)

        burst = Circle(radius=0.3, color=C_GREEN,
                        fill_opacity=0.15, stroke_width=0)
        burst.move_to(ah)
        self.play(Write(ah), burst.animate.scale(10).set_opacity(0), run_time=0.5)
        self.remove(burst)
        self.play(Write(af), run_time=0.8)
        self.play(Write(af2), run_time=0.8)
        self.play(FadeIn(an, shift=UP * 0.12))
        self._glow(VGroup(af, af2), C_GREEN, 0.5, 2.0)
        self.wait(3.5)
        self.play(FadeOut(VGroup(ah, af, af2, an)))
        self.wait(0.5)

        # ── Run all acceptance checks ──
        from app.render_acceptance import run_render_acceptance as _check
        try:
            _check(self)
            print("ALL ACCEPTANCE CHECKS PASSED ✓")
        except ValueError as _e:
            print(f"ACCEPTANCE CHECK FAILED: {_e}")
            raise


if __name__ == "__main__":
    scene = FourierLaplaceScene()
    scene.render()
