"""
run_chaos_game_job.py
─────────────────────────────────────────────────────
Custom runner: Chaos Game → Sierpinski Triangle.

Layout invariants:
  Upper safe-zone  UP * 1.5 → UP * 3.8  : all text, counters, formulas
  Lower workspace  DOWN * 0.5 → DOWN * 3.5 : triangle, dots only

Text collision prevention:
  Every text element is built via VGroup(...).arrange(DOWN, buff=N)
  No two independent objects share a static UP * N address.
"""

import uuid
import sys
import os
import shutil
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.orm import Session
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job
import app.pipeline
import app.craft_pipeline
from app.craft_pipeline import CraftVideoPlan, CraftBeatPlan

# ─────────────────────────────────────────────────────────────────────────────
# STORYBOARD MOCK
# ─────────────────────────────────────────────────────────────────────────────

def custom_generate_storyboard_draft(topic, duration_seconds, audience, db=None, job_id=None, provider=None):
    storyboard_text = """# Approach: triangle setup, explicit midpoint steps, rapid chaos game generation, fractal reveal, recall checkpoint.
[0-6] ON SCREEN: Title card and rule description in upper safe-zone. | VO: "Welcome to the Chaos Game. One simple rule draws a perfect fractal."
[6-14] ON SCREEN: GRAPH: Equilateral triangle with labelled vertices A, B, C in geometric workspace. Random starting point placed. | VO: "Start with an equilateral triangle. Drop a random point inside."
[14-26] ON SCREEN: GRAPH: Five explicit steps shown. Random vertex chosen each time. Dotted line drawn to vertex. Midpoint plotted and marked. | VO: "Pick a random vertex. Move halfway toward it. Mark the midpoint. Repeat."
[26-38] ON SCREEN: GRAPH: Rapid point generation phase. Step counter in upper zone climbs from 5 to 600. Fractal pattern emerges. | VO: "Watch what happens when we accelerate. Hundreds of points. Same rule."
[38-50] ON SCREEN: GRAPH: Full fractal dot cloud visible. Probability formula in upper safe-zone. | VO: "The Sierpinski Triangle. An infinitely self-similar fractal born from pure randomness."
[50-60] [RECALL_CHECKPOINT] ON SCREEN: GRAPH: Hollow central triangle highlighted in red. Question prompt in upper zone. Answer revealed after 5 seconds. | VO: "Which region is permanently empty? Pause and think before the answer appears."
"""
    return {"storyboard": storyboard_text}

def custom_generate_craft_plan(provider, storyboard, orientation, beat_numbers, db, job_id):
    beats = [
        CraftBeatPlan(beat_number=1, shape="TEXT_INTRO",       param_title="Chaos Game Rules"),
        CraftBeatPlan(beat_number=2, shape="PLOT_GEOMETRY",    param_title="Equilateral Triangle"),
        CraftBeatPlan(beat_number=3, shape="EXPLICIT_STEPS",   param_title="5 Midpoint Steps"),
        CraftBeatPlan(beat_number=4, shape="RAPID_GENERATION", param_title="Hundreds of Points"),
        CraftBeatPlan(beat_number=5, shape="FRACTAL_REVEAL",   param_title="Sierpinski Pattern"),
        CraftBeatPlan(beat_number=6, shape="NONE"),
    ]
    return CraftVideoPlan(beats=beats)

# ─────────────────────────────────────────────────────────────────────────────
# SCENE CODE — injected as the compiled craft scene
# ─────────────────────────────────────────────────────────────────────────────

