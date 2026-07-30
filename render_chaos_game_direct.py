"""
render_chaos_game_direct.py
────────────────────────────
Writes the Chaos Game scene to a local file and renders it directly via
the manim CLI — zero pipeline dependency, zero LLM calls.
Output: C:/PROJECTS/newmanim/outputs/4.mp4
"""
import os, sys, subprocess, shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DEST  = os.path.join(PROJECT_ROOT, "outputs", "4.mp4")
SCENE_NAME   = "ChaosGameSierpinskiAnimation"

SCENE_CODE = r"""
import sys
sys.path.insert(0, r'""" + PROJECT_ROOT.replace("\\", "/") + r"""')
from manim import *
import random, math
import numpy as np

BG_COLOR      = "#0D0D1A"
TEAL_COLOR    = "#00D4D4"
ORANGE_COLOR  = "#FF9F45"
PURPLE_COLOR  = "#C084FC"
CREAM_COLOR   = "#F5F0E8"
GOLD_COLOR    = "#FFD700"
RED_COLOR     = "#FF4D6D"
GREEN_COLOR   = "#4ADE80"
DIM_WHITE     = "#CCCCCC"
DOT_COLOR     = "#00D4D4"

class ChaosGameSierpinskiAnimation(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR

        # ── Triangle vertex coordinates (lower 60% workspace) ─────────────────
        # Scale down and shift lower to guarantee no element crosses Y = -0.5
        S   = 3.6
        H   = S * math.sqrt(3) / 2
        ctr = np.array([0.0, -3.0, 0.0])

        v_A = ctr + np.array([0.0,  2 * H / 3, 0.0])
        v_B = ctr + np.array([-S / 2, -H / 3, 0.0])
        v_C = ctr + np.array([ S / 2, -H / 3, 0.0])
        VERTS       = [v_A, v_B, v_C]
        VERT_NAMES  = ["A", "B", "C"]
        VERT_COLORS = [ORANGE_COLOR, TEAL_COLOR, PURPLE_COLOR]

        # ── Text Layout Group (Upper 40% Safe Zone) ─────────────────────────
        text_layout_group = VGroup().set_z_index(10)

        # ── Beat 1: Title + Rules (0–6 s) ────────────────────────────────────
        title = Text("The Chaos Game", font_size=38, color=GOLD_COLOR, weight=BOLD)
        rule_lines = VGroup(
            Text("Rule:", font_size=22, color=ORANGE_COLOR, weight=BOLD),
            Text("Pick a random vertex, move halfway,", font_size=19, color=CREAM_COLOR),
            Text("mark the midpoint. Repeat.", font_size=19, color=CREAM_COLOR),
        ).arrange(DOWN, buff=0.18)
        step_counter = VGroup(
            Text("Step:", font_size=20, color=DIM_WHITE),
            Text("0", font_size=26, color=TEAL_COLOR, weight=BOLD),
        ).arrange(RIGHT, buff=0.2)

        text_layout_group = VGroup(title, rule_lines, step_counter)
        text_layout_group.arrange(DOWN, buff=0.3).to_edge(UP, buff=0.4).set_z_index(10)
        
        if text_layout_group.width > config.frame_width - 1.5:
            text_layout_group.scale_to_fit_width(config.frame_width - 1.5)

        self.play(FadeIn(title, shift=DOWN * 0.3), run_time=1.2)
        self.play(FadeIn(rule_lines, shift=UP * 0.2), run_time=1.2)
        self.play(FadeIn(step_counter), run_time=0.8)
        self.wait(2.8)

        # ── Beat 2: Triangle + Vertex Labels (6–14 s) ────────────────────────
        # All geometric objects are placed on z_index 1
        triangle = Polygon(v_A, v_B, v_C,
                           color=DIM_WHITE, stroke_width=2.5,
                           fill_color=BG_COLOR, fill_opacity=1.0).set_z_index(1)
        self.play(Create(triangle), run_time=1.8)

        label_offsets = [
            np.array([0.0,  0.38, 0.0]),
            np.array([-0.28, -0.38, 0.0]),
            np.array([ 0.28, -0.38, 0.0]),
        ]
        vert_label_objs = []
        for vpos, vname, vcol, loff in zip(VERTS, VERT_NAMES, VERT_COLORS, label_offsets):
            lbl = Text(vname, font_size=28, color=vcol, weight=BOLD).move_to(vpos + loff).set_z_index(1)
            vert_label_objs.append(lbl)
        self.play(*[FadeIn(l, scale=1.3) for l in vert_label_objs], run_time=1.0)

        # Random starting point (fixed seed for reproducibility)
        random.seed(42)
        np.random.seed(42)
        r1, r2 = sorted([random.random(), random.random()])
        start_pt = r1 * v_A + (r2 - r1) * v_B + (1 - r2) * v_C

        current_dot = Dot(start_pt, radius=0.1, color=RED_COLOR).set_z_index(1)
        self.play(FadeIn(current_dot, scale=2.0), run_time=0.8)
        self.wait(1.5)

        # ── Beat 3: 5 explicit midpoint steps (14–26 s) ──────────────────────
        current_pos = np.array(start_pt, dtype=float)
        step_num    = 0

        for _ in range(5):
            chosen_idx  = random.randint(0, 2)
            chosen_pos  = np.array(VERTS[chosen_idx], dtype=float)
            chosen_col  = VERT_COLORS[chosen_idx]
            chosen_name = VERT_NAMES[chosen_idx]
            mid_pos     = (current_pos + chosen_pos) / 2.0

            highlight  = Circle(radius=0.25, color=chosen_col,
                                stroke_width=3).move_to(chosen_pos).set_z_index(1)
            chosen_tag = Text(f"vertex {chosen_name}", font_size=18,
                              color=chosen_col).next_to(highlight, RIGHT, buff=0.15).set_z_index(1)
            self.play(Create(highlight), FadeIn(chosen_tag), run_time=0.4)

            guide = DashedLine(current_pos, chosen_pos,
                               dash_length=0.12, color=chosen_col,
                               stroke_width=1.5, stroke_opacity=0.55).set_z_index(1)
            self.play(Create(guide), run_time=0.45)

            new_dot = Dot(mid_pos, radius=0.09, color=DOT_COLOR).set_z_index(1)
            self.play(FadeIn(new_dot, scale=1.8), run_time=0.35)

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
            ).arrange(RIGHT, buff=0.2).move_to(step_counter.get_center()).set_z_index(10)
            self.play(Transform(step_counter, new_counter), run_time=0.25)
            step_counter = new_counter

            current_pos = mid_pos
            self.wait(0.3)

        # ── Beat 4: Rapid generation (26–38 s) ───────────────────────────────
        accel_label = VGroup(
            Text("Accelerating...", font_size=22, color=ORANGE_COLOR, weight=BOLD),
            Text("Same rule, hundreds of points.", font_size=19, color=CREAM_COLOR),
        ).arrange(DOWN, buff=0.22)
        
        # Explicit recalculation of the parent text layout
        text_layout_group = VGroup(title, accel_label, step_counter)
        text_layout_group.arrange(DOWN, buff=0.25).to_edge(UP, buff=0.4).set_z_index(10)
        if text_layout_group.width > config.frame_width - 1.5:
            text_layout_group.scale_to_fit_width(config.frame_width - 1.5)

        self.play(
            title.animate.move_to(text_layout_group[0]),
            Transform(rule_lines, text_layout_group[1]),
            step_counter.animate.move_to(text_layout_group[2]),
            run_time=0.8
        )
        rule_lines = text_layout_group[1]

        all_pts = []
        p = current_pos.copy()
        for _ in range(600):
            idx = random.randint(0, 2)
            p   = (p + np.array(VERTS[idx], dtype=float)) / 2.0
            all_pts.append(p.copy())

        batch_specs = [
            (0,   100, 0.06,  0.07),
            (100, 300, 0.025, 0.065),
            (300, 600, 0.01,  0.055),
        ]
        for (si, ei, pause, drad) in batch_specs:
            for idx_p in range(si, ei):
                dot = Dot(all_pts[idx_p], radius=drad, color=DOT_COLOR, fill_opacity=0.85).set_z_index(1)
                self.add(dot)
                step_num += 1
                if step_num % 25 == 0:
                    new_c = VGroup(
                        Text("Step:", font_size=20, color=DIM_WHITE),
                        Text(str(step_num), font_size=26, color=TEAL_COLOR, weight=BOLD),
                    ).arrange(RIGHT, buff=0.2).move_to(step_counter.get_center()).set_z_index(10)
                    self.remove(step_counter)
                    step_counter = new_c
                    self.add(step_counter)
                self.wait(pause)

        self.wait(0.8)

        # ── Beat 5: Full fractal reveal + formula (38–50 s) ──────────────────
        fractal_title = Text("Sierpinski Triangle", font_size=30,
                             color=GOLD_COLOR, weight=BOLD)
        fractal_sub   = Text("Born from randomness + one rule", font_size=19,
                             color=DIM_WHITE)
        formula_label = Text("Probability any region is reached:", font_size=18,
                             color=ORANGE_COLOR)
        formula_tex   = Text("P = (1/2)^n", font_size=24,
                             color=TEAL_COLOR)
        top_block = VGroup(
            VGroup(fractal_title, fractal_sub).arrange(DOWN, buff=0.22),
            VGroup(formula_label, formula_tex).arrange(DOWN, buff=0.18),
        )

        text_layout_group = VGroup(top_block)
        text_layout_group.arrange(DOWN, buff=0.38).to_edge(UP, buff=0.4).set_z_index(10)
        
        if text_layout_group.width > config.frame_width - 1.5:
            text_layout_group.scale_to_fit_width(config.frame_width - 1.5)

        self.play(
            FadeOut(title),
            FadeOut(rule_lines),
            FadeOut(step_counter),
            FadeIn(text_layout_group, shift=UP * 0.2),
            run_time=1.2,
        )
        self.wait(10.0)

        # ── Beat 6: Active Recall Checkpoint (50–60 s) ───────────────────────
        mid_AB = (v_A + v_B) / 2.0
        mid_BC = (v_B + v_C) / 2.0
        mid_AC = (v_A + v_C) / 2.0
        inner_tri = Polygon(mid_AB, mid_BC, mid_AC,
                            color=RED_COLOR, stroke_width=2.5,
                            fill_color=RED_COLOR, fill_opacity=0.18).set_z_index(1)

        # ── Entire recall block as one VGroup — zero static Y overlap ─────────
        recall_q    = Text("Pause and Think:", font_size=26,
                           color=ORANGE_COLOR, weight=BOLD)
        recall_body = Text("Which region is always empty?", font_size=20,
                           color=CREAM_COLOR)
        recall_hint = Text("Hint: look at the highlighted triangle.",
                           font_size=18, color=DIM_WHITE)
        recall_grp  = VGroup(recall_q, recall_body, recall_hint)
        
        text_layout_group_new = VGroup(recall_grp)
        text_layout_group_new.arrange(DOWN, buff=0.28).to_edge(UP, buff=0.4).set_z_index(10)

        if text_layout_group_new.width > config.frame_width - 1.5:
            text_layout_group_new.scale_to_fit_width(config.frame_width - 1.5)

        self.play(
            FadeOut(text_layout_group),
            FadeIn(inner_tri),
            FadeIn(text_layout_group_new, shift=UP * 0.2),
            run_time=1.2,
        )
        text_layout_group = text_layout_group_new

        for _ in range(2):
            self.play(inner_tri.animate.set_fill(opacity=0.40), run_time=0.7)
            self.play(inner_tri.animate.set_fill(opacity=0.18), run_time=0.7)

        ans_hdr  = Text("Answer:", font_size=24, color=GREEN_COLOR, weight=BOLD)
        ans_body = Text("No point ever lands in the central", font_size=18,
                        color=CREAM_COLOR)
        ans_body2 = Text("triangle — it is the Sierpinski void.", font_size=18,
                         color=CREAM_COLOR)
        ans_grp  = VGroup(ans_hdr, ans_body, ans_body2)
        
        text_layout_group_ans = VGroup(ans_grp)
        text_layout_group_ans.arrange(DOWN, buff=0.25).to_edge(UP, buff=0.4).set_z_index(10)
        
        if text_layout_group_ans.width > config.frame_width - 1.5:
            text_layout_group_ans.scale_to_fit_width(config.frame_width - 1.5)

        self.wait(2.0)
        self.play(Transform(text_layout_group, text_layout_group_ans), run_time=1.0)
        self.wait(4.5)
"""


