import uuid
import sys
import os
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job
import app.pipeline
import app.craft_pipeline
from app.craft_pipeline import CraftVideoPlan, CraftBeatPlan

def custom_generate_storyboard_draft(topic, duration_seconds, audience, db=None, job_id=None, provider=None):
    storyboard_text = """# Approach: graph setup, fundamental frequency, adding third harmonic, adding fifth harmonic, generalization, recall check.
[0-7.5] ON SCREEN: GRAPH: Empty axes. A sharp, alternating square wave (target function) in red appears. | VO: "Let's visually explore how a Fourier Series approximates a square wave by adding odd harmonics."
[7.5-18.0] ON SCREEN: GRAPH: Overlay the fundamental frequency sine wave (n=1) in teal. Text safe-zone: `f(t) \\approx \\frac{4}{\\pi} \\sin(t)`. | VO: "We start by overlaying the fundamental frequency sine wave, matching the square wave's period."
[18.0-23.25] ON SCREEN: GRAPH: Show individual third harmonic. Then transform to combined sum. Text safe-zone: `f(t) \\approx \\frac{4}{\\pi} \\left[ \\sin(t) + \\frac{1}{3} \\sin(3t) \\right]`. | VO: "Next, we add the third harmonic. The sum is shown, and the transition is perfectly fluid."
[23.25-32.5] ON SCREEN: GRAPH: Show individual fifth harmonic. Transform to combined sum. Text safe-zone: `f(t) \\approx \\frac{4}{\\pi} \\left[ \\sin(t) + \\frac{1}{3} \\sin(3t) + \\frac{1}{5} \\sin(5t) \\right]`. | VO: "Finally, we overlay the fifth harmonic, bringing the approximation closer to the corners."
[32.5-45.0] ON SCREEN: GRAPH: Show higher-order sum converging. Text safe-zone: `f(t) = \\frac{4}{\\pi} \\sum_{n=1,3,5,...}^{\\infty} \\frac{1}{n} \\sin(nt)`. | VO: "As we add more odd harmonics, the series converges to the sharp, alternating square wave."
[45.0-60.0] [RECALL_CHECKPOINT] ON SCREEN: GRAPH: Square wave. Question: "What is the next term in this series?" countdown timer in bottom zone. worked solution reveals `+\\frac{1}{7}\\sin(7t)`. | VO: "Pause and try this: What would be the next term to add to the series for an even sharper approximation?"
"""
    return {"storyboard": storyboard_text}

def custom_generate_craft_plan(provider, storyboard, orientation, beat_numbers, db, job_id):
    beats = [
        CraftBeatPlan(beat_number=1, shape="PLOT_MATH_CURVE", param_title="Square Wave"),
        CraftBeatPlan(beat_number=2, shape="TRANSFORM_EQUATION", param_title="Fundamental Wave", param_old_eq="Square", param_new_eq="n1"),
        CraftBeatPlan(beat_number=3, shape="TRANSFORM_EQUATION", param_title="Third Harmonic", param_old_eq="n1", param_new_eq="n3"),
        CraftBeatPlan(beat_number=4, shape="TRANSFORM_EQUATION", param_title="Fifth Harmonic", param_old_eq="n3", param_new_eq="n5"),
        CraftBeatPlan(beat_number=5, shape="TRANSFORM_EQUATION", param_title="Generalization", param_old_eq="n5", param_new_eq="sum"),
        CraftBeatPlan(beat_number=6, shape="NONE")
    ]
    return CraftVideoPlan(beats=beats)

