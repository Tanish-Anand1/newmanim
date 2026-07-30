from manim import *
import numpy as np
from vivacity_base_scene import VivacityScene

class DerivativeDefinition(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        # Title
        title = Text("Derivative of x^2 at x=3 using Definition", font_size=36)
        title.to_edge(UP)
        self.play(FadeIn(title))
        self.wait(1)

        # Function definition
        f_equal = MathTex("f(x) = x^2")
        f_equal.next_to(title, DOWN, buff=0.5)
        self.play(FadeIn(f_equal))
        self.wait(0.5)

        # Definition of derivative
        def_def = MathTex("f'(a) = \\lim_{h \\to 0} \\frac{f(a+h) - f(a)}{h}")
        def_def.next_to(f_equal, DOWN, buff=0.8)
        self.play(FadeIn(def_def))
        self.wait(0.5)

        # Substitute a=3, f(x)=x^2
        sub1 = MathTex("f'(3) = \\lim_{h \\to 0} \\frac{(3+h)^2 - 3^2}{h}")
        sub1.next_to(def_def, DOWN, buff=0.8)
        self.play(FadeIn(sub1))
        self.wait(0.5)

        # Expand numerator
        expand = MathTex("f'(3) = \\lim_{h \\to 0} \\frac{9 + 6h + h^2 - 9}{h}")
        expand.next_to(sub1, DOWN, buff=0.6)
        self.play(FadeIn(expand))
        self.wait(0.5)

        # Simplify
        simplify = MathTex("f'(3) = \\lim_{h \\to 0} \\frac{6h + h^2}{h}")
        simplify.next_to(expand, DOWN, buff=0.6)
        self.play(FadeIn(simplify))
        self.wait(0.5)

        # Factor h
        factor = MathTex("f'(3) = \\lim_{h \\to 0} \\frac{h(6 + h)}{h}")
        factor.next_to(simplify, DOWN, buff=0.6)
        self.play(FadeIn(factor))
        self.wait(0.5)

        # Cancel h (assuming h ≠ 0)
        cancel = MathTex("f'(3) = \\lim_{h \\to 0} (6 + h)")
        cancel.next_to(factor, DOWN, buff=0.6)
        self.play(FadeIn(cancel))
        self.wait(0.5)

        # Take limit
        result = MathTex("f'(3) = 6")
        result.next_to(cancel, DOWN, buff=0.8)
        result.set_color(GREEN)
        self.play(FadeIn(result))
        self.wait(1)

        # Summary
        summary = Text("The derivative of x^2 at x=3 is 6.", font_size=28)
        summary.next_to(result, DOWN, buff=0.8)
        self.play(FadeIn(summary))
        self.wait(2)

        # Fade out
        self.play(*[FadeOut(mob) for mob in self.mobjects])
