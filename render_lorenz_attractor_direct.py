"""
render_lorenz_attractor_direct.py
────────────────────────────
Writes the Lorenz Attractor scene to a local file and renders it directly via
the manim CLI. Strict 2D layout anchoring on top + 3D rendering on bottom.
Output: C:/PROJECTS/newmanim/outputs/5.mp4
"""
import os, sys, subprocess, shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DEST  = os.path.join(PROJECT_ROOT, "outputs", "5.mp4")
SCENE_NAME   = "LorenzAttractorAnimation"

SCENE_CODE = r"""
import sys
sys.path.insert(0, r'""" + PROJECT_ROOT.replace("\\", "/") + r"""')
from manim import *
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

class LorenzAttractorAnimation(ThreeDScene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        
        # ── 1. Upper Math Zone (Fixed in frame) ─────────────────
        # All text gets packed into ONE master VGroup and positioned once to guarantee ZERO overlapping.
        title = Text("The Lorenz Attractor", font_size=36, color=GOLD_COLOR, weight=BOLD)
        subtitle = Text("Sensitivity to Initial Conditions", font_size=20, color=CREAM_COLOR)
        
        eq1 = Text("dx/dt = σ(y - x)", font_size=24, color=DIM_WHITE)
        eq2 = Text("dy/dt = x(ρ - z) - y", font_size=24, color=DIM_WHITE)
        eq3 = Text("dz/dt = xy - βz", font_size=24, color=DIM_WHITE)
        eq_group = VGroup(eq1, eq2, eq3).arrange(DOWN, buff=0.15)
        
        state_text_1 = Text("State: Single Path", font_size=22, color=TEAL_COLOR, weight=BOLD)
        
        # Pack into a unified layout structure
        top_group = VGroup(
            title, 
            subtitle, 
            eq_group, 
            state_text_1
        ).arrange(DOWN, buff=0.3).to_edge(UP, buff=0.5)
        
        # Add text as flat 2D objects over the 3D scene
        self.add_fixed_in_frame_mobjects(top_group)
        self.play(FadeIn(top_group))
        
        # ── 2. Lower Geometric Workspace (3D) ─────────────────
        axes = ThreeDAxes(
            x_range=[-30, 30, 10],
            y_range=[-30, 30, 10],
            z_range=[0, 50, 10],
            x_length=6,
            y_length=6,
            z_length=4.5
        )
        # Shift the 3D grid down physically in the 3D world space
        axes.shift(DOWN * 1.5)
        
        # Set dynamic 3D camera angle
        self.set_camera_orientation(phi=65 * DEGREES, theta=30 * DEGREES)
        self.play(Create(axes), run_time=1.5)
        
        # Slowly spin the camera while animating
        self.begin_ambient_camera_rotation(rate=0.15)

        # Mathematical parameters
        sigma, rho, beta = 10.0, 28.0, 8.0/3.0
        dt = 0.01
        steps = 2500  # Tracing steps
        
        def lorenz(p):
            x, y, z = p
            return np.array([
                sigma * (y - x),
                x * (rho - z) - y,
                x * y - beta * z
            ])
            
        def get_trajectory(start_pos):
            pts = [start_pos]
            curr = start_pos
            for _ in range(steps):
                curr = curr + lorenz(curr) * dt
                pts.append(curr)
            return pts

        start_1 = np.array([0.1, 0.0, 0.0])
        pts_1 = get_trajectory(start_1)
        
        # Efficient polyline curve rendering
        curve_1 = VMobject(color=TEAL_COLOR, stroke_width=2)
        curve_1.set_points_as_corners([axes.c2p(*p) for p in pts_1])
        
        # ── 3. Single Path Trace ─────────────────
        self.play(Create(curve_1), run_time=4.0, rate_func=linear)
        self.wait(1.5)
        
        # ── 4. Divergence Trace ─────────────────
        # Swapping text safely inside the static upper zone
        state_text_2 = Text("State: Diverging Trajectories", font_size=22, color=ORANGE_COLOR, weight=BOLD)
        state_text_2.move_to(state_text_1)
        self.add_fixed_in_frame_mobjects(state_text_2)
        
        self.play(
            FadeOut(curve_1),
            FadeOut(state_text_1),
            FadeIn(state_text_2)
        )
        
        # Trace both with 0.0001 offset
        start_2 = start_1 + np.array([0.0001, 0.0, 0.0])
        pts_2 = get_trajectory(start_2)
        
        curve_1_new = VMobject(color=TEAL_COLOR, stroke_width=2)
        curve_1_new.set_points_as_corners([axes.c2p(*p) for p in pts_1])
        
        curve_2_new = VMobject(color=ORANGE_COLOR, stroke_width=2)
        curve_2_new.set_points_as_corners([axes.c2p(*p) for p in pts_2])
        
        self.play(
            Create(curve_1_new),
            Create(curve_2_new),
            run_time=6.0,
            rate_func=linear
        )
        self.wait(2)
        self.stop_ambient_camera_rotation()
        
        # ── 5. Final Explanation ─────────────────
        final_text = Text("Tiny change in start → massive divergence", font_size=24, color=RED_COLOR, weight=BOLD)
        final_text.move_to(state_text_2)
        self.add_fixed_in_frame_mobjects(final_text)
        
        self.play(
            FadeOut(state_text_2),
            FadeIn(final_text)
        )
        self.wait(3)
"""

def main():
    render_dir = os.path.join(PROJECT_ROOT, "_lorenz_render")
    os.makedirs(render_dir, exist_ok=True)
    scene_py = os.path.join(render_dir, "lorenz_scene.py")
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
    result = subprocess.run(cmd, cwd=render_dir, capture_output=False)
    if result.returncode != 0:
        print(f"Manim exited with code {result.returncode}")
        sys.exit(result.returncode)

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
    print(f"\nSaved -> {OUTPUT_DEST}")

if __name__ == "__main__":
    main()
