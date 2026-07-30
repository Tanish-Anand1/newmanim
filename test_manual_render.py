from manim import *

class SumOfOdds(Scene):
    def construct(self):
        self.camera.background_color = "#1E1E1E"

        title = Text("Sum of First n Odd Integers = n²", font_size=36, color="#DDDDDD")
        title.to_edge(UP, buff=0.5)
        self.play(Write(title))

        grid_group = VGroup()
        equations = VGroup()

        # Step 1: 1
        dot1 = Dot(color="#ffd43b", radius=0.2)
        grid_group.add(dot1)
        grid_group.move_to(ORIGIN).shift(DOWN * 0.5)
        
        eq1 = MathTex("1 = 1^2 = 1", font_size=32, color="#DDDDDD")
        equations.add(eq1)
        equations.arrange(DOWN, buff=0.3).next_to(grid_group, DOWN, buff=1.0)
        
        self.play(FadeIn(dot1), Write(eq1))
        self.wait(1)

        # Step 2: 1 + 3 = 4
        dots2 = VGroup(
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, RIGHT, buff=0.2),
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, UP, buff=0.2),
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, UR, buff=0.2)
        )
        grid_group.add(dots2)
        grid_group.move_to(ORIGIN).shift(DOWN * 0.5)

        eq2 = MathTex("1 + 3 = 2^2 = 4", font_size=32, color="#DDDDDD")
        equations.add(eq2)
        equations.arrange(DOWN, buff=0.3).next_to(grid_group, DOWN, buff=1.0)

        self.play(FadeIn(dots2), Write(eq2))
        self.wait(1)

        # Step 3: 1 + 3 + 5 = 9
        dots3 = VGroup()
        for i in range(3):
            dots3.add(Dot(color="#3bffd4", radius=0.2).next_to(grid_group, RIGHT, buff=0.2).shift(UP * i * 0.6))
            dots3.add(Dot(color="#3bffd4", radius=0.2).next_to(grid_group, UP, buff=0.2).shift(RIGHT * i * 0.6))
        # The corner dot
        corner_dot = Dot(color="#3bffd4", radius=0.2)
        dots3.add(corner_dot)
        
        # We simplify adding L shape
        dots3_simple = VGroup()
        base_x = dot1.get_center()[0]
        base_y = dot1.get_center()[1]
        spacing = 0.6
        for i in range(3):
            dots3_simple.add(Dot(color="#3bffd4", radius=0.2).move_to([base_x + 2*spacing, base_y + i*spacing, 0]))
            dots3_simple.add(Dot(color="#3bffd4", radius=0.2).move_to([base_x + i*spacing, base_y + 2*spacing, 0]))
        dots3_simple.add(Dot(color="#3bffd4", radius=0.2).move_to([base_x + 2*spacing, base_y + 2*spacing, 0]))

        grid_group.add(dots3_simple)
        grid_group.move_to(ORIGIN).shift(DOWN * 0.5)

        eq3 = MathTex("1 + 3 + 5 = 3^2 = 9", font_size=32, color="#DDDDDD")
        equations.add(eq3)
        equations.arrange(DOWN, buff=0.3).next_to(grid_group, DOWN, buff=1.0)

        self.play(FadeIn(dots3_simple), Write(eq3))
        self.wait(1)

        # Step 4: Generalize
        eq4 = MathTex("1 + 3 + 5 + ... + (2n-1) = n^2", font_size=36, color="#ffb84d")
        eq4.next_to(equations, DOWN, buff=0.5)
        self.play(Write(eq4))
        self.wait(2)
