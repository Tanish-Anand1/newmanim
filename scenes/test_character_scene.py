import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from manim import *
from vivacity_base_scene import VivacityScene
from app.vivacity_character import VivacityCharacter

class TestCharacterScene(VivacityScene):
    def construct(self):
        self.camera.background_color = "#0b1020"

        # Title
        title = self.safe_text("Vivacity Character Demo", zone="top", font_size=48)
        title.to_edge(UP, buff=0.4)
        self.play(FadeIn(title), run_time=0.8)
        self.wait(0.5)

        # Create character at left side, ensure no overlap
        char = VivacityCharacter(expression="neutral")
        char.scale(0.9)
        # Place left of center, vertical center
        char.move_to(LEFT * 3)
        self.safe_position(char, zone=None)  # not in specific zone
        self.play(FadeIn(char), run_time=0.8)
        self.wait(0.5)

        # Simulate recall checkpoint event
        self.play(char.blink())
        char.react_to("recall_checkpoint")
        self.wait(0.8)

        # Simulate edge-case reveal
        edge_text = self.safe_text("What if the function is discontinuous?", zone="bottom", font_size=32)
        edge_text.to_edge(DOWN, buff=0.4)
        self.play(FadeIn(edge_text), run_time=0.6)
        self.wait(0.5)
        char.react_to("edge_case_reveal")
        self.wait(1)

        # Correct answer celebration
        correct = self.safe_text("Correct! The limit exists.", zone="bottom", font_size=32)
        correct.to_edge(DOWN, buff=0.4)
        self.play(
            FadeOut(edge_text),
            FadeIn(correct),
            run_time=0.6,
        )
        char.react_to("correct_answer")
        self.wait(1.5)

        # Fade out
        self.play(
            FadeOut(title),
            FadeOut(char),
            FadeOut(correct),
            run_time=0.8,
        )