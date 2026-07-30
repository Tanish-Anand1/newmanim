from manim import *
from vivacity_base_scene import VivacityScene


class AreaUnderXSquared(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        title = Tex("Why does the area under", color="#f4f7fb", font_size=34)
        formula_title = MathTex(r"y=x^2", color="#69d2ff", font_size=42)
        heading = VGroup(title, formula_title).arrange(RIGHT, buff=0.18)
        heading.scale_to_fit_width(config.frame_width - 0.8)
        heading.to_edge(UP, buff=0.38)
        assert heading.width <= config.frame_width - 0.4
        self.play(Write(title), Write(formula_title), run_time=1.6)
        self.wait(0.5)

        axes = Axes(
            x_range=[0, 1.05, 0.25],
            y_range=[0, 1.08, 0.25],
            x_length=3.4,
            y_length=4.5,
            axis_config={"color": "#aab4c4", "stroke_width": 2},
            tips=False,
        ).shift(DOWN * 0.45)
        x_label = MathTex("x", color="#cbd5e1", font_size=28).next_to(axes.x_axis, RIGHT, buff=0.12)
        y_label = MathTex("y", color="#cbd5e1", font_size=28).next_to(axes.y_axis, UP, buff=0.12)
        graph = axes.plot(lambda x: x**2, x_range=[0, 1], color="#69d2ff", stroke_width=5)
        curve_label = MathTex("y=x^2", color="#69d2ff", font_size=30)
        curve_label.move_to(axes.c2p(0.72, 0.78))
        graph_group = VGroup(axes, x_label, y_label, graph, curve_label)

        self.play(Create(axes), Write(x_label), Write(y_label), run_time=1.2)
        self.play(Create(graph), FadeIn(curve_label), run_time=1.3)
        self.wait(0.6)

        area_label = Tex("The shaded region is the area we want.", color="#f4f7fb", font_size=25)
        area_label.next_to(axes, DOWN, buff=0.38)
        self.play(FadeIn(area_label, shift=UP * 0.12), run_time=0.7)
        self.wait(0.5)

        rect4 = axes.get_riemann_rectangles(
            graph, x_range=[0, 1], dx=0.25, input_sample_type="left",
            stroke_color="#f7c948", stroke_width=1.5,
            fill_opacity=0.42, color="#f7c948",
        )
        count4 = MathTex("4", color="#f7c948", font_size=34)
        count4.move_to(axes.c2p(0.08, 0.86))
        self.play(Create(rect4), FadeIn(count4), run_time=1.2)
        self.wait(0.6)

        rect8 = axes.get_riemann_rectangles(
            graph, x_range=[0, 1], dx=0.125, input_sample_type="left",
            stroke_color="#b18cff", stroke_width=1.0,
            fill_opacity=0.38, color="#b18cff",
        )
        count8 = MathTex("8", color="#b18cff", font_size=34).move_to(count4)
        self.safe_visual_transform(rect4, rect8, run_time=1.0)
        self.safe_swap(count4, count8)
        self.wait(0.5)

        rect16 = axes.get_riemann_rectangles(
            graph, x_range=[0, 1], dx=0.0625, input_sample_type="left",
            stroke_color="#ff8a65", stroke_width=0.8,
            fill_opacity=0.32, color="#ff8a65",
        )
        count16 = MathTex("16", color="#ff8a65", font_size=34).move_to(count8)
        self.safe_visual_transform(rect4, rect16, run_time=1.0)
        self.safe_swap(count8, count16)
        self.wait(0.6)

        n_label = MathTex(r"n\to\infty", color="#f7c948", font_size=34)
        n_label.move_to(count16)
        self.safe_swap(count16, n_label)
        self.wait(0.5)

        self.play(
            FadeOut(area_label),
            FadeOut(rect4),
            FadeOut(n_label),
            FadeOut(graph_group),
            run_time=0.7,
        )

        integral = MathTex(r"A=\int_0^1 x^2\,dx", color="#f4f7fb", font_size=42)
        integral.move_to(axes.get_center())
        self.play(Write(integral), run_time=1.0)
        self.wait(0.7)

        result = MathTex(r"A=\left[\frac{x^3}{3}\right]_0^1=\frac{1}{3}", color="#69d2ff", font_size=42)
        result.move_to(integral)
        self.safe_swap(integral, result)
        self.wait(1.2)

        takeaway = Tex("More rectangles reveal the curve's exact area.", color="#f4f7fb", font_size=22)
        takeaway.scale_to_fit_width(config.frame_width - 0.45)
        takeaway.next_to(axes, DOWN, buff=0.4)
        self.play(FadeIn(takeaway, shift=UP * 0.12), run_time=0.8)
        self.wait(1.5)
