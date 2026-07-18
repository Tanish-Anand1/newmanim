# These snippets are VERIFIED WORKING on Manim CE 0.20.1.
# The backend selects only the categories that match the storyboard.

from manim import *
import numpy as np


# CATEGORY: force-diagrams
class ForceTriangleIncline(Scene):
    def construct(self):
        plane = Line(LEFT * 3, RIGHT * 3).rotate(25 * DEGREES)
        block = Square(side_length=0.8).rotate(25 * DEGREES).move_to(plane.point_from_proportion(0.55) + UP * 0.35)
        weight = Arrow(block.get_center(), block.get_center() + DOWN * 1.8, buff=0, color=YELLOW)
        normal = Arrow(block.get_center(), block.get_center() + plane.copy().rotate(90 * DEGREES).get_unit_vector() * 1.4, buff=0, color=BLUE)
        parallel = Arrow(block.get_center(), block.get_center() + plane.get_unit_vector() * 1.5, buff=0, color=GREEN)
        labels = VGroup(
            MathTex("mg").next_to(weight, DOWN, buff=0.15),
            MathTex("N").next_to(normal, UP, buff=0.15),
            MathTex("mg\\sin\\theta").next_to(parallel, RIGHT, buff=0.15),
        )
        self.play(Create(plane), FadeIn(block))
        self.play(GrowArrow(weight), GrowArrow(normal), GrowArrow(parallel), Write(labels))
        self.wait(1)


# CATEGORY: force-diagrams
class FreeBodyDiagram(Scene):
    def construct(self):
        dot = Dot()
        force_right = Arrow(dot.get_center(), RIGHT * 2, buff=0, color=GREEN)
        force_left = Arrow(dot.get_center(), LEFT * 1.5, buff=0, color=RED)
        force_up = Arrow(dot.get_center(), UP * 1.4, buff=0, color=BLUE)
        force_down = Arrow(dot.get_center(), DOWN * 1.8, buff=0, color=YELLOW)
        labels = VGroup(
            MathTex("F").next_to(force_right, RIGHT),
            MathTex("f").next_to(force_left, LEFT),
            MathTex("N").next_to(force_up, UP),
            MathTex("mg").next_to(force_down, DOWN),
        )
        self.play(FadeIn(dot))
        self.play(*(GrowArrow(arrow) for arrow in [force_right, force_left, force_up, force_down]))
        self.play(Write(labels))
        self.wait(1)


# CATEGORY: curve-plotting
class ParabolaPlot(Scene):
    def construct(self):
        axes = Axes(x_range=[-3, 3, 1], y_range=[0, 5, 1], x_length=6, y_length=4)
        graph = axes.plot(lambda x: x**2, color=BLUE_C)
        label = MathTex("y=x^2").next_to(graph.point_from_proportion(0.8), RIGHT, buff=0.2)
        self.play(Create(axes))
        self.play(Create(graph), Write(label))
        self.wait(1)


# CATEGORY: curve-plotting
class SineApproximation(Scene):
    def construct(self):
        axes = Axes(x_range=[-4, 4, 1], y_range=[-2, 2, 1], x_length=7, y_length=4)
        sine = axes.plot(lambda x: np.sin(x), color=TEAL)
        tangent = axes.plot(lambda x: x, x_range=[-1.5, 1.5], color=ORANGE)
        labels = VGroup(
            MathTex("\\sin x").next_to(sine.point_from_proportion(0.72), UP, buff=0.2),
            MathTex("x").next_to(tangent.point_from_proportion(0.8), RIGHT, buff=0.2),
        )
        self.play(Create(axes))
        self.play(Create(sine), Create(tangent), Write(labels))
        self.wait(1)


# CATEGORY: algebraic-stepwise
class AlgebraStepTransform(Scene):
    def construct(self):
        line1 = MathTex("F_{net}=ma").scale(1.1)
        line2 = MathTex("mg\\sin\\theta=ma").scale(1.1)
        line3 = MathTex("a=g\\sin\\theta").scale(1.1)
        self.play(Write(line1))
        self.play(ReplacementTransform(line1, line2))
        self.play(ReplacementTransform(line2, line3))
        self.wait(1)


# CATEGORY: algebraic-stepwise
class EquationStack(Scene):
    def construct(self):
        steps = VGroup(
            MathTex("(a+b)^2"),
            MathTex("=a^2+2ab+b^2"),
            MathTex("\\therefore\\ (a+b)^2=a^2+2ab+b^2"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        self.play(Write(steps[0]))
        self.play(Write(steps[1]))
        self.play(Write(steps[2]))
        self.wait(1)


# CATEGORY: geometric-proof
class SimilarTriangles(Scene):
    def construct(self):
        tri1 = Polygon(LEFT * 3 + DOWN, LEFT + DOWN, LEFT * 3 + UP, color=BLUE)
        tri2 = Polygon(RIGHT + DOWN, RIGHT * 3 + DOWN, RIGHT + UP, color=GREEN)
        labels = VGroup(
            MathTex("\\triangle ABC").next_to(tri1, DOWN, buff=0.2),
            MathTex("\\triangle PQR").next_to(tri2, DOWN, buff=0.2),
        )
        self.play(Create(tri1), Create(tri2))
        self.play(Write(labels))
        self.wait(1)


# CATEGORY: geometric-proof
class CircleChordProof(Scene):
    def construct(self):
        circle = Circle(radius=2)
        chord = Line(circle.point_at_angle(35 * DEGREES), circle.point_at_angle(145 * DEGREES), color=YELLOW)
        radius1 = Line(ORIGIN, chord.get_start(), color=BLUE)
        radius2 = Line(ORIGIN, chord.get_end(), color=BLUE)
        angle = Angle(radius1, radius2, radius=0.55, color=ORANGE)
        label = MathTex("\\theta").next_to(angle, UP, buff=0.15)
        self.play(Create(circle), Create(chord))
        self.play(Create(radius1), Create(radius2), Create(angle), Write(label))
        self.wait(1)