def custom_compile_craft_scene(scene_name, orientation, plan, project_root):
    code = f"""import sys
sys.path.insert(0, r'{project_root}')
from manim import *
from app.craft_library import CraftContext

class {scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0C0C0E"
        ctx = CraftContext(self, orientation='portrait')
        
        BG_COLOR = "#0C0C0E"
        RED_COLOR = "#EB5757"     # Target Square Wave
        TEAL_COLOR = "#2D9CDB"    # Sum / Fundamental
        ORANGE_COLOR = "#F2994A"  # 3rd harmonic / Timer
        PURPLE_COLOR = "#BB6BD9"  # 5th harmonic / Solution
        CREAM_COLOR = "#E0E0E0"
        
        # --- Beat 1: Target Square Wave (0.0s - 7.5s) ---
        # Designated Math & Text Safe-Zone: Upper 45% (UP * 1.5 to UP * 3.0)
        # Designated Geometric Workspace: Lower 55% (DOWN * 0.5 to DOWN * 3.0)
        
        header1 = Text("Fourier Series", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        subtitle1 = Text("Target: Square Wave", font_size=22, color=RED_COLOR).next_to(header1, DOWN, buff=0.35)
        
        axes = Axes(
            x_range=[-3.5, 3.5, 1.5708],  # step size of pi/2
            y_range=[-2.0, 2.0, 1.0],
            x_length=4.2,
            y_length=3.0,
            axis_config={{"color": CREAM_COLOR, "stroke_width": 2}},
            tips=False
        ).move_to(DOWN * 1.5)
        
        # Construct exact sharp square wave corners using Line coordinates to prevent slope artifacts
        sq_points = [
            axes.c2p(-3.5, 1),
            axes.c2p(-3.1416, 1),
            axes.c2p(-3.1416, -1),
            axes.c2p(0, -1),
            axes.c2p(0, 1),
            axes.c2p(3.1416, 1),
            axes.c2p(3.1416, -1),
            axes.c2p(3.5, -1)
        ]
        sq_path = VMobject(color=RED_COLOR, stroke_width=4)
        sq_path.set_points_as_corners(sq_points)
        
        self.play(FadeIn(header1, shift=UP*0.2, run_time=1.0))
        self.play(FadeIn(subtitle1, scale=1.05, run_time=1.0))
        self.play(Create(axes, run_time=1.2))
        self.play(Create(sq_path, run_time=1.8))
        self.wait(2.5)  # Remaining wait for 7.5s Beat 1
        
        # --- Beat 2: Fundamental Wave Overlay (7.5s - 18.0s) ---
        header2 = Text("1st Harmonic", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        subtitle2 = Text("Fundamental Frequency", font_size=20, color=TEAL_COLOR).next_to(header2, DOWN, buff=0.35)
        eq2 = MathTex(
            "f(t) \\\\approx \\\\frac{{4}}{{\\\\pi}} \\\\sin(t)",
            color=TEAL_COLOR
        ).scale(0.85).move_to(UP * 2.2)
        
        fund_curve = axes.plot(
            lambda t: (4.0 / 3.14159) * np.sin(t),
            x_range=[-3.5, 3.5],
            color=TEAL_COLOR,
            stroke_width=3
        )
        
        self.play(
            FadeOut(subtitle1, shift=UP*0.1),
            run_time=0.5
        )
        self.play(
            Transform(header1, header2),
            FadeIn(subtitle2, shift=UP*0.1),
            FadeIn(eq2, scale=1.05),
            Create(fund_curve, run_time=2.0),
            run_time=2.0
        )
        self.wait(8.0)  # 1.25s breathing window + extra wait for 10.5s segment
        
        # --- Beat 3: Add Third Harmonic (18.0s - 23.25s) ---
        header3 = Text("3rd Harmonic Added", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        subtitle3 = Text("Adding Odd Harmonics", font_size=20, color=ORANGE_COLOR).next_to(header3, DOWN, buff=0.35)
        eq3 = MathTex(
            "f(t) \\\\approx \\\\frac{{4}}{{\\\\pi}} \\\\left[ \\\\sin(t) + \\\\frac{{1}}{{3}} \\\\sin(3t) \\\\right]",
            color=TEAL_COLOR
        ).scale(0.8).move_to(UP * 2.2)
        
        # Individual 3rd harmonic component
        h3_curve = axes.plot(
            lambda t: (4.0 / (3.0 * 3.14159)) * np.sin(3.0 * t),
            x_range=[-3.5, 3.5],
            color=ORANGE_COLOR,
            stroke_width=1.5
        ).set_opacity(0.6)
        
        # Sum of n=1 and n=3
        sum3_curve = axes.plot(
            lambda t: (4.0 / 3.14159) * (np.sin(t) + (1.0/3.0) * np.sin(3.0 * t)),
            x_range=[-3.5, 3.5],
            color=TEAL_COLOR,
            stroke_width=3
        )
        
        self.play(
            FadeOut(subtitle2, shift=UP*0.1),
            FadeOut(eq2, shift=UP*0.1),
            run_time=0.5
        )
        self.play(
            Transform(header1, header3),
            FadeIn(subtitle3, shift=UP*0.1),
            FadeIn(eq3, scale=1.05),
            Create(h3_curve, run_time=1.0),
            run_time=1.0
        )
        self.wait(0.5)
        self.play(
            ReplacementTransform(fund_curve, sum3_curve),
            FadeOut(h3_curve),
            run_time=1.25
        )
        self.wait(2.0)  # 1.25s breathing window + extra hold
        
        # --- Beat 4: Add Fifth Harmonic (23.25s - 32.5s) ---
        header4 = Text("5th Harmonic Added", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        subtitle4 = Text("Sharper Corner Fit", font_size=20, color=PURPLE_COLOR).next_to(header4, DOWN, buff=0.35)
        eq4 = MathTex(
            "f(t) \\\\approx \\\\frac{{4}}{{\\\\pi}} \\\\left[ \\\\sin(t) + \\\\frac{{1}}{{3}} \\\\sin(3t) + \\\\frac{{1}}{{5}} \\\\sin(5t) \\\\right]",
            color=TEAL_COLOR
        ).scale(0.72).move_to(UP * 2.2)
        
        # Individual 5th harmonic component
        h5_curve = axes.plot(
            lambda t: (4.0 / (5.0 * 3.14159)) * np.sin(5.0 * t),
            x_range=[-3.5, 3.5],
            color=PURPLE_COLOR,
            stroke_width=1.5
        ).set_opacity(0.6)
        
        # Sum of n=1, 3, 5
        sum5_curve = axes.plot(
            lambda t: (4.0 / 3.14159) * (np.sin(t) + (1.0/3.0) * np.sin(3.0 * t) + (1.0/5.0) * np.sin(5.0 * t)),
            x_range=[-3.5, 3.5],
            color=TEAL_COLOR,
            stroke_width=3
        )
        
        self.play(
            FadeOut(subtitle3, shift=UP*0.1),
            FadeOut(eq3, shift=UP*0.1),
            run_time=0.5
        )
        self.play(
            Transform(header1, header4),
            FadeIn(subtitle4, shift=UP*0.1),
            FadeIn(eq4, scale=1.05),
            Create(h5_curve, run_time=1.0),
            run_time=1.0
        )
        self.wait(0.5)
        self.play(
            ReplacementTransform(sum3_curve, sum5_curve),
            FadeOut(h5_curve),
            run_time=1.25
        )
        self.wait(5.5)  # 1.25s breathing window + hold
        
        # --- Beat 5: Summation & Generalization (32.5s - 45.0s) ---
        header5 = Text("General Fourier Series", font_size=36, color=CREAM_COLOR).move_to(UP * 3.8)
        subtitle5 = Text("Infinite Harmonics", font_size=20, color=CREAM_COLOR).next_to(header5, DOWN, buff=0.35)
        eq5 = MathTex(
            "f(t) = \\\\frac{{4}}{{\\\\pi}} \\\\sum_{{n=1,3,5,...}}^{{\\\\infty}} \\\\frac{{1}}{{n}} \\\\sin(nt)",
            color=TEAL_COLOR
        ).scale(0.8).move_to(UP * 2.2)
        
        # Large sum (up to n=19) to show a beautiful sharp approximation
        sum19_curve = axes.plot(
            lambda t: (4.0 / 3.14159) * sum((1.0 / n) * np.sin(float(n) * t) for n in range(1, 20, 2)),
            x_range=[-3.5, 3.5],
            color=TEAL_COLOR,
            stroke_width=3
        )
        
        self.play(
            FadeOut(subtitle4, shift=UP*0.1),
            FadeOut(eq4, shift=UP*0.1),
            run_time=0.5
        )
        self.play(
            Transform(header1, header5),
            FadeIn(subtitle5, shift=UP*0.1),
            FadeIn(eq5, scale=1.05),
            ReplacementTransform(sum5_curve, sum19_curve, run_time=2.0),
            run_time=2.0
        )
        self.wait(10.0)
        
        # --- Beat 6: Active Recall Checkpoint (45.0s - 60.0s) ---
        # Persistent layout: coordinate grid and curves remain in lower 55%
        # Use a VGroup so header + body are anchored together — no static overlap
        q_header = Text("Pause & Try This:", font_size=28, color=ORANGE_COLOR)
        q_body = Text("What is the next term in this series?", font_size=20, color=CREAM_COLOR)
        q_group = VGroup(q_header, q_body).arrange(DOWN, buff=0.3).move_to(UP * 2.9)
        
        self.play(
            FadeOut(header1),
            FadeOut(subtitle5),
            FadeOut(eq5),
            FadeIn(q_group, shift=UP*0.2),
            run_time=1.0
        )
        
        # Countdown timer anchored well below graph — at DOWN * 3.3 (bottom safe margin)
        timer_text = Text("Time Remaining: 5s", font_size=22, color=ORANGE_COLOR).move_to(DOWN * 3.3)
        self.play(FadeIn(timer_text))
        for sec in range(4, -1, -1):
            new_timer = Text(f"Time Remaining: {{sec}}s", font_size=22, color=ORANGE_COLOR).move_to(DOWN * 3.3)
            self.play(Transform(timer_text, new_timer), run_time=1.0)
            
        # worked solution — fade out entire question group first, then reveal answer
        sol_header = Text("Answer: 7th Harmonic", font_size=24, color=PURPLE_COLOR)
        sol_text = MathTex(
            "+\\\\frac{{1}}{{7}}\\\\sin(7t)",
            color=PURPLE_COLOR
        ).scale(1.1)
        sol_group = VGroup(sol_header, sol_text).arrange(DOWN, buff=0.3).move_to(UP * 2.9)
        
        self.play(
            FadeOut(timer_text),
            FadeOut(q_group),
            FadeIn(sol_group, scale=1.05),
            run_time=1.0
        )
        
        self.wait(8.0)

"""
    return code