def custom_compile_craft_scene(scene_name, orientation, plan, project_root):
    code = f"""import sys
sys.path.insert(0, r'{project_root}')
from manim import *
import random, math
import numpy as np

# ── Palette ──────────────────────────────────────────────────────────────────
BG_COLOR       = "#0D0D1A"
TEAL_COLOR     = "#00D4D4"
ORANGE_COLOR   = "#FF9F45"
PURPLE_COLOR   = "#C084FC"
CREAM_COLOR    = "#F5F0E8"
GOLD_COLOR     = "#FFD700"
RED_COLOR      = "#FF4D6D"
GREEN_COLOR    = "#4ADE80"
DIM_WHITE      = "#CCCCCC"
DOT_COLOR      = "#00D4D4"

class {scene_name}(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR

        # ── Triangle vertex coordinates (lower 55% workspace) ─────────────────
        # Centroid at DOWN * 1.8, side_length = 4.6
        S   = 4.6
        H   = S * math.sqrt(3) / 2          # ~3.98
        ctr = np.array([0, -1.8, 0])         # centroid anchor

        v_A = ctr + np.array([0,  2 * H / 3, 0])              # apex
        v_B = ctr + np.array([-S / 2, -H / 3, 0])             # bottom-left
        v_C = ctr + np.array([ S / 2, -H / 3, 0])             # bottom-right
        VERTS = [v_A, v_B, v_C]
        VERT_NAMES  = ["A", "B", "C"]
        VERT_COLORS = [ORANGE_COLOR, TEAL_COLOR, PURPLE_COLOR]

        # ── Safe-zone Y anchors (upper 45%) ───────────────────────────────────
        TITLE_Y   = UP * 3.5
        RULES_Y   = UP * 2.55
        COUNTER_Y = UP * 1.65

        # ─────────────────────────────────────────────────────────────────────
        # Beat 1: Title + Rules (0 - 6 s)
        # ─────────────────────────────────────────────────────────────────────
        title = Text("The Chaos Game", font_size=38, color=GOLD_COLOR,
                     weight=BOLD).move_to(TITLE_Y)

        rule_lines = VGroup(
            Text("Rule:", font_size=22, color=ORANGE_COLOR, weight=BOLD),
            Text("Pick a random vertex, move halfway,", font_size=19, color=CREAM_COLOR),
            Text("mark the midpoint. Repeat.", font_size=19, color=CREAM_COLOR),
        ).arrange(DOWN, buff=0.18).move_to(RULES_Y)

        step_label   = Text("Step:", font_size=20, color=DIM_WHITE)
        step_number  = Text("0", font_size=26, color=TEAL_COLOR, weight=BOLD)
        step_counter = VGroup(step_label, step_number).arrange(RIGHT, buff=0.2).move_to(COUNTER_Y)

        self.play(FadeIn(title, shift=DOWN * 0.3), run_time=1.2)
        self.play(FadeIn(rule_lines, shift=UP * 0.2), run_time=1.2)
        self.play(FadeIn(step_counter), run_time=0.8)
        self.wait(2.8)

        # ─────────────────────────────────────────────────────────────────────
        # Beat 2: Triangle + Vertex Labels (6 - 14 s)
        # ─────────────────────────────────────────────────────────────────────
        triangle = Polygon(v_A, v_B, v_C,
                           color=DIM_WHITE, stroke_width=2.5,
                           fill_color=BG_COLOR, fill_opacity=1.0)
        self.play(Create(triangle), run_time=1.8)

        label_offsets = [
            np.array([0,  0.38, 0]),
            np.array([-0.28, -0.38, 0]),
            np.array([ 0.28, -0.38, 0]),
        ]
        vert_label_objs = []
        for vpos, vname, vcol, loff in zip(VERTS, VERT_NAMES, VERT_COLORS, label_offsets):
            lbl = Text(vname, font_size=28, color=vcol, weight=BOLD).move_to(vpos + loff)
            vert_label_objs.append(lbl)

        self.play(*[FadeIn(l, scale=1.3) for l in vert_label_objs], run_time=1.0)

        # Random starting point (fixed seed)
        random.seed(42)
        np.random.seed(42)
        r1, r2 = sorted([random.random(), random.random()])
        start_pt = r1 * v_A + (r2 - r1) * v_B + (1 - r2) * v_C

        current_dot = Dot(start_pt, radius=0.1, color=RED_COLOR)
        self.play(FadeIn(current_dot, scale=2.0), run_time=0.8)
        self.wait(1.5)

        # ─────────────────────────────────────────────────────────────────────
        # Beat 3: 5 explicit midpoint steps (14 - 26 s)
        # ─────────────────────────────────────────────────────────────────────
        current_pos = np.array(start_pt)
        step_num    = 0

        for _ in range(5):
            chosen_idx  = random.randint(0, 2)
            chosen_pos  = np.array(VERTS[chosen_idx])
            chosen_col  = VERT_COLORS[chosen_idx]
            chosen_name = VERT_NAMES[chosen_idx]
            mid_pos     = (current_pos + chosen_pos) / 2.0

            # Highlight chosen vertex
            highlight  = Circle(radius=0.25, color=chosen_col,
                                stroke_width=3).move_to(chosen_pos)
            chosen_tag = Text(f"vertex {{chosen_name}}", font_size=18,
                              color=chosen_col).next_to(highlight, RIGHT, buff=0.15)
            self.play(Create(highlight), FadeIn(chosen_tag), run_time=0.4)

            # Dotted guide line
            guide = DashedLine(current_pos, chosen_pos,
                               dash_length=0.12, color=chosen_col,
                               stroke_width=1.5, stroke_opacity=0.55)
            self.play(Create(guide), run_time=0.45)

            # Midpoint dot
            new_dot = Dot(mid_pos, radius=0.09, color=DOT_COLOR)
            self.play(FadeIn(new_dot, scale=1.8), run_time=0.35)

            # Move current dot to midpoint; fade guide
            self.play(
                FadeOut(guide),
                FadeOut(highlight),
                FadeOut(chosen_tag),
                current_dot.animate.move_to(mid_pos),
                run_time=0.55,
            )

            step_num += 1
            new_counter = VGroup(
                Text("Step:", font_size=20, color=DIM_WHITE),
                Text(str(step_num), font_size=26, color=TEAL_COLOR, weight=BOLD),
            ).arrange(RIGHT, buff=0.2).move_to(COUNTER_Y)
            self.play(Transform(step_counter, new_counter), run_time=0.25)

            current_pos = mid_pos
            self.wait(0.3)

        # ─────────────────────────────────────────────────────────────────────
        # Beat 4: Rapid generation (26 - 38 s)
        # ─────────────────────────────────────────────────────────────────────
        accel_label = VGroup(
            Text("Accelerating...", font_size=22, color=ORANGE_COLOR, weight=BOLD),
            Text("Same rule, hundreds of points.", font_size=19, color=CREAM_COLOR),
        ).arrange(DOWN, buff=0.22).move_to(RULES_Y)
        self.play(Transform(rule_lines, accel_label), run_time=0.8)

        # Pre-compute 600 chaos-game points
        all_pts = []
        p = current_pos.copy()
        for _ in range(600):
            idx = random.randint(0, 2)
            p   = (p + np.array(VERTS[idx])) / 2.0
            all_pts.append(p.copy())

        # Render in batches with decreasing pause
        batch_specs = [
            (0,   100, 0.06,  0.07),
            (100, 300, 0.025, 0.065),
            (300, 600, 0.01,  0.055),
        ]
        for (si, ei, pause, drad) in batch_specs:
            for idx_p in range(si, ei):
                pt  = all_pts[idx_p]
                dot = Dot(pt, radius=drad, color=DOT_COLOR, fill_opacity=0.85)
                self.add(dot)
                step_num += 1
                if step_num % 25 == 0:
                    new_c = VGroup(
                        Text("Step:", font_size=20, color=DIM_WHITE),
                        Text(str(step_num), font_size=26, color=TEAL_COLOR, weight=BOLD),
                    ).arrange(RIGHT, buff=0.2).move_to(COUNTER_Y)
                    self.remove(step_counter)
                    step_counter.become(new_c)
                    self.add(step_counter)
                self.wait(pause)

        self.wait(0.8)

        # ─────────────────────────────────────────────────────────────────────
        # Beat 5: Full fractal reveal + formula (38 - 50 s)
        # ─────────────────────────────────────────────────────────────────────
        fractal_title = Text("Sierpinski Triangle", font_size=30,
                             color=GOLD_COLOR, weight=BOLD)
        fractal_sub   = Text("Born from randomness + one rule", font_size=19,
                             color=DIM_WHITE)
        formula_label = Text("Probability any region is reached:", font_size=18,
                             color=ORANGE_COLOR)
        formula_tex   = MathTex(
            r"P = \\left(\\frac{{1}}{{2}}\\right)^n",
            color=TEAL_COLOR
        ).scale(1.05)
        top_block = VGroup(
            VGroup(fractal_title, fractal_sub).arrange(DOWN, buff=0.22),
            VGroup(formula_label, formula_tex).arrange(DOWN, buff=0.18),
        ).arrange(DOWN, buff=0.38).move_to((np.array(RULES_Y) + np.array(COUNTER_Y)) / 2)

        self.play(
            FadeOut(rule_lines),
            FadeOut(step_counter),
            FadeIn(top_block, shift=UP * 0.2),
            run_time=1.2,
        )
        self.wait(10.0)

        # ─────────────────────────────────────────────────────────────────────
        # Beat 6: Active Recall Checkpoint (50 - 60 s)
        # All text in upper zone via a single anchored VGroup — zero static overlap
        # ─────────────────────────────────────────────────────────────────────
        mid_AB = (v_A + v_B) / 2.0
        mid_BC = (v_B + v_C) / 2.0
        mid_AC = (v_A + v_C) / 2.0
        inner_tri = Polygon(mid_AB, mid_BC, mid_AC,
                            color=RED_COLOR, stroke_width=2.5,
                            fill_color=RED_COLOR, fill_opacity=0.18)

        # Entire recall block built as one VGroup — no two items share a static Y
        recall_q    = Text("Pause and Think:", font_size=26,
                           color=ORANGE_COLOR, weight=BOLD)
        recall_body = Text("Which region is always empty?", font_size=20,
                           color=CREAM_COLOR)
        recall_hint = Text("Hint: look at the highlighted triangle.",
                           font_size=18, color=DIM_WHITE)
        recall_grp  = VGroup(recall_q, recall_body, recall_hint).arrange(
            DOWN, buff=0.28
        ).move_to(UP * 2.7)

        self.play(
            FadeOut(top_block),
            FadeIn(inner_tri),
            FadeIn(recall_grp, shift=UP * 0.2),
            run_time=1.2,
        )

        # Pulse the empty triangle gently
        for _ in range(2):
            self.play(inner_tri.animate.set_fill(opacity=0.40), run_time=0.7)
            self.play(inner_tri.animate.set_fill(opacity=0.18), run_time=0.7)

        # Reveal answer — Transform replaces entire VGroup atomically
        ans_hdr  = Text("Answer:", font_size=24, color=GREEN_COLOR, weight=BOLD)
        ans_body = Text("No point ever lands in the central", font_size=18,
                        color=CREAM_COLOR)
        ans_body2 = Text("triangle. It is the Sierpinski void.", font_size=18,
                         color=CREAM_COLOR)
        ans_grp  = VGroup(ans_hdr, ans_body, ans_body2).arrange(
            DOWN, buff=0.25
        ).move_to(UP * 2.7)

        self.wait(2.0)
        self.play(Transform(recall_grp, ans_grp), run_time=1.0)
        self.wait(4.5)
"""
    return code

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app.pipeline.generate_storyboard_draft  = custom_generate_storyboard_draft
    app.craft_pipeline.generate_craft_plan  = custom_generate_craft_plan
    app.craft_pipeline.compile_craft_scene  = custom_compile_craft_scene

    job_id = str(uuid.uuid4())
    topic  = (
        "Visually explain the rules of the Chaos Game to generate a Sierpinski Triangle. "
        "Lock a large equilateral triangle with vertices A, B, C in the lower 55% workspace. "
        "Show 5 explicit steps: random vertex selection, dotted line, midpoint plot. "
        "Transition into rapid generation of hundreds of points forming the fractal pattern."
    )

    payload = {
        "topic":             topic,
        "duration_seconds":  60,
        "audience":          "JEE aspirants",
        "scene_name":        "ChaosGameSierpinskiAnimation",
        "orientation":       "portrait",
        "pipeline_profile":  "craft",
    }

    with SessionLocal() as db:
        job = Job(
            id               = job_id,
            status           = JobStatus.queued,
            job_kind         = "topic",
            pipeline_profile = "craft",
            request_payload  = payload,
            scene_name       = "ChaosGameSierpinskiAnimation",
            orientation      = "portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created Chaos Game job {job_id}")

    print("Running Chaos Game topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id           = job_id,
            topic            = topic,
            duration_seconds = 60,
            audience         = "JEE aspirants",
            scene_name       = "ChaosGameSierpinskiAnimation",
            orientation      = "portrait",
            pipeline_profile = "craft",
        )
        print(f"Job {job_id} run completed successfully.")

        # Copy the final video to outputs/4.mp4
        job_runs_dir = Path("C:/PROJECTS/vivacity_job_runs") / job_id
        outputs_dir  = Path("C:/PROJECTS/newmanim/outputs")
        outputs_dir.mkdir(parents=True, exist_ok=True)
        dest = outputs_dir / "4.mp4"

        # Walk: prefer production/ over draft/
        found = None
        for priority_kw in ("production", "draft"):
            for root, _dirs, files in os.walk(job_runs_dir):
                if priority_kw not in root:
                    continue
                for fname in files:
                    if fname.endswith(".mp4") and "partial" not in root:
                        found = Path(root) / fname
                        break
                if found:
                    break
            if found:
                break

        if found:
            shutil.copy2(found, dest)
            print(f"Saved -> {dest}  ({dest.stat().st_size:,} bytes)")
        else:
            print("Warning: Could not find rendered video in job runs folder.")

    except Exception as e:
        print(f"Error running job {job_id}: {e!r}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
