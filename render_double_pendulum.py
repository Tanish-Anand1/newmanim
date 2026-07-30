"""
render_double_pendulum.py
────────────────────────────
Writes the Double Pendulum scene to a local file and renders it directly via manim CLI.
Output: C:/PROJECTS/newmanim/outputs/double_pendulum.mp4
"""
import os, sys, subprocess, shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DEST  = os.path.join(PROJECT_ROOT, "outputs", "double_pendulum.mp4")
SCENE_NAME   = "DoublePendulumScene"

SCENE_CODE = r"""
import sys
sys.path.insert(0, r'""" + PROJECT_ROOT.replace("\\", "/") + r"""')
from manim import *
import numpy as np

BG_COLOR      = "#0D0D1A"
CYAN_COLOR    = "#00D4D4"
MAGENTA_COLOR = "#FF00FF"
CREAM_COLOR   = "#F5F0E8"
GOLD_COLOR    = "#FFD700"
DIM_WHITE     = "#CCCCCC"

class DoublePendulumScene(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        
        # 1. Text Safe-Zone (Upper 45%)
        title = Text("Double Pendulum Chaos", font_size=36, color=GOLD_COLOR, weight=BOLD)
        desc = Text("Phase Space: Angular Velocity vs Angle", font_size=24, color=DIM_WHITE)
        
        text_group = VGroup(title, desc).arrange(DOWN, buff=0.35)
        text_group.move_to(UP * (config.frame_height * 0.275))
        self.add(text_group)
        
        # 2. Left Workspace (Pendulum) & Right Workspace (Phase Space)
        # Shift the pivot anchors down by exactly 2.0 units to keep in lower 55%
        left_center = LEFT * 2.5 + DOWN * 2.0
        right_center = RIGHT * 2.5 + DOWN * 2.0
        
        # Pivot point
        pivot = Dot(left_center, color=WHITE, radius=0.08)
        self.add(pivot)
        
        # Phase space axes
        ps_axes = Axes(
            x_range=[-np.pi, np.pi, np.pi/2],
            y_range=[-8, 8, 2],
            x_length=4.5,
            y_length=4.5,
            axis_config={"color": DIM_WHITE}
        ).move_to(right_center)
        self.add(ps_axes)
        
        # 3. Physics Simulation Setup
        # Mathematically restrict the lengths
        L1, L2 = 1.0, 1.0
        m1, m2 = 1.0, 1.0
        g = 9.81
        dt = 0.015
        
        # State: [theta1, theta2, omega1, omega2]
        def derivatives(state):
            t1, t2, w1, w2 = state
            delta = t2 - t1
            
            den1 = (m1 + m2) * L1 - m2 * L1 * np.cos(delta)**2
            den2 = (L2 / L1) * den1
            
            dw1 = (m2 * L1 * w1**2 * np.sin(delta) * np.cos(delta) +
                   m2 * g * np.sin(t2) * np.cos(delta) +
                   m2 * L2 * w2**2 * np.sin(delta) -
                   (m1 + m2) * g * np.sin(t1)) / den1
                   
            dw2 = (-m2 * L2 * w2**2 * np.sin(delta) * np.cos(delta) +
                   (m1 + m2) * g * np.sin(t1) * np.cos(delta) -
                   (m1 + m2) * L1 * w1**2 * np.sin(delta) -
                   (m1 + m2) * g * np.sin(t2)) / den2
                   
            return np.array([w1, w2, dw1, dw2])
            
        def rk4_step(state, dt):
            k1 = derivatives(state)
            k2 = derivatives(state + 0.5 * dt * k1)
            k3 = derivatives(state + 0.5 * dt * k2)
            k4 = derivatives(state + dt * k3)
            return state + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)

        # Initial conditions: angle difference of 0.001
        state_cyan = np.array([np.pi/2, np.pi/2, 0.0, 0.0])
        state_magenta = np.array([np.pi/2 + 0.001, np.pi/2, 0.0, 0.0])
        
        # Trajectory trackers
        trace_cyan = TracedPath(lambda: ps_axes.c2p(state_cyan[1], state_cyan[3]), stroke_color=CYAN_COLOR, stroke_width=2)
        trace_magenta = TracedPath(lambda: ps_axes.c2p(state_magenta[1], state_magenta[3]), stroke_color=MAGENTA_COLOR, stroke_width=2)
        self.add(trace_cyan, trace_magenta)
        
        line1_c = Line(pivot.get_center(), pivot.get_center(), color=CYAN_COLOR)
        line2_c = Line(pivot.get_center(), pivot.get_center(), color=CYAN_COLOR)
        dot1_c = Dot(color=CYAN_COLOR)
        dot2_c = Dot(color=CYAN_COLOR)
        
        line1_m = Line(pivot.get_center(), pivot.get_center(), color=MAGENTA_COLOR)
        line2_m = Line(pivot.get_center(), pivot.get_center(), color=MAGENTA_COLOR)
        dot1_m = Dot(color=MAGENTA_COLOR)
        dot2_m = Dot(color=MAGENTA_COLOR)
        
        self.add(line1_c, line2_c, dot1_c, dot2_c)
        self.add(line1_m, line2_m, dot1_m, dot2_m)
        
        def update_pendulum(l1, l2, d1, d2, state, color):
            t1, t2 = state[0], state[1]
            x1 = L1 * np.sin(t1)
            y1 = -L1 * np.cos(t1)
            x2 = x1 + L2 * np.sin(t2)
            y2 = y1 - L2 * np.cos(t2)
            
            # Scale coordinates up for visibility (restricted scale to fit bottom 55%)
            scale = 1.5
            p1 = left_center + np.array([x1*scale, y1*scale, 0])
            p2 = left_center + np.array([x2*scale, y2*scale, 0])
            
            l1.put_start_and_end_on(pivot.get_center(), p1)
            l2.put_start_and_end_on(p1, p2)
            d1.move_to(p1)
            d2.move_to(p2)

        # Updater to evolve physics each frame
        def evolve_physics(mob):
            nonlocal state_cyan, state_magenta
            # Multiple substeps per frame for stability
            for _ in range(5):
                state_cyan = rk4_step(state_cyan, dt/5)
                state_magenta = rk4_step(state_magenta, dt/5)
                
            update_pendulum(line1_c, line2_c, dot1_c, dot2_c, state_cyan, CYAN_COLOR)
            update_pendulum(line1_m, line2_m, dot1_m, dot2_m, state_magenta, MAGENTA_COLOR)

        # 4. Simulation
        self.play(FadeIn(text_group), FadeIn(ps_axes))
        
        # Attach updater to an invisible mobject to drive simulation
        driver = Mobject()
        driver.add_updater(evolve_physics)
        self.add(driver)
        
        # Run simulation for 10 seconds
        self.wait(10.0)
        
        driver.remove_updater(evolve_physics)
        self.wait(1)
"""

def main():
    render_dir = os.path.join(PROJECT_ROOT, "_pendulum_render")
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
