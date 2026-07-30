from manim import *
from vivacity_base_scene import VivacityScene


class MaximumAreaUnderParabolaScene(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        title = self.safe_title("Maximum rectangle area under a parabola")
        subtitle = self.safe_text(r"y=12-x^2", zone=None, font_size=32, color="#69d2ff")
        subtitle.next_to(title, DOWN, buff=0.14)
        self.safe_position(subtitle, "top")
        self.safe_add(title)
        self.play(Write(subtitle), run_time=0.9)
        self.wait(0.45)

        axes = Axes(
            x_range=[-4, 4, 1],
            y_range=[0, 13, 2],
            x_length=3.7,
            y_length=4.7,
            axis_config={"color": "#9aa8bb", "stroke_width": 2},
            tips=False,
        ).shift(DOWN * 0.45)
        x_label = self.safe_text("x", zone=None, font_size=24, color="#cbd5e1").next_to(axes.x_axis, RIGHT, buff=0.1)
        y_label = self.safe_text("y", zone=None, font_size=24, color="#cbd5e1").next_to(axes.y_axis, UP, buff=0.1)
        self.safe_position(x_label, "anchor")
        self.safe_position(y_label, "anchor")
        curve = axes.plot(lambda x: 12 - x**2, x_range=[-3.46, 3.46], color="#69d2ff", stroke_width=5)
        curve_label = self.safe_text(r"y=12-x^2", zone=None, font_size=24, color="#69d2ff")
        # Keep the equation label above the arc so it never sits on the curve.
        curve_label.move_to(axes.c2p(2.0, 10.6))
        self.safe_position(curve_label, "anchor")

        self.play(Create(axes), Write(x_label), Write(y_label), run_time=1.2)
        self.play(Create(curve), FadeIn(curve_label, shift=UP * 0.12), run_time=1.5)

        half_width = ValueTracker(0.8)

        def rectangle_shape():
            a = half_width.get_value()
            h = max(0.05, 12 - a**2)
            return Polygon(
                axes.c2p(-a, 0), axes.c2p(a, 0),
                axes.c2p(a, h), axes.c2p(-a, h),
                stroke_color="#f7c948", stroke_width=2,
                fill_color="#f7c948", fill_opacity=0.34,
            )

        rectangle = always_redraw(rectangle_shape)

        boundary_dot = always_redraw(
            lambda: Dot(
                axes.c2p(
                    half_width.get_value(),
                    max(0.05, 12 - half_width.get_value() ** 2),
                ),
                radius=0.065,
                color="#ff9f68",
            )
        )

        width_label = MathTex(r"2a", color="#f7c948", font_size=26)
        width_label.add_updater(lambda mob: mob.move_to(axes.c2p(0, -0.65)))
        height_label = MathTex(r"12-a^2", color="#ff9f68", font_size=24)
        height_label.add_updater(
            lambda mob: mob.next_to(
                axes.c2p(half_width.get_value(), max(0.05, 12 - half_width.get_value() ** 2) * 0.5),
                RIGHT,
                buff=0.12,
            )
        )
        dimensions = VGroup(width_label, height_label)

        area_value = DecimalNumber(2 * 0.8 * (12 - 0.8**2), num_decimal_places=1, color="#ff9f68", font_size=25)
        area_value.add_updater(
            lambda mob: mob.set_value(2 * half_width.get_value() * (12 - half_width.get_value() ** 2))
        )
        a_value = DecimalNumber(0.8, num_decimal_places=1, color="#f7c948", font_size=25)
        a_value.add_updater(lambda mob: mob.set_value(half_width.get_value()))
        panel = VGroup(
            VGroup(MathTex("a=", color="#cbd5e1", font_size=25), a_value).arrange(RIGHT, buff=0.05),
            VGroup(MathTex("A=", color="#cbd5e1", font_size=25), area_value).arrange(RIGHT, buff=0.05),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.05)
        panel.move_to(axes.c2p(-2.5, 10.8))
        panel.add_background_rectangle(color="#111a2c", opacity=0.9, buff=0.1)

        caption = Tex("Move the sides: the area changes continuously.", color="#f4f7fb", font_size=21)
        caption.scale_to_fit_width(config.frame_width - 0.45)
        caption.to_edge(DOWN, buff=0.35)
        self._check_overlap(caption, "bottom")
        self.play(
            FadeIn(rectangle),
            FadeIn(boundary_dot),
            FadeIn(dimensions),
            FadeIn(panel),
            FadeIn(caption),
            run_time=1.0,
        )
        self.wait(0.7)

        self.play(half_width.animate.set_value(1.5), run_time=2.6, rate_func=smooth)
        self.play(half_width.animate.set_value(2.0), run_time=2.2, rate_func=smooth)
        self.wait(0.8)

        focus = Tex("The largest rectangle occurs when the area stops increasing.", color="#f4f7fb", font_size=20)
        focus.scale_to_fit_width(config.frame_width - 0.42)
        focus.to_edge(DOWN, buff=0.35)
        self._remove_from_zone(caption, "bottom")
        self.play(FadeOut(caption), FadeIn(focus), run_time=0.7)
        self._check_overlap(focus, "bottom")
        self.play(half_width.animate.set_value(2.45), run_time=1.8, rate_func=smooth)
        self.play(half_width.animate.set_value(2.0), run_time=1.8, rate_func=smooth)
        self.wait(0.7)

        area_formula = self.safe_text(r"A(a)=2a(12-a^2)", zone=None, font_size=34, color="#f4f7fb")
        area_formula.to_edge(DOWN, buff=0.45)
        self._remove_from_zone(focus, "bottom")
        self.safe_position(area_formula, "bottom")
        self.play(FadeOut(focus), FadeIn(area_formula), run_time=0.8)
        self.wait(0.8)

        derivative = self.safe_text(r"A'(a)=24-6a^2=0\quad\Rightarrow\quad a=2", zone=None, font_size=31, color="#69d2ff")
        derivative.move_to(area_formula)
        self.safe_swap(area_formula, derivative, zone="bottom")
        self.wait(1.0)

        result = self.safe_text(r"\boxed{A_{\max}=32}", zone=None, font_size=38, color="#f7c948")
        result.move_to(derivative)
        self.safe_swap(derivative, result, zone="bottom")
        self.wait(1.8)
