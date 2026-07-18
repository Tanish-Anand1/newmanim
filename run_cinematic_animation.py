import uuid
import sys
import os
import inspect
from pathlib import Path
from sqlalchemy.orm import Session
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job
import app.pipeline
import app.craft_pipeline
from app.craft_pipeline import CraftVideoPlan, CraftBeatPlan

def custom_generate_storyboard_draft(topic, duration_seconds, audience, db=None, job_id=None, provider=None):
    storyboard_text = """# Approach: graph setup, critical points, area integration, circle construction, outro.
[0-12] ON SCREEN: Plot the curve f(x)=x^3-3x^2+4 for cinematic math animation analysis. Draw the horizontal minimum tangent line y=0. Mark P(-1,0) and (2,0). | VO: "We start our cinematic math animation analysis of the cubic by plotting it with its horizontal minimum tangent line."
[12-27] ON SCREEN: Write f'(x)=3x^2-6x=0 and solve to find critical points x=0 and x=2. Highlight them on the graph. | VO: "We locate the critical points at zero and two."
[27-45] ON SCREEN: Animate enclosed area shading and evaluation. Write the integral A=∫_{-1}^{2}(x^3-3x^2+4)dx. Evaluate to 27/4. | VO: "We show the enclosed area shading under the curve, and perform the integral evaluation."
[45-63] ON SCREEN: Solve inscribed circle tangency construction. Write |4-k|=k and solve for k=2. Draw the expanding circle. | VO: "For the inscribed circle tangency construction, we solve the distance relation."
[63-69] ON SCREEN: Fade out formulas and hold the full geometric diagram. | VO: "The final complete diagram."
"""
    return {"storyboard": storyboard_text}

def custom_generate_craft_plan(provider, storyboard, orientation, beat_numbers, db, job_id):
    beats = [
        CraftBeatPlan(beat_number=1, shape="PLOT_MATH_CURVE", param_title="Analyzing the Cubic"),
        CraftBeatPlan(beat_number=2, shape="TRANSFORM_EQUATION", param_title="Critical Points", param_old_eq="f(x)", param_new_eq="f'(x)=0"),
        CraftBeatPlan(beat_number=3, shape="TRANSFORM_EQUATION", param_title="Area Integration", param_old_eq="integral", param_new_eq="area"),
        CraftBeatPlan(beat_number=4, shape="TRANSFORM_EQUATION", param_title="Circle Construction", param_old_eq="radius", param_new_eq="r=2"),
        CraftBeatPlan(beat_number=5, shape="NONE")
    ]
    return CraftVideoPlan(beats=beats)

