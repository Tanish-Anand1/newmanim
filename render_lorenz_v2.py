"""
render_lorenz_v2.py
────────────────────────────
Writes the Lorenz Attractor scene to a local file and renders it directly via manim CLI.
Output: C:/PROJECTS/newmanim/outputs/lorenz_v2.mp4
"""
import os, sys, subprocess, shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DEST  = os.path.join(PROJECT_ROOT, "outputs", "lorenz_v2.mp4")
SCENE_NAME   = "LorenzScene"

SCENE_CODE = r"""
import sys
sys.path.insert(0, r'""" + PROJECT_ROOT.replace("\\", "/") + r"""')
from manim import *
import numpy as np

BG_COLOR      = "#0D0D1A"
TEAL_COLOR    = "#00D4D4"
ORANGE_COLOR  = "#FF9F45"
CREAM_COLOR   = "#F5F0E8"
GOLD_COLOR    = "#FFD700"
DIM_WHITE     = "#CCCCCC"

class LorenzScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        
        # Upper 45% Math Zone
        title = Text("The Lorenz Attractor", font_size=36, color=GOLD_COLOR, weight=BOLD)
        
        eq_group = VGroup(
            Text("dx/dt = σ(y - x)", font_size=24, color=DIM_WHITE),
            Text("dy/dt = x(ρ - z) - y", font_size=24, color=DIM_WHITE),
            Text("dz/dt = xy - βz", font_size=24, color=DIM_WHITE)
        ).arrange(DOWN, buff=0.15)
        
        state_text = Text("State: Single Path", font_size=22, color=TEAL_COLOR, weight=BOLD)
        
        top_group = VGroup(title, eq_group, state_text).arrange(DOWN, buff=0.35)
        top_group.move_to(UP * (config.frame_height * 0.275))
        
        self.add_fixed_in_frame_mobjects(top_group)
        self.play(FadeIn(top_group))
        
        # Lower 55% Workspace
        axes = ThreeDAxes(
            x_range=[-30, 30, 10],
            y_range=[-30, 30, 10],
            z_range=[0, 50, 10],
            x_length=5,
            y_length=5,
            z_length=4
        ).shift(DOWN * 2.0)
        
        self.set_camera_orientation(phi=65 * DEGREES, theta=30 * DEGREES)
        self.play(Create(axes), run_time=1.5)
        self.begin_ambient_camera_rotation(rate=0.15)

        sigma, rho, beta = 10.0, 28.0, 8.0/3.0
        dt = 0.01
        steps = 2000
        
        def lorenz(p):
            x, y, z = p
            return np.array([sigma * (y - x), x * (rho - z) - y, x * y - beta * z])
            
        def get_trajectory(start_pos):
            pts = [start_pos]
            curr = start_pos
            for _ in range(steps):
                curr = curr + lorenz(curr) * dt
                pts.append(curr)
            return pts

        start_1 = np.array([0.1, 0.0, 0.0])
        pts_1 = get_trajectory(start_1)
        curve_1 = VMobject(color=TEAL_COLOR, stroke_width=2)
        curve_1.set_points_as_corners([axes.c2p(*p) for p in pts_1])
        
        self.play(Create(curve_1), run_time=4.0, rate_func=linear)
        self.wait(1)
        
        # Reset and Diverge
        new_state_text = Text("State: Diverging Trajectories", font_size=22, color=ORANGE_COLOR, weight=BOLD)
        new_state_text.move_to(state_text.get_center())
        self.add_fixed_in_frame_mobjects(new_state_text)
        
        self.play(
            FadeOut(curve_1),
            FadeOut(state_text),
            FadeIn(new_state_text)
        )
        
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
"""

def main():
    render_dir = os.path.join(PROJECT_ROOT, "_lorenz_v2_render")
    os.makedirs(render_dir, exist_ok=True)
    scene_py = os.path.join(render_dir, "scene.py")
    with open(scene_py, "w", encoding="utf-8") as f:
        f.write(SCENE_CODE)

    cmd = [os.path.join(PROJECT_ROOT, "manim-env", "Scripts", "manim.exe"), scene_py, SCENE_NAME, "--fps", "60", "--resolution", "1080,1920", "-q", "h", "--media_dir", os.path.join(render_dir, "media")]
    subprocess.run(cmd, cwd=render_dir, capture_output=False, check=True)

    for root, _, files in os.walk(os.path.join(render_dir, "media")):
        for fname in files:
            if fname.endswith(".mp4") and "partial" not in root:
                shutil.copy2(os.path.join(root, fname), OUTPUT_DEST)
                return

if __name__ == "__main__":
    main()
