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
    storyboard_text = """# Approach: graph setup, linear approximation, cubic correction, generalizing pattern.
[0-12] ON SCREEN: Plot f(x)=sin(x) on a coordinate grid. Lock the grid to the lower 55% of the frame. Add floating text f(x)=sin(x). | VO: "We start by plotting the target function sine of x on a fixed coordinate grid."
[12-27] ON SCREEN: Fade in title 'Linear Approximation (n=1)' and P1(x)=x in the top safe-zone. Draw orange tangent line y=x. | VO: "Next, we draw the first-degree linear approximation, which matches the slope at the origin."
[27-45] ON SCREEN: Replace n=1 text with title 'Cubic Correction (n=3)' and P3(x)=x-x^3/6. Morph orange line into amethyst purple cubic curve. | VO: "Adding a cubic correction gives us a cubic curve that hugs the sine wave further out."
[45-60] ON SCREEN: Clear the top safe-zone. Display summation formula f(x)=sum_{n=0}^{infty} f^(n)(0)/n! * x^n scaled to 0.8. | VO: "Generalizing this pattern yields the Taylor series expansion around zero."
"""
    return {"storyboard": storyboard_text}

def custom_generate_craft_plan(provider, storyboard, orientation, beat_numbers, db, job_id):
    beats = [
        CraftBeatPlan(beat_number=1, shape="PLOT_MATH_CURVE", param_title="Sine Wave"),
        CraftBeatPlan(beat_number=2, shape="TRANSFORM_EQUATION", param_title="Linear Approximation", param_old_eq="sin(x)", param_new_eq="P1(x)=x"),
        CraftBeatPlan(beat_number=3, shape="TRANSFORM_EQUATION", param_title="Cubic Correction", param_old_eq="P1(x)", param_new_eq="P3(x)"),
        CraftBeatPlan(beat_number=4, shape="TRANSFORM_EQUATION", param_title="Generalization", param_old_eq="P3(x)", param_new_eq="sum"),
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
        PURPLE_COLOR = "#BB6BD9"
        CREAM_COLOR = "#E0E0E0"
        
        # --- Beat 1: Target Function ---
        # Coordinate grid locked to the lower 55% of the frame (centered at DOWN * 1.5)
        # Designated upper 45% is the safe-zone for text (centered around UP * 2.2)
        
        header1 = Text("Target Function", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        eq1 = MathTex("f(x) = \\\\sin(x)", color=TEAL_COLOR).next_to(header1, DOWN, buff=0.4)
        
        axes = Axes(
            x_range=[-3.5, 3.5, 1],
            y_range=[-2.0, 2.0, 1],
            x_length=3.8,
            y_length=2.8,
            axis_config={{"color": CREAM_COLOR, "stroke_width": 2}},
            tips=False
        ).move_to(DOWN * 1.5)
        
        curve = axes.plot(lambda x: np.sin(x), x_range=[-3.2, 3.2], color=TEAL_COLOR)
        curve_label = MathTex("f(x) = \\\\sin(x)", color=TEAL_COLOR, font_size=20).next_to(axes.c2p(2.2, np.sin(2.2)), UR, buff=0.1)
        
        self.play(FadeIn(header1, shift=UP*0.2, run_time=1.0))
        self.play(FadeIn(eq1, scale=1.05, run_time=1.0))
        self.play(Create(axes, run_time=1.2))
        self.play(Create(curve, run_time=2.0), FadeIn(curve_label, scale=1.05, run_time=1.0))
        
        # Lock coordinates/visuals in place
        graph_group = VGroup(axes, curve, curve_label)
        self.wait(5.8)
        
        # --- Beat 2: Linear Approximation (n=1) ---
        header2 = Text("Linear Approximation", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        eq2 = MathTex("P_1(x) = x", color=ORANGE_COLOR).next_to(header2, DOWN, buff=0.4)
        
        # y = x tangent line
        tangent_line = Line(
            axes.c2p(-1.5, -1.5),
            axes.c2p(1.5, 1.5),
            color=ORANGE_COLOR,
            stroke_width=3
        )
        
        self.play(
            FadeOut(header1, shift=UP*0.2),
            FadeOut(eq1, shift=UP*0.2),
            run_time=0.8
        )
        self.play(
            FadeIn(header2, shift=UP*0.2),
            FadeIn(eq2, scale=1.05),
            Create(tangent_line, run_time=1.5),
            run_time=1.5
        )
        graph_group.add(tangent_line)
        self.wait(10.2)
        
        # --- Beat 3: Cubic Correction (n=3) ---
        header3 = Text("Cubic Correction", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        eq3 = MathTex("P_3(x) = x - \\\\frac{{x^3}}{{6}}", color=PURPLE_COLOR).next_to(header3, DOWN, buff=0.4)
        
        # Cubic curve
        cubic_curve = axes.plot(lambda x: x - (x**3)/6.0, x_range=[-2.4, 2.4], color=PURPLE_COLOR)
        
        self.play(
            FadeOut(header2, shift=UP*0.2),
            FadeOut(eq2, shift=UP*0.2),
            run_time=0.8
        )
        self.play(
            FadeIn(header3, shift=UP*0.2),
            FadeIn(eq3, scale=1.05),
            ReplacementTransform(tangent_line, cubic_curve, run_time=2.0),
            run_time=2.0
        )
        graph_group.remove(tangent_line)
        graph_group.add(cubic_curve)
        self.wait(10.2)
        
        # --- Beat 4: Generalization ---
        # Clear the top safe-zone
        self.play(
            FadeOut(header3, shift=UP*0.2),
            FadeOut(eq3, shift=UP*0.2),
            run_time=0.8
        )
        
        # Global summation formula scaled to 0.8 to fit perfectly in the top 45%
        summation = MathTex(
            "f(x) = \\\\sum_{{n=0}}^{{\\\\infty}} \\\\frac{{f^{{(n)}}(0)}}{{n!}} x^n",
            color=CREAM_COLOR
        ).scale(0.8).move_to(UP * 2.4)
        
        self.play(FadeIn(summation, scale=1.05, run_time=1.5))
        self.wait(12.7)
        
        # Outro
        self.play(
            FadeOut(summation, shift=UP*0.2),
            run_time=1.0
        )
        self.play(
            graph_group.animate.scale(1.2).move_to(ORIGIN),
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
        "Taylor series of sin(x) around a=0 (Maclaurin expansion), vertical aspect ratio, "
        "lock coordinate grid to lower 55%, safe-zone in upper 45%, n=1 orange tangent, "
        "n=3 purple cubic morph, global summation formula scaled to 0.8."
    )
    
    payload = {
        "topic": topic,
        "duration_seconds": 60,
        "audience": "Advanced High School Calculus Student",
        "scene_name": "TaylorSinExpansion",
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
            scene_name="TaylorSinExpansion",
            orientation="portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created custom Taylor Series job {job_id}")

    print("Running custom Taylor Series topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=60,
            audience="Advanced High School Calculus Student",
            scene_name="TaylorSinExpansion",
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