def custom_compile_craft_scene(scene_name, orientation, plan, project_root):
    # This returns the highly polished, cinematic 3Blue1Brown-style Manim script.
    code = f"""import sys
sys.path.insert(0, r'{project_root}')
from manim import *
from app.craft_library import CraftContext

class {scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0C0C0E"
        ctx = CraftContext(self, orientation='portrait')
        
        BG_COLOR = "#0C0C0E"
        TEAL_COLOR = "#2D9CDB"
        ORANGE_COLOR = "#F2994A"
        SAGE_COLOR = "#87A987"
        PURPLE_COLOR = "#BB6BD9"
        CREAM_COLOR = "#E0E0E0"
        
        # --- Beat 1: The Graphic Canvas ---
        # Narration target duration: 12 seconds
        # Section header sits strictly at UP * 3.8 (> UP * 2.5)
        # All equations strictly use relative positioning to prevent overlapping
        header1 = Text("Analyzing the Cubic", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        eq1 = MathTex("f(x) = x^3 - 3x^2 + 4", color=CREAM_COLOR).next_to(header1, DOWN, buff=0.6)
        
        # Grid/Axes setup, centered at DOWN * 0.2 initially
        axes = Axes(
            x_range=[-2.5, 3.5, 1],
            y_range=[-2.0, 5.0, 1],
            x_length=3.6,
            y_length=3.6,
            axis_config={{"color": CREAM_COLOR, "stroke_width": 2}},
            tips=False
        ).move_to(DOWN * 0.2)
        
        curve = axes.plot(lambda x: x**3 - 3*(x**2) + 4, x_range=[-1.15, 3.1], color=TEAL_COLOR)
        
        # Tangent line at minimum (x = 2) is y = 0
        tangent_line = Line(axes.c2p(-2.2, 0), axes.c2p(3.2, 0), color=ORANGE_COLOR, stroke_width=3)
        tangent_label = MathTex("y = 0", color=ORANGE_COLOR, font_size=24).next_to(axes.c2p(2.8, 0), UP, buff=0.1)
        
        p_dot = Dot(axes.c2p(-1, 0), color=ORANGE_COLOR, radius=0.08)
        p_label = MathTex("P(-1,0)", color=CREAM_COLOR, font_size=20).next_to(p_dot, DOWN, buff=0.15)
        
        min_dot = Dot(axes.c2p(2, 0), color=ORANGE_COLOR, radius=0.08)
        min_label = MathTex("(2,0)", color=CREAM_COLOR, font_size=20).next_to(min_dot, DOWN, buff=0.15)
        
        # Play Beat 1
        self.play(FadeIn(header1, shift=UP*0.2, run_time=1.0))
        self.play(FadeIn(eq1, scale=1.05, run_time=1.0))
        self.play(Create(axes, run_time=1.2))
        self.play(Create(curve, run_time=2.0))
        self.play(Create(tangent_line, run_time=1.2), FadeIn(tangent_label, scale=1.05, run_time=0.8))
        self.play(Create(p_dot, run_time=0.5), FadeIn(p_label, scale=1.05, run_time=0.5))
        self.play(Create(min_dot, run_time=0.5), FadeIn(min_label, scale=1.05, run_time=0.5))
        
        # Shift entire graph to lower 60% of the screen dynamically
        graph_group = VGroup(axes, curve, tangent_line, tangent_label, p_dot, p_label, min_dot, min_label)
        self.play(graph_group.animate.scale(0.85).move_to(DOWN * 1.6), run_time=2.0)
        self.wait(0.8)
        
        # --- Beat 2: Interactive Calculus ---
        # Narration target duration: 15 seconds
        header2 = Text("Critical Points", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        
        # Arrange derivations in vertical VGroup with 0.4 buff to prevent overlapping
        eq2_1 = MathTex("f'(x) = 3x^2 - 6x = 0", color=CREAM_COLOR)
        eq2_2 = MathTex("3x(x - 2) = 0", color=CREAM_COLOR)
        eq2_3 = MathTex("\\\\implies x = 0,\\\\quad x = 2", color=CREAM_COLOR)
        
        eq_group2 = VGroup(eq2_1, eq2_2, eq2_3).arrange(DOWN, buff=0.4)
        eq_group2.next_to(header2, DOWN, buff=0.5)
        
        # Local Max point highlight on curve
        max_dot = Dot(axes.c2p(0, 4), color=TEAL_COLOR, radius=0.08)
        max_label = MathTex("(0,4)", color=CREAM_COLOR, font_size=20).next_to(max_dot, UP, buff=0.15)
        
        # Play Beat 2
        self.play(
            FadeOut(header1, shift=UP*0.2),
            FadeOut(eq1, shift=UP*0.2),
            run_time=0.8
        )
        self.play(
            FadeIn(header2, shift=UP*0.2),
            run_time=0.8
        )
        self.play(FadeIn(eq2_1, scale=1.05, run_time=1.2))
        self.play(FadeIn(eq2_2, scale=1.05, run_time=1.0))
        self.play(FadeIn(eq2_3, scale=1.05, run_time=1.0))
        
        # Highlight maximum (0,4) and minimum (2,0)
        self.play(
            Create(max_dot),
            FadeIn(max_label, scale=1.05),
            Flash(min_dot, color=ORANGE_COLOR, line_length=0.15, num_lines=8, run_time=1.0),
            run_time=1.2
        )
        graph_group.add(max_dot, max_label)
        self.wait(8.6)
        
        # --- Beat 3: Integration and Shading ---
        # Narration target duration: 18 seconds
        header3 = Text("Area Integration", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        
        # Area shading
        area_shading = axes.get_area(curve, x_range=[-1, 2], color=SAGE_COLOR, opacity=0.25)
        
        eq3_1 = MathTex("A = \\\\int_{{-1}}^{{2}} (x^3 - 3x^2 + 4)\\\\,dx", color=CREAM_COLOR)
        eq3_2 = MathTex("= \\\\left[ \\\\frac{{x^4}}{{4}} - x^3 + 4x \\\\right]_{{-1}}^{{2}}", color=CREAM_COLOR)
        eq3_3 = MathTex("= 4 - \\\\left(-\\\\frac{{11}}{{4}}\\\\right) = \\\\frac{{27}}{{4}}", color=CREAM_COLOR)
        
        eq_group3 = VGroup(eq3_1, eq3_2, eq3_3).arrange(DOWN, buff=0.35).scale(0.75)
        eq_group3.to_edge(UP, buff=0.5)
        
        # Play Beat 3
        self.play(
            FadeOut(header2, shift=UP*0.2),
            FadeOut(eq_group2, shift=UP*0.2),
            run_time=0.8
        )
        self.play(
            FadeIn(header3, shift=UP*0.2),
            Create(area_shading, run_time=1.5),
            run_time=1.5
        )
        graph_group.add(area_shading)
        
        self.play(FadeOut(header3, shift=UP*0.2), run_time=0.8)
        self.play(FadeIn(eq3_1, scale=1.05, run_time=1.2))
        self.play(FadeIn(eq3_2, scale=1.05, run_time=1.5))
        self.play(FadeIn(eq3_3, scale=1.05, run_time=1.5))
        self.wait(11.5)
        
        # --- Beat 4: Geometric Circle Construction ---
        # Narration target duration: 18 seconds
        header4 = Text("Circle Construction", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        
        # Value tracker for expanding circle
        k_tracker = ValueTracker(0.5)
        circle = always_redraw(lambda: Circle(
            radius=axes.c2p(0, k_tracker.get_value())[1] - axes.c2p(0, 0)[1],
            color=PURPLE_COLOR,
            stroke_width=3
        ).move_to(axes.c2p(0, k_tracker.get_value())))
        
        eq4_1 = MathTex("|4 - k| = k", color=CREAM_COLOR)
        eq4_2 = MathTex("4 - k = k \\\\implies 2k = 4 \\\\implies k = 2", color=CREAM_COLOR)
        eq4_3 = MathTex("\\\\text{{Center: }} (0,2),\\\\quad r = 2", color=CREAM_COLOR)
        
        eq_group4 = VGroup(eq4_1, eq4_2, eq4_3).arrange(DOWN, buff=0.4)
        eq_group4.next_to(header4, DOWN, buff=0.5)
        
        # Play Beat 4
        self.play(
            FadeOut(header3, shift=UP*0.2),
            FadeOut(eq_group3, shift=UP*0.2),
            run_time=0.8
        )
        self.play(
            FadeIn(header4, shift=UP*0.2),
            FadeIn(circle, run_time=1.0),
            run_time=1.0
        )
        self.play(FadeIn(eq4_1, scale=1.05, run_time=1.2))
        
        # Dynamic solving and circle expansion
        self.play(
            FadeIn(eq4_2, scale=1.05, run_time=2.0),
            k_tracker.animate.set_value(2.0),
            run_time=3.0,
            rate_func=linear
        )
        self.play(FadeIn(eq4_3, scale=1.05, run_time=1.0))
        
        # Replace dynamic circle with a static circle for the outro
        final_circle = Circle(
            radius=axes.c2p(0, 2.0)[1] - axes.c2p(0, 0)[1],
            color=PURPLE_COLOR,
            stroke_width=3
        ).move_to(axes.c2p(0, 2.0))
        self.remove(circle)
        self.add(final_circle)
        graph_group.add(final_circle)
        self.wait(10.8)
        
        # --- Beat 5: Elegant Outro ---
        # Narration target duration: 6 seconds
        self.play(
            FadeOut(header4),
            FadeOut(eq_group4),
            run_time=1.0
        )
        self.play(
            graph_group.animate.scale(1.15).move_to(ORIGIN),
            run_time=2.0
        )
        self.wait(3.0)
"""
    return code

