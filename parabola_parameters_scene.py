from manim import *
from vivacity_base_scene import VivacityScene


class ParabolaParameterAnimation(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        title = Tex("How the parameters shape", color="#f4f7fb", font_size=32)
        equation = MathTex(r"y=mx^2+c", color="#69d2ff", font_size=40)
        heading = VGroup(title, equation).arrange(RIGHT, buff=0.16)
        heading.scale_to_fit_width(config.frame_width - 0.55)
        heading.to_edge(UP, buff=0.32)
        assert heading.width <= config.frame_width - 0.35
        self.play(Write(title), Write(equation), run_time=1.4)

        axes = Axes(
            x_range=[-1.5, 1.5, 0.5],
            y_range=[-2.5, 2.5, 0.5],
            x_length=3.65,
            y_length=5.0,
            axis_config={"color": "#9aa8bb", "stroke_width": 2},
            tips=False,
        ).shift(DOWN * 0.38)
        x_label = MathTex("x", color="#cbd5e1", font_size=26).next_to(axes.x_axis, RIGHT, buff=0.1)
        y_label = MathTex("y", color="#cbd5e1", font_size=26).next_to(axes.y_axis, UP, buff=0.1)
        plane = VGroup(axes, x_label, y_label)
        self.play(Create(axes), Write(x_label), Write(y_label), run_time=1.1)

        m = ValueTracker(-1.5)
        c = ValueTracker(0.0)

        def current_curve():
            return axes.plot(
            lambda x: m.get_value() * x**2 + c.get_value(),
            x_range=[-1.32, 1.32],
            color="#69d2ff",
            stroke_width=5,
            use_smoothing=False,
        )

        curve = always_redraw(current_curve)

        vertex = Dot(axes.c2p(0, c.get_value()), radius=0.085, color="#f7c948")
        vertex.add_updater(lambda mob: mob.move_to(axes.c2p(0, c.get_value())))

        m_value = DecimalNumber(m.get_value(), num_decimal_places=1, color="#69d2ff", font_size=26)
        c_value = DecimalNumber(c.get_value(), num_decimal_places=1, color="#ff9f68", font_size=26)
        m_value.add_updater(lambda mob: mob.set_value(m.get_value()))
        c_value.add_updater(lambda mob: mob.set_value(c.get_value()))
        values = VGroup(
            VGroup(MathTex("m=", color="#cbd5e1", font_size=26), m_value).arrange(RIGHT, buff=0.06),
            VGroup(MathTex("c=", color="#cbd5e1", font_size=26), c_value).arrange(RIGHT, buff=0.06),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
        values.to_corner(UR, buff=0.24)
        values.shift(DOWN * 0.62)
        values.add_background_rectangle(color="#111a2c", opacity=0.88, buff=0.12)

        vertex_text = self.live_value_label(
            c,
            lambda: vertex.get_center() + UR * 0.12,
            fmt="(0,\\,{:.1f})",
        )
        self.add(curve, vertex, vertex_text, values)

        phase_m = Tex("Change m: opening and steepness", color="#f4f7fb", font_size=23)
        phase_m.to_edge(DOWN, buff=0.42)
        self.play(FadeIn(phase_m, shift=UP * 0.1), run_time=0.7)
        self.wait(0.7)
        self.play(m.animate.set_value(1.5), run_time=5.2, rate_func=linear)
        self.wait(0.8)

        self.play(FadeOut(phase_m), run_time=0.45)
        m.set_value(0.8)
        phase_c = Tex("Change c: vertical translation", color="#f4f7fb", font_size=23)
        phase_c.to_edge(DOWN, buff=0.42)
        self.play(FadeIn(phase_c, shift=UP * 0.1), run_time=0.7)
        self.wait(0.6)
        self.play(c.animate.set_value(1.8), run_time=3.0, rate_func=linear)
        self.play(c.animate.set_value(-1.8), run_time=4.2, rate_func=linear)
        self.play(c.animate.set_value(0.0), run_time=2.3, rate_func=linear)
        self.wait(0.8)

        takeaway = Tex("m controls shape; c controls height.", color="#f4f7fb", font_size=24)
        takeaway.scale_to_fit_width(config.frame_width - 0.55)
        takeaway.to_edge(DOWN, buff=0.42)
        self.safe_swap(phase_c, takeaway)
        self.wait(1.6)
