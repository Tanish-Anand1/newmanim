import os
import sys
import importlib.util
from manim import config, Scene, Text, Tex, MathTex, VGroup

def test_no_orphaned_text_mobjects(scene: Scene):
    """
    Fails if any Text/Tex mobject remains in scene after being 
    conceptually replaced.
    """
    # Look for multiple Text/Tex objects that overlap in their bounding boxes
    text_mobs = []
    for mob in scene.mobjects:
        if isinstance(mob, (Text, Tex, MathTex)):
            text_mobs.append(mob)
        elif isinstance(mob, VGroup):
            # Check if it contains text
            has_text = any(isinstance(sub, (Text, Tex, MathTex)) for sub in mob.submobjects)
            if has_text:
                text_mobs.append(mob)
                
    for i, mob1 in enumerate(text_mobs):
        for j, mob2 in enumerate(text_mobs):
            if i >= j: continue
            
            # Get bounding boxes
            left1, right1 = mob1.get_left()[0], mob1.get_right()[0]
            bottom1, top1 = mob1.get_bottom()[1], mob1.get_top()[1]
            
            left2, right2 = mob2.get_left()[0], mob2.get_right()[0]
            bottom2, top2 = mob2.get_bottom()[1], mob2.get_top()[1]
            
            # Check overlap
            overlap = not (right1 < left2 or right2 < left1 or top1 < bottom2 or top2 < bottom1)
            
            if overlap:
                # If they overlap significantly and are separate mobjects, it's an orphaned overwrite!
                raise ValueError(f"Orphaned text mobject detected! Double exposure overlap between '{mob1}' and '{mob2}'.")


def test_all_mobjects_within_frame(scene: Scene):
    """
    Fails if any mobject's bounding box exceeds frame bounds 
    at any point it's visible.
    """
    margin = 0.1
    safe_left = -config.frame_x_radius + margin
    safe_right = config.frame_x_radius - margin
    safe_top = config.frame_y_radius - margin
    safe_bottom = -config.frame_y_radius + margin
    
    for mob in scene.mobjects:
        if mob.width < 1e-4 and mob.height < 1e-4:
            continue
            
        left = mob.get_left()[0]
        right = mob.get_right()[0]
        bottom = mob.get_bottom()[1]
        top = mob.get_top()[1]
        
        if left < safe_left - 0.1 or right > safe_right + 0.1 or bottom < safe_bottom - 0.1 or top > safe_top + 0.1:
            raise ValueError(f"Mobject '{mob}' exceeds frame bounds! (Left: {left}, Right: {right}, Top: {top}, Bottom: {bottom})")

def run_render_acceptance(scene: Scene):
    """Run all acceptance tests against the constructed scene."""
    test_no_orphaned_text_mobjects(scene)
    test_all_mobjects_within_frame(scene)