def main():
    # Use a local render folder — avoids 8.3 short-path issues that break LaTeX
    render_dir = os.path.join(PROJECT_ROOT, "_chaos_render")
    os.makedirs(render_dir, exist_ok=True)
    scene_py = os.path.join(render_dir, "chaos_scene.py")
    with open(scene_py, "w", encoding="utf-8") as f:
        f.write(SCENE_CODE)

    media_dir = os.path.join(render_dir, "media")
    manim_exe = os.path.join(PROJECT_ROOT, "manim-env", "Scripts", "manim.exe")

    cmd = [
        manim_exe,
        scene_py,
        SCENE_NAME,
        "--fps", "60",
        "--resolution", "1080,1920",
        "-q", "h",
        "--media_dir", media_dir,
    ]

    print(f"Rendering {SCENE_NAME} ...")
    print("Command:", " ".join(cmd))

    result = subprocess.run(cmd, cwd=render_dir, capture_output=False)
    if result.returncode != 0:
        print(f"Manim exited with code {result.returncode}")
        sys.exit(result.returncode)

    # Find the output mp4
    found = None
    for root, _dirs, files in os.walk(media_dir):
        for fname in files:
            if fname.endswith(".mp4") and "partial" not in root:
                found = os.path.join(root, fname)
                break
        if found:
            break

    if not found:
        print("ERROR: Manim did not produce an mp4.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_DEST), exist_ok=True)
    shutil.copy2(found, OUTPUT_DEST)
    print(f"\nSaved -> {OUTPUT_DEST}  ({os.path.getsize(OUTPUT_DEST):,} bytes)")


if __name__ == "__main__":
    main()
