from manim import *
from vivacity_base_scene import VivacityScene


class FundamentalTheoremRiemannScene(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        title = self.safe_title("How rectangles measure curved area")
        equation = self.safe_text(r"f(x)=x^2,\quad 0\le x\le 2", zone=None, font_size=30, color="#69d2ff")
        equation.next_to(title, DOWN, buff=0.16)
        self.safe_position(equation, "top")
        self.safe_add(title)
        self.play(Write(equation), run_time=0.8)

        axes = Axes(
            x_range=[0, 2.1, 0.5],
            y_range=[0, 4.5, 1],
            x_length=3.55,
            y_length=4.85,
            axis_config={"color": "#9aa8bb", "stroke_width": 2},
            tips=False,
        ).shift(DOWN * 0.04)
        x_label = self.safe_text("x", zone=None, font_size=25, color="#cbd5e1").next_to(axes.x_axis, RIGHT, buff=0.1)
        y_label = self.safe_text("y", zone=None, font_size=25, color="#cbd5e1").next_to(axes.y_axis, UP, buff=0.1)
        self.safe_position(x_label, "anchor")
        self.safe_position(y_label, "anchor")
        curve = axes.plot(lambda x: x**2, x_range=[0, 2], color="#69d2ff", stroke_width=5)
        curve_label = self.safe_text(r"y=x^2", zone=None, font_size=27, color="#69d2ff")
        curve_label.move_to(axes.c2p(1.35, 3.65))
        self.safe_position(curve_label, "anchor")

        self.play(Create(axes), Write(x_label), Write(y_label), run_time=1.0)
        self.play(Create(curve), FadeIn(curve_label), run_time=1.0)

        n_tracker = ValueTracker(4)
        n_values = [4, 8, 16, 32, 64]

        def midpoint_sum(n):
            dx = 2 / n
            return sum(((i + 0.5) * dx) ** 2 * dx for i in range(n))

        def rectangle_group(n):
            return axes.get_riemann_rectangles(
                curve,
                x_range=[0, 2],
                dx=2 / n,
                input_sample_type="center",
                stroke_color="#f7c948",
                stroke_width=0.7,
                fill_opacity=0.34,
                color="#f7c948",
            )

        rectangles = rectangle_group(4)

        n_display = Integer(4, color="#f7c948", font_size=29)
        n_display.add_updater(lambda mob: mob.set_value(int(round(n_tracker.get_value()))))
        sum_display = DecimalNumber(midpoint_sum(4), num_decimal_places=3, color="#ff9f68", font_size=27)
        sum_display.add_updater(lambda mob: mob.set_value(midpoint_sum(int(round(n_tracker.get_value())))))
        panel = VGroup(
            VGroup(MathTex("n=", color="#cbd5e1", font_size=27), n_display).arrange(RIGHT, buff=0.05),
            VGroup(MathTex("L_n=", color="#cbd5e1", font_size=27), sum_display).arrange(RIGHT, buff=0.05),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.07)
        panel.move_to(axes.c2p(0.28, 3.55))
        panel.add_background_rectangle(color="#111a2c", opacity=0.9, buff=0.1)

        step_caption = Tex("Each rectangle estimates one small slice of area.", color="#f4f7fb", font_size=21)
        step_caption.scale_to_fit_width(config.frame_width - 0.45)
        step_caption.to_edge(DOWN, buff=0.36)
        self._check_overlap(step_caption, "bottom")
        self.play(
            FadeIn(rectangles, shift=UP * 0.08),
            FadeIn(panel, shift=UP * 0.08),
            FadeIn(step_caption, shift=UP * 0.08),
            run_time=0.9,
        )
        self.wait(0.8)

        for previous, current in zip(n_values, n_values[1:]):
            new_rectangles = rectangle_group(current)
            self.safe_visual_transform(
                rectangles,
                new_rectangles,
                run_time=2.0,
                rate_func=smooth,
            )
            n_tracker.set_value(current)
            self.wait(1.0)

        self._remove_from_zone(step_caption, "bottom")
        self.play(FadeOut(step_caption), run_time=0.4)
        approx = self.safe_text(r"L_{64}\approx 2.667", zone=None, font_size=32, color="#ff9f68")
        approx.to_edge(DOWN, buff=0.55)
        self.safe_position(approx, "bottom")
        self.play(FadeIn(approx, shift=UP * 0.12), run_time=0.7)
        self.wait(0.8)

        exact = self.safe_text(r"\int_0^2 x^2\,dx=\frac{8}{3}", zone=None, font_size=34, color="#69d2ff")
        exact.move_to(approx)
        self.safe_swap(approx, exact, zone="bottom")
        self.wait(1.6)