def main():
    # Patch the storyboard, plan, and compile functions
    app.pipeline.generate_storyboard_draft = custom_generate_storyboard_draft
    app.craft_pipeline.generate_craft_plan = custom_generate_craft_plan
    app.craft_pipeline.compile_craft_scene = custom_compile_craft_scene

    job_id = str(uuid.uuid4())
    topic = (
        "Cinematic math animation: f(x)=x^3-3x^2+4 analysis, horizontal minimum tangent, "
        "enclosed area shading and evaluation, inscribed circle tangency construction."
    )
    
    payload = {
        "topic": topic,
        "duration_seconds": 69,
        "audience": "Advanced High School Calculus Student",
        "scene_name": "CinematicCubicAnalysis",
        "orientation": "portrait",
        "pipeline_profile": "craft"
    }
    
    with SessionLocal() as db:
        job = Job(
            id=job_id,
            status=JobStatus.queued,
            job_kind="topic",
            pipeline_profile="craft",
            request_payload=payload,
            scene_name="CinematicCubicAnalysis",
            orientation="portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created cinematic custom job {job_id}")

    print("Running custom cinematic topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=69,
            audience="Advanced High School Calculus Student",
            scene_name="CinematicCubicAnalysis",
            orientation="portrait",
            pipeline_profile="craft"
        )
        print(f"Job {job_id} run completed successfully.")
    except Exception as e:
        print(f"Error running job {job_id}: {repr(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