def main():
    app.pipeline.generate_storyboard_draft = custom_generate_storyboard_draft
    app.craft_pipeline.generate_craft_plan = custom_generate_craft_plan
    app.craft_pipeline.compile_craft_scene = custom_compile_craft_scene

    job_id = str(uuid.uuid4())
    topic = (
        "Visually explain how a Fourier Series approximates a square wave by adding odd harmonics. "
        "Show the target function as a sharp, alternating square wave. Then, step-by-step, "
        "overlay the fundamental frequency sine wave, followed by the third harmonic, and finally the fifth harmonic."
    )
    
    payload = {
        "topic": topic,
        "duration_seconds": 60,
        "audience": "JEE aspirants",
        "scene_name": "FourierSquareWaveApproximation",
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
            scene_name="FourierSquareWaveApproximation",
            orientation="portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created custom Fourier Series job {job_id}")

    print("Running custom Fourier Series topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=60,
            audience="JEE aspirants",
            scene_name="FourierSquareWaveApproximation",
            orientation="portrait",
            pipeline_profile="craft"
        )
        print(f"Job {job_id} run completed successfully.")
        
        # Copy the final video to outputs/3.mp4
        job_runs_dir = Path("C:/PROJECTS/vivacity_job_runs") / job_id
        video_files = list(job_runs_dir.glob("*_FINAL.mp4"))
        if not video_files:
            video_files = list(job_runs_dir.glob("*.mp4"))
            
        if video_files:
            output_dir = Path("C:/PROJECTS/newmanim/outputs")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "3.mp4"
            shutil.copy(video_files[0], output_file)
            print(f"Successfully copied final video to {output_file}")
        else:
            print("Warning: Could not find rendered video in job runs folder.")
            
    except Exception as e:
        print(f"Error running job {job_id}: {repr(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
