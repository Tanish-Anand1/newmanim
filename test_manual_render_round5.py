from manim import *
import sys

class SumOfOdds(Scene):
    def construct(self):
        self.camera.background_color = "#0e0f12"

        title = Tex("Sum of First $n$ Odd Integers = $n^2$", color="#e0e0e3")
        
        # Scale BEFORE positioning
        if title.width > (config.frame_width - 1.0):
            title.scale_to_fit_width(config.frame_width - 1.0)
            
        title.to_edge(UP, buff=0.4)
        self.play(Write(title))

        grid_group = VGroup()

        # Step 1: 1
        dot1 = Dot(color="#ffd43b", radius=0.2)
        grid_group.add(dot1)
        grid_group.move_to(ORIGIN).shift(DOWN * 1.2)
        
        eq1 = MathTex("1 = 1^2 = 1", font_size=32, color="#e0e0e3")
        if eq1.width > (config.frame_width - 1.0):
            eq1.scale_to_fit_width(config.frame_width - 1.0)
        eq1.next_to(title, DOWN, buff=0.4)
        
        self.play(FadeIn(dot1), Write(eq1))
        self.wait(1)

        # Step 2: 1 + 3 = 4
        dots2 = VGroup(
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, RIGHT, buff=0.2),
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, UP, buff=0.2),
            Dot(color="#cc99ff", radius=0.2).next_to(dot1, UR, buff=0.2)
        )
        grid_group.add(dots2)
        grid_group.move_to(ORIGIN).shift(DOWN * 1.2)

        eq2 = MathTex("1 + 3 = 2^2 = 4", font_size=32, color="#e0e0e3")
        if eq2.width > (config.frame_width - 1.0):
            eq2.scale_to_fit_width(config.frame_width - 1.0)
        eq2.next_to(title, DOWN, buff=0.4)

        self.play(FadeIn(dots2), TransformMatchingTex(eq1, eq2))
        self.wait(1)

        # Step 3: 1 + 3 + 5 = 9
        dots3 = VGroup()
        base_x = dot1.get_center()[0]
        base_y = dot1.get_center()[1]
        spacing = 0.6
        for i in range(3):
            dots3.add(Dot(color="#17dcfc", radius=0.2).move_to([base_x + 2*spacing, base_y + i*spacing, 0]))
            dots3.add(Dot(color="#17dcfc", radius=0.2).move_to([base_x + i*spacing, base_y + 2*spacing, 0]))
        dots3.add(Dot(color="#17dcfc", radius=0.2).move_to([base_x + 2*spacing, base_y + 2*spacing, 0]))

        grid_group.add(dots3)
        grid_group.move_to(ORIGIN).shift(DOWN * 1.2)

        eq3 = MathTex("1 + 3 + 5 = 3^2 = 9", font_size=32, color="#e0e0e3")
        if eq3.width > (config.frame_width - 1.0):
            eq3.scale_to_fit_width(config.frame_width - 1.0)
        eq3.next_to(title, DOWN, buff=0.4)

        self.play(FadeIn(dots3), TransformMatchingTex(eq2, eq3))
        self.wait(1)
        
        # Step 4: 1 + 3 + 5 + 7 = 16
        dots4 = VGroup()
        for i in range(4):
            dots4.add(Dot(color="#ff7c43", radius=0.2).move_to([base_x + 3*spacing, base_y + i*spacing, 0]))
            dots4.add(Dot(color="#ff7c43", radius=0.2).move_to([base_x + i*spacing, base_y + 3*spacing, 0]))
        dots4.add(Dot(color="#ff7c43", radius=0.2).move_to([base_x + 3*spacing, base_y + 3*spacing, 0]))

        grid_group.add(dots4)
        grid_group.move_to(ORIGIN).shift(DOWN * 1.2)

        eq4 = MathTex("1 + 3 + 5 + 7 = 4^2 = 16", font_size=32, color="#e0e0e3")
        if eq4.width > (config.frame_width - 1.0):
            eq4.scale_to_fit_width(config.frame_width - 1.0)
        eq4.next_to(title, DOWN, buff=0.4)

        self.play(FadeIn(dots4), TransformMatchingTex(eq3, eq4))
        self.wait(2)

        # Step 5: Generalize
        eq5 = MathTex("1 + 3 + 5 + ... + (2n-1) = n^2", font_size=40, color="#e0e0e3")
        if eq5.width > (config.frame_width - 1.0):
            eq5.scale_to_fit_width(config.frame_width - 1.0)
        eq5.next_to(title, DOWN, buff=0.4)
        
        # EXCEPTION for final transition as requested
        self.play(FadeOut(eq4, run_time=0.3))
        self.play(FadeIn(eq5, run_time=0.4))
        self.wait(2)

        sys.path.insert(0, r'C:\PROJECTS\newmanim')
        from app.render_acceptance import run_render_acceptance
        run_render_acceptance(self)
