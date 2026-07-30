import os
from typing import Dict, Any, Optional, List
import re
import math
from typing import Sequence

from vivacity_constants import (
    BACKGROUND_COLOR,
    EQUATION_COLOR,
    PRIMARY_COLOR,
    SECONDARY_COLOR,
    MUTED_COLOR,
)

try:
    from manim import *
except ImportError:
    pass  # Allow running tests without Manim installed

# Craft Constants
CRAFT_TITLE_FONT_SIZE = 48
CRAFT_BODY_FONT_SIZE = 36
CRAFT_EQUATION_FONT_SIZE = 42

# Premium Cinematic Color Palette
CRAFT_BG_COLOR = BACKGROUND_COLOR
CRAFT_AXES_COLOR = MUTED_COLOR
CRAFT_TEXT_COLOR = MUTED_COLOR

CRAFT_CURVE_COLOR = EQUATION_COLOR
CRAFT_TANGENT_COLOR = SECONDARY_COLOR
CRAFT_DOT_COLOR = PRIMARY_COLOR
CRAFT_AREA_COLOR = PRIMARY_COLOR
CRAFT_CIRCLE_COLOR = SECONDARY_COLOR

def get_luminance(hex_color: str) -> float:
    """Calculate relative luminance of a hex color."""
    if not isinstance(hex_color, str):
        from manim.utils.color.core import color_to_rgb

        rgb = color_to_rgb(hex_color)
        return 0.2126 * float(rgb[0]) + 0.7152 * float(rgb[1]) + 0.0722 * float(rgb[2])
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c + c for c in hex_color)
    r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def adjust(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)

def ensure_contrast(text_color: str, background_color: str):
    """Text color must have sufficient luminance difference from background."""
    lum_bg = get_luminance(background_color)
    lum_fg = get_luminance(text_color)
    ratio = (max(lum_fg, lum_bg) + 0.05) / (min(lum_fg, lum_bg) + 0.05)
    if ratio < 3.0:
        raise ValueError(f"Contrast ratio {ratio:.2f} too low between text ({text_color}) and bg ({background_color})")



def fit_to_frame(mobject, max_width_ratio=0.9, max_height_ratio=0.9):
    """Scale mobject down if it exceeds safe frame bounds. Never scales up."""
    frame_width = config.frame_width * max_width_ratio
    frame_height = config.frame_height * max_height_ratio
    if mobject.width > frame_width:
        mobject.scale_to_fit_width(frame_width)
    if mobject.height > frame_height:
        mobject.scale_to_fit_height(frame_height)
    return mobject

def wrap_text(text: str, max_chars_per_line: int = 30) -> str:
    words = text.split(" ")
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_chars_per_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1
    if current_line:
        lines.append(" ".join(current_line))
    return "\n".join(lines)

def format_title_text(text: str) -> str:
    formatted = text
    formatted = formatted.replace("f(x)=x^3-3x^2+4", "f(x) = x³ − 3x² + 4")
    formatted = formatted.replace("f(x)=x^3?3x^2+4", "f(x) = x³ − 3x² + 4")
    formatted = formatted.replace("f'(x)=3x^2-6x=3x(x-2)", "f'(x) = 3x² − 6x = 3x(x − 2)")
    formatted = formatted.replace("f'(x)=3x^2?6x=3x(x?2)", "f'(x) = 3x² − 6x = 3x(x − 2)")
    formatted = formatted.replace("x^3-3x^2+4", "x³ − 3x² + 4")
    formatted = formatted.replace("x^3?3x^2+4", "x³ − 3x² + 4")
    formatted = formatted.replace("x^3", "x³")
    formatted = formatted.replace("3x^2", "3x²")
    formatted = formatted.replace("(x-2)^2(x+1)", "(x − 2)²(x + 1)")
    formatted = formatted.replace("(x?2)^2(x+1)", "(x − 2)²(x + 1)")
    formatted = formatted.replace("y=0", "y = 0")
    formatted = formatted.replace("P(-1,0)", "P(−1, 0)")
    formatted = formatted.replace("P(?-1,0)", "P(−1, 0)")
    formatted = formatted.replace("A=27/4", "A = 27/4")
    formatted = formatted.replace("r=2", "r = 2")
    formatted = formatted.replace("x^2+(y-2)^2=4", "x² + (y − 2)² = 4")
    formatted = formatted.replace("x^2+(y?2)^2=4", "x² + (y − 2)² = 4")
    # Fix LLM-generated camelCase merges in titles: "Maclaurinlimit" → "Maclaurin limit"
    # Only split on lowercase→uppercase transitions (not acronyms like "P3" or math)
    # Skip strings containing math characters to avoid breaking equations
    if not re.search(r"[\\$^_{}=\d]", formatted):
        formatted = re.sub(r"([a-z])([A-Z])", r"\1 \2", formatted)
    return formatted


def clean_latex_string(s: str) -> str:
    if not s:
        return s
    cleaned = s
    # Dashes
    cleaned = cleaned.replace("−", "-").replace("–", "-").replace("—", "-")
    # Superscript digits
    cleaned = cleaned.replace("²", "^2").replace("³", "^3").replace("⁴", "^4")
    cleaned = cleaned.replace("⁻¹", "^{-1}")
    # Subscript digits
    cleaned = cleaned.translate(str.maketrans({"₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4", "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9"}))
    # Common operators
    cleaned = cleaned.replace("·", "\\cdot").replace("×", "\\times").replace("÷", "\\div")
    cleaned = cleaned.replace("±", "\\pm").replace("′", "'")
    cleaned = cleaned.replace("≤", "\\leq ").replace("≥", "\\geq ").replace("≠", "\\neq ")
    cleaned = cleaned.replace("≈", "\\approx ").replace("≡", "\\equiv ").replace("∝", "\\propto ")
    cleaned = cleaned.replace("∈", "\\in ").replace("∉", "\\notin ")
    cleaned = cleaned.replace("∠", "\\angle ").replace("⊥", "\\perp ").replace("∥", "\\parallel ")
    # Calculus
    cleaned = cleaned.replace("∫", "\\int ").replace("∂", "\\partial ").replace("∞", "\\infty")
    # Summation / product
    cleaned = cleaned.replace("Σ", "\\sum ").replace("∑", "\\sum ")
    cleaned = cleaned.replace("Π", "\\Pi ").replace("∏", "\\prod ")
    # Greek uppercase
    cleaned = cleaned.replace("Δ", "\\Delta ").replace("∇", "\\nabla ")
    cleaned = cleaned.replace("Ω", "\\Omega ").replace("Φ", "\\Phi ")
    cleaned = cleaned.replace("Ψ", "\\Psi ").replace("Γ", "\\Gamma ")
    cleaned = cleaned.replace("Λ", "\\Lambda ")
    # Greek lowercase
    cleaned = cleaned.replace("α", "\\alpha ").replace("β", "\\beta ")
    cleaned = cleaned.replace("γ", "\\gamma ").replace("δ", "\\delta ")
    cleaned = cleaned.replace("ε", "\\epsilon ").replace("η", "\\eta ")
    cleaned = cleaned.replace("θ", "\\theta ").replace("λ", "\\lambda ")
    cleaned = cleaned.replace("μ", "\\mu ").replace("ν", "\\nu ")
    cleaned = cleaned.replace("ξ", "\\xi ").replace("π", "\\pi ")
    cleaned = cleaned.replace("ρ", "\\rho ").replace("σ", "\\sigma ")
    cleaned = cleaned.replace("τ", "\\tau ").replace("υ", "\\upsilon ")
    cleaned = cleaned.replace("φ", "\\phi ").replace("χ", "\\chi ")
    cleaned = cleaned.replace("ψ", "\\psi ").replace("ω", "\\omega ")
    # Fix bare-paren superscripts: f^(n) → f^{n}
    cleaned = re.sub(r"\^\(([^)]{1,40})\)", r"^{\1}", cleaned)
    # Implicit multiplication: a2 → a^2 (only trailing single digits)
    cleaned = re.sub(r"(?<![a-zA-Z])([a-zA-Z])([23456789])", r"\1^\2", cleaned)
    return cleaned


def create_mixed_text(text: str, font_size: float, color=None, weight=NORMAL) -> VMobject:
    if color is None:
        color = CRAFT_TEXT_COLOR
    ensure_contrast(color, CRAFT_BG_COLOR)
    import re
    if not text:
        return VMobject()

    cleaned_text = clean_latex_string(text)

    # Detect if the entire string is pure LaTeX:
    # - Contains a backslash "\" (indicating LaTeX commands like \text, \frac, \int, \cdot, etc.)
    # - Contains no spaces at all (e.g. "f(x)=x^3-3x^2+4")
    # - Is wrapped in a single pair of "$" (e.g. "$A = \int f(x) dx$")
    has_backslash = "\\" in cleaned_text
    has_spaces = " " in cleaned_text.strip()
    is_wrapped = cleaned_text.startswith("$") and cleaned_text.endswith("$") and cleaned_text.count("$") == 2

    # Check for common mathematical English words to determine if it is mixed text
    common_words = {"at", "the", "value", "is", "and", "to", "from", "of", "in", "equals", "its", "point", "center", "roots", "with", "evaluate", "substitute", "compute", "find", "solve", "factor", "intersection", "tangent", "line", "local", "maximum", "minimum", "extrema", "shaded", "region", "enclosed", "between", "exact", "area", "radius", "circle", "centered", "on", "y-axis", "distance"}
    words_in_text = set(re.findall(r"\b[a-zA-Z]+\b", cleaned_text.lower()))
    has_prose = not words_in_text.isdisjoint(common_words)

    if (has_backslash and "$" not in cleaned_text) or (has_backslash and not has_prose) or (not has_spaces) or is_wrapped:
        math_str = cleaned_text[1:-1] if is_wrapped else cleaned_text
        try:
            return MathTex(math_str, font_size=font_size, color=color)
        except Exception:
            pass  # Fall back to mixed rendering if MathTex fails

    processed = cleaned_text
    if "$" not in processed:
        # Wrap coordinates: e.g. P(-1,0), (0,4), (0,r)
        processed = re.sub(r"([a-zA-Z]?\(-?\w+,\s*\w+\))", r"$\1$", processed)
        # Wrap equation-like parts containing '=': e.g. x=2, y=0, r=2, A=27/4, |4-r|=r
        processed = re.sub(r"([a-zA-Z0-9_'\(\)\|\\,\s\+\-\*/\^]+=[a-zA-Z0-9_'\(\)\|\\,\s\+\-\*/\^]+)", 
                           lambda m: f"${m.group(1).strip()}$" if any(c in m.group(1) for c in "+-*/^()_'") or re.search(r"\b(x|y|r|f|A)\b", m.group(1)) else m.group(0), 
                           processed)
        # Wrap expressions with math operators: e.g. x^3-3x^2+4, x^4/4-x^3+4x
        processed = re.sub(r"(\b[a-zA-Z0-9_\(\)]*(?:[\^\+\-\*/][a-zA-Z0-9_\(\)]+)+)", r"$\1$", processed)
        # Wrap standalone single-letter variables: x, y, r, A
        processed = re.sub(r"\b([xyrA])\b", r"$\1$", processed)
        # Wrap standalone fractions: e.g. 27/4, 16/4
        processed = re.sub(r"(\b\d+/\d+\b)", r"$\1$", processed)
        # Clean double $$
        processed = processed.replace("$$", "$")

    parts = processed.split("$")
    mobjects = []
    current_line = []
    
    for idx, part in enumerate(parts):
        if not part:
            continue
        if idx % 2 == 0:
            # Even: plain text
            words = part.split(" ")
            for w_idx, word in enumerate(words):
                if not word.strip():
                    continue
                if "\n" in word:
                    subwords = word.split("\n")
                    for sw_idx, sw in enumerate(subwords):
                        if sw.strip():
                            current_line.append(Text(sw.strip(), font_size=font_size, color=color, weight=weight))
                        if sw_idx < len(subwords) - 1:
                            if current_line:
                                mobjects.append(VGroup(*current_line).arrange(RIGHT, buff=0.12))
                                current_line = []
                else:
                    current_line.append(Text(word.strip(), font_size=font_size, color=color, weight=weight))
        else:
            # Odd: math
            cleaned_math = clean_latex_string(part)
            if not cleaned_math.strip():
                continue
            try:
                current_line.append(MathTex(cleaned_math.strip(), font_size=font_size, color=color))
            except Exception:
                current_line.append(Text(part.strip(), font_size=font_size, color=color, weight=weight))
                
    if current_line:
        mobjects.append(VGroup(*current_line).arrange(RIGHT, buff=0.12))
        
    if not mobjects:
        return VMobject()
    if len(mobjects) == 1:
        return mobjects[0]
    else:
        return VGroup(*mobjects).arrange(DOWN, buff=0.25)

def get_mobject_latex_or_text(mob) -> str:
    if not mob:
        return ""
    if isinstance(mob, MathTex):
        return "".join(mob.tex_strings)
    elif isinstance(mob, Text):
        return mob.text
    elif hasattr(mob, "submobjects") and mob.submobjects:
        return "".join(get_mobject_latex_or_text(sub) for sub in mob.submobjects)
    return ""

class CraftContext:
    """
    Maintains persistent state across template calls for a single video.
    Enforces color semantics and consistent settings.
    """
    def __init__(self, scene: "Scene", orientation: str = "portrait"):
        self.scene = scene
        self.orientation = orientation
        self.scene.camera.background_color = CRAFT_BG_COLOR
        self.semantic_colors: Dict[str, str] = {}
        # Predefined pleasing palette to pull from
        self.available_colors = [
            CRAFT_CURVE_COLOR, CRAFT_TANGENT_COLOR, CRAFT_DOT_COLOR, CRAFT_AREA_COLOR, CRAFT_CIRCLE_COLOR
        ]
        self.color_index = 0
        self.previous_visuals: List[Any] = []
        
        # Track active mobjects by categories to prevent overlaps and clean up stale ones
        self.persistent_geometry: List[Any] = []
        self.temporary_labels: List[Any] = []
        self.current_heading: Optional[Any] = None
        self.current_equation: Optional[Any] = None
        self.graph_elements: Dict[str, Any] = {}

    def get_color(self, semantic_name: str) -> str:
        """Assigns and persists a color for a mathematical object/variable."""
        semantic_name = semantic_name.strip().lower()
        if semantic_name not in self.semantic_colors:
            self.semantic_colors[semantic_name] = self.available_colors[self.color_index % len(self.available_colors)]
            self.color_index += 1
        return self.semantic_colors[semantic_name]

    def remove_recursively(self, mob):
        if not mob:
            return
        # Fixed-in-frame mobjects are tracked separately by Manim. Removing
        # only from scene.mobjects leaves ghost headings behind on later beats.
        if hasattr(self.scene, "remove_fixed_in_frame_mobjects"):
            self.scene.remove_fixed_in_frame_mobjects(mob)
        self.scene.remove(mob)
        if hasattr(mob, "submobjects") and mob.submobjects:
            for sub in mob.submobjects:
                self.remove_recursively(sub)

    def add_fixed(self, mob):
        """Forces an onscreen label or formula to remain fixed in screen-space."""
        if not mob:
            return
        if hasattr(self.scene, "add_fixed_in_frame_mobjects"):
            self.scene.add_fixed_in_frame_mobjects(mob)

    def smooth_wait(self, duration: float = 3.0):
        """Slowly and linearly zooms the camera frame to create continuous flow."""
        if hasattr(self.scene, "camera") and hasattr(self.scene.camera, "frame"):
            current_width = self.scene.camera.frame.width
            default_width = config.frame_width
            
            # Bound camera frame width between 94% and 106% of default to prevent overflows
            if current_width < default_width * 0.94:
                scale_factor = 1.008
            elif current_width > default_width * 1.06:
                scale_factor = 0.992
            else:
                scale_factor = 0.994
                
            self.scene.play(
                self.scene.camera.frame.animate.scale(scale_factor),
                run_time=duration,
                rate_func=rate_functions.linear
            )
        else:
            self.scene.wait(duration)

    def prepare_beat(self, beat_type: str, keep_current_equation: bool = False):
        """
        Clears the scene state in preparation for a new beat.
        If beat_type is full-screen text ('concept', 'compare'), we clear EVERYTHING.
        If beat_type is math/graph ('plot', 'equation'), we keep persistent geometry,
        but clear temporary labels, equations, and headings.
        """
        fade_outs = []
        
        # Always fade out previous headings
        if self.current_heading:
            fade_outs.append(FadeOut(self.current_heading))
            
        # Fade out equation if not morphing from it
        if self.current_equation and not keep_current_equation:
            fade_outs.append(FadeOut(self.current_equation))
            
        # Always fade out temporary labels from the previous beat
        for mob in self.temporary_labels:
            fade_outs.append(FadeOut(mob))
            
        # If transitioning to a full-screen text beat, we also clear all graph/persistent geometry
        if beat_type in ['concept', 'compare']:
            if "axes" in self.graph_elements:
                # Do NOT clear graph/axes elements to maintain persistent layout
                pass
            else:
                for mob in self.persistent_geometry:
                    fade_outs.append(FadeOut(mob))
                for name, mob in self.graph_elements.items():
                    fade_outs.append(FadeOut(mob))
                self.persistent_geometry = []
                self.graph_elements = {}
            
        if fade_outs:
            self.scene.play(*fade_outs, run_time=0.6)
            # Explicitly remove them recursively to prevent any ghosting or stale rendering references
            if beat_type in ['concept', 'compare']:
                for mob in self.persistent_geometry:
                    self.remove_recursively(mob)
                for name, mob in self.graph_elements.items():
                    self.remove_recursively(mob)
            if self.current_heading:
                self.remove_recursively(self.current_heading)
            if self.current_equation and not keep_current_equation:
                self.remove_recursively(self.current_equation)
            for mob in self.temporary_labels:
                self.remove_recursively(mob)
                
        self.current_heading = None
        if not keep_current_equation:
            self.current_equation = None
        self.temporary_labels = []

    def clear_screen(self, run_time=0.6):
        """Clears the screen cleanly (wrapper for concept mode)."""
        self.prepare_beat('concept')


def introduce_concept(ctx: CraftContext, title: str, text: Optional[str] = None):
    """Template 1: Introduce a concept with a title and optional subtitle."""
    ctx.prepare_beat('concept')
    
    formatted_title = wrap_text(format_title_text(title), max_chars_per_line=15)
    title_mob = create_mixed_text(formatted_title, font_size=CRAFT_TITLE_FONT_SIZE, color=CRAFT_TEXT_COLOR, weight=BOLD)
    group = VGroup(title_mob)
    
    if text:
        formatted_text = wrap_text(format_title_text(text), max_chars_per_line=18)
        sub_mob = create_mixed_text(formatted_text, font_size=CRAFT_BODY_FONT_SIZE, color=CRAFT_TEXT_COLOR)
        group.add(sub_mob)
    
    group.arrange(DOWN, buff=0.6)
    
    # Graph-aware layout positioning in portrait mode (no absolute offsets)
    if ctx.orientation == "portrait":
        group.scale_to_fit_width(config.frame_width * 0.85)
    
    # Strictly bind text group to frame edge without hardcoded UP values
    group.to_edge(UP, buff=0.5)
    
    ctx.add_fixed(group)
    
    ctx.scene.play(Write(title_mob), rate_func=rate_functions.ease_in_out_sine, run_time=1.2)
    if text:
        ctx.scene.play(FadeIn(sub_mob, shift=UP*0.2), rate_func=rate_functions.ease_in_out_sine, run_time=1.0)
    
    ctx.scene.wait(0.8) # Purposeful hold
    ctx.temporary_labels.append(group)

def transform_equation(ctx: CraftContext, old_eq: str, new_eq: str, heading: Optional[str] = None):
    """Template 2: Morph one equation into another without hard cuts."""
    source_mob = ctx.current_equation
    
    # 1. Search for matching on-screen equation if current_equation is None
    if not source_mob:
        normalized_old = old_eq.replace(" ", "").replace("\\,", "").replace("−", "-").replace("³", "^3").replace("²", "^2")
        for name, mob in list(ctx.graph_elements.items()):
            tex_string = get_mobject_latex_or_text(mob).replace(" ", "").replace("\\,", "").replace("−", "-").replace("³", "^3").replace("²", "^2")
            if tex_string and (normalized_old == tex_string or (len(tex_string) > 3 and abs(len(tex_string) - len(normalized_old)) <= 3 and (normalized_old in tex_string or tex_string in normalized_old))):
                source_mob = mob
                # Pop from graph_elements so it's not faded out as graph element later
                ctx.graph_elements.pop(name, None)
                break

    # Prepare the beat, keeping the current equation for the transition
    ctx.prepare_beat('equation', keep_current_equation=True)
    
    old_eq_clean = clean_latex_string(old_eq)
    new_eq_clean = clean_latex_string(new_eq)
    # Let create_mixed_text parse equations: pure LaTeX becomes MathTex, mixed becomes VGroup
    eq_old = create_mixed_text(old_eq_clean, font_size=CRAFT_EQUATION_FONT_SIZE)
    eq_new = create_mixed_text(new_eq_clean, font_size=CRAFT_EQUATION_FONT_SIZE)
    
    # Constrain width so long equations don't overflow frame
    _max_eq_w = config.frame_width * 0.88
    if eq_old.width > _max_eq_w:
        eq_old.scale_to_fit_width(_max_eq_w)
    if eq_new.width > _max_eq_w:
        eq_new.scale_to_fit_width(_max_eq_w)
    
    if heading:
        # Wrap heading to multiple lines if needed and format LaTeX strings
        formatted_heading = wrap_text(format_title_text(heading), max_chars_per_line=18)
        heading_mob = create_mixed_text(formatted_heading, font_size=CRAFT_BODY_FONT_SIZE, color=CRAFT_TEXT_COLOR, weight=BOLD)
        heading_mob.to_edge(UP, buff=0.5)
        ctx.add_fixed(heading_mob)
        ctx.scene.play(Write(heading_mob), run_time=0.8)
        ctx.current_heading = heading_mob
        
        # Dynamic relative stacking per strict architectural rules
        eq_old.next_to(heading_mob, DOWN, buff=0.4)
        eq_new.next_to(heading_mob, DOWN, buff=0.4)
    else:
        # Without heading, just anchor to the text safe-zone
        eq_old.to_edge(UP, buff=0.5)
        eq_new.to_edge(UP, buff=0.5)
        
    ctx.add_fixed(eq_old)
    ctx.add_fixed(eq_new)
        
    if source_mob:
        # Check if source_mob matches old_eq
        source_tex = get_mobject_latex_or_text(source_mob).replace(" ", "").replace("\\,", "").replace("−", "-").replace("³", "^3").replace("²", "^2")
        normalized_old = old_eq_clean.replace(" ", "").replace("\\,", "").replace("−", "-").replace("³", "^3").replace("²", "^2")
        if source_tex == normalized_old or (len(source_tex) > 3 and abs(len(source_tex) - len(normalized_old)) <= 3 and (normalized_old in source_tex or source_tex in normalized_old)):
            # Matches! Morph directly from source_mob to eq_new
            # If the size difference is large, use Pattern B to avoid glyph scrambling
            old_len = len(source_tex)
            new_len = len(new_eq_clean.replace(" ", ""))
            if abs(old_len - new_len) > 4:
                ctx.scene.play(FadeOut(source_mob), run_time=0.6)
                ctx.scene.remove(source_mob)
                ctx.scene.play(FadeIn(eq_new), run_time=1.0)
            else:
                ctx.scene.play(ReplacementTransform(source_mob, eq_new), rate_func=rate_functions.smooth, run_time=1.5)
                ctx.scene.remove(source_mob)
        else:
            # Does not match! Fade out source_mob, Write eq_old, then Morph to eq_new
            ctx.scene.play(FadeOut(source_mob), run_time=0.6)
            ctx.scene.remove(source_mob)
            ctx.scene.play(Write(eq_old), rate_func=rate_functions.smooth, run_time=1.0)
            ctx.scene.wait(0.5)
            
            old_len = len(old_eq_clean.replace(" ", ""))
            new_len = len(new_eq_clean.replace(" ", ""))
            if abs(old_len - new_len) > 4:
                ctx.scene.play(FadeOut(eq_old), run_time=0.6)
                ctx.scene.remove(eq_old)
                ctx.scene.play(FadeIn(eq_new), run_time=1.0)
            else:
                ctx.scene.play(ReplacementTransform(eq_old, eq_new), rate_func=rate_functions.smooth, run_time=1.5)
                ctx.scene.remove(eq_old)
    else:
        ctx.scene.play(Write(eq_old), rate_func=rate_functions.smooth, run_time=1.0)
        ctx.scene.wait(0.5)
        
        old_len = len(old_eq_clean.replace(" ", ""))
        new_len = len(new_eq_clean.replace(" ", ""))
        if abs(old_len - new_len) > 4:
            ctx.scene.play(FadeOut(eq_old), run_time=0.6)
            ctx.scene.remove(eq_old)
            ctx.scene.play(FadeIn(eq_new), run_time=1.0)
        else:
            ctx.scene.play(ReplacementTransform(eq_old, eq_new), rate_func=rate_functions.smooth, run_time=1.5)
            ctx.scene.remove(eq_old)
        
    ctx.scene.wait(0.8) # Purposeful hold
    ctx.current_equation = eq_new

def compare_side_by_side(ctx: CraftContext, left_text: str, left_eq: str, right_text: str, right_eq: str, heading: Optional[str] = None):
    """Template 3: Compare two concepts side by side."""
    ctx.prepare_beat('compare')
    
    group = VGroup()
    if heading:
        formatted_heading = wrap_text(format_title_text(heading), max_chars_per_line=15)
        heading_mob = create_mixed_text(formatted_heading, font_size=CRAFT_TITLE_FONT_SIZE, color=CRAFT_TEXT_COLOR, weight=BOLD)
        heading_mob.to_edge(UP, buff=0.5)
        ctx.add_fixed(heading_mob)
        ctx.scene.play(Write(heading_mob), run_time=1.0)
        ctx.current_heading = heading_mob
        
    # Wrap text for side-by-side comparison to keep it legible in portrait mode
    left_eq = clean_latex_string(left_eq)
    right_eq = clean_latex_string(right_eq)

    wrapped_l_text = wrap_text(format_title_text(left_text), max_chars_per_line=18)
    # Equations in side-by-side are mixed-aware
    left_eq_mob = create_mixed_text(left_eq, font_size=CRAFT_EQUATION_FONT_SIZE, color=CRAFT_TEXT_COLOR)
    if left_eq_mob.width > config.frame_width * 0.42:
        left_eq_mob.scale_to_fit_width(config.frame_width * 0.42)
    left_group = VGroup(
        create_mixed_text(wrapped_l_text, font_size=CRAFT_BODY_FONT_SIZE, color=LIGHT_GREY),
        left_eq_mob
    ).arrange(DOWN, buff=0.4)

    wrapped_r_text = wrap_text(format_title_text(right_text), max_chars_per_line=18)
    right_eq_mob = create_mixed_text(right_eq, font_size=CRAFT_EQUATION_FONT_SIZE, color=CRAFT_TEXT_COLOR)
    if right_eq_mob.width > config.frame_width * 0.42:
        right_eq_mob.scale_to_fit_width(config.frame_width * 0.42)
    right_group = VGroup(
        create_mixed_text(wrapped_r_text, font_size=CRAFT_BODY_FONT_SIZE, color=LIGHT_GREY),
        right_eq_mob
    ).arrange(DOWN, buff=0.4)
    
    compare_group = VGroup(left_group, right_group)
    if "axes" in ctx.graph_elements:
        compare_group.arrange(RIGHT, buff=0.4)
        if ctx.orientation == "portrait":
            compare_group.scale_to_fit_width(config.frame_width * 0.9)
            compare_group.move_to(UP * 1.3)
    elif ctx.orientation == "portrait":
        compare_group.arrange(DOWN, buff=1.0)
    else:
        compare_group.arrange(RIGHT, buff=1.5)
        
    ctx.add_fixed(compare_group)
    
    ctx.scene.play(
        FadeIn(left_group, shift=UP*0.2), 
        rate_func=rate_functions.ease_in_out_sine, 
        run_time=1.2
    )
    ctx.scene.wait(0.4)
    ctx.scene.play(
        FadeIn(right_group, shift=UP*0.2), 
        rate_func=rate_functions.ease_in_out_sine, 
        run_time=1.2
    )
    
    ctx.scene.wait(0.8)
    ctx.temporary_labels.append(compare_group)

def plot_math_curve_with_tangent_and_area(ctx: CraftContext, heading: Optional[str] = None):
    """Template 4: Plot a function curve with its tangent line, shaded area, and inscribed circle."""
    ctx.prepare_beat('plot')
    
    if heading:
        formatted_heading = wrap_text(format_title_text(heading), max_chars_per_line=15)
        heading_mob = create_mixed_text(formatted_heading, font_size=CRAFT_TITLE_FONT_SIZE, color=CRAFT_TEXT_COLOR, weight=BOLD)
        heading_mob.to_edge(UP, buff=0.4)
        ctx.add_fixed(heading_mob)
        ctx.scene.play(Write(heading_mob), run_time=0.8)
        ctx.current_heading = heading_mob

    # 1. Setup or Retrieve Axes
    if "axes" in ctx.graph_elements:
        axes = ctx.graph_elements["axes"]
    else:
        x_len = 3.8 if ctx.orientation == "portrait" else 5.5
        y_len = 3.2 if ctx.orientation == "portrait" else 4.5
        axes_pos = DOWN * 0.8 if ctx.orientation == "portrait" else DOWN * 0.5
        axes = Axes(
            x_range=[-2.2, 3.5, 1],
            y_range=[-3, 5, 1],
            x_length=x_len,
            y_length=y_len,
            tips=False,
            axis_config={"color": CRAFT_AXES_COLOR, "stroke_opacity": 0.5},
        )
        axes.move_to(axes_pos)
        ctx.scene.play(Create(axes), run_time=1.0)
        ctx.graph_elements["axes"] = axes

    # 2. Setup or Retrieve Curve and label
    if "curve" in ctx.graph_elements:
        curve = ctx.graph_elements["curve"]
    else:
        # Background curve: dimmer than the active focal elements (opacity hierarchy)
        curve = axes.plot(lambda x: x**3 - 3*x**2 + 4, x_range=[-1.22, 3.1], color=CRAFT_CURVE_COLOR, stroke_opacity=0.85)
        curve_label = MathTex("f(x) = x^3 - 3x^2 + 4", font_size=24, color=CRAFT_CURVE_COLOR).next_to(axes.c2p(1.5, 4.5), RIGHT)
        curve_label.set_opacity(0.85)
        ctx.scene.play(Create(curve), run_time=1.2)
        ctx.scene.play(Write(curve_label), run_time=0.8)
        ctx.graph_elements["curve"] = curve
        ctx.graph_elements["curve_label"] = curve_label

    # 3. Setup or Retrieve Tangent Line and its point labels
    if "tangent_line" in ctx.graph_elements:
        tangent_line = ctx.graph_elements["tangent_line"]
    else:
        tangent_line = Line(
            start=axes.c2p(-1.8, 0),
            end=axes.c2p(3.2, 0),
            color=CRAFT_TANGENT_COLOR,
            stroke_width=4
        )
        tangent_label = MathTex("y = 0", font_size=24, color=CRAFT_TANGENT_COLOR).next_to(axes.c2p(2.8, 0), UP)
        p_dot = Dot(axes.c2p(-1, 0), color=CRAFT_DOT_COLOR)
        p_label = MathTex("P(-1,0)", font_size=24, color=CRAFT_DOT_COLOR).next_to(p_dot, DOWN + LEFT, buff=0.1)
        min_dot = Dot(axes.c2p(2, 0), color=CRAFT_DOT_COLOR)
        min_label = MathTex("(2,0)", font_size=24, color=CRAFT_DOT_COLOR).next_to(min_dot, DOWN + RIGHT, buff=0.1)
        
        ctx.scene.play(Create(tangent_line), run_time=1.0)
        ctx.scene.play(Write(tangent_label), run_time=0.8)
        ctx.scene.play(
            Create(p_dot), Write(p_label),
            Create(min_dot), Write(min_label),
            run_time=1.0
        )
        ctx.graph_elements["tangent_line"] = tangent_line
        ctx.graph_elements["tangent_label"] = tangent_label
        ctx.graph_elements["p_dot"] = p_dot
        ctx.graph_elements["p_label"] = p_label
        ctx.graph_elements["min_dot"] = min_dot
        ctx.graph_elements["min_label"] = min_label

    # Check which elements should be displayed based on heading content
    heading_text = heading.lower() if heading else ""
    show_all = any(w in heading_text for w in ["summary", "all", "final"])
    show_area = any(w in heading_text for w in ["area", "integral", "enclose", "shade"]) or show_all
    show_circle = any(w in heading_text for w in ["circle", "inscribed", "radius"]) or show_all

    # 4. Draw Shaded Area (and keep it if showing circle)
    if show_area or show_circle:
        if "area" not in ctx.graph_elements:
            area = axes.get_area(curve, x_range=[-1, 2], color=CRAFT_AREA_COLOR, opacity=0.25)
            area_label = MathTex("\\text{Area} = \\frac{27}{4}", font_size=24, color=CRAFT_AREA_COLOR).move_to(axes.c2p(0.5, 1.2))
            ctx.scene.play(FadeIn(area), run_time=1.0)
            ctx.scene.play(Write(area_label), run_time=0.8)
            ctx.graph_elements["area"] = area
            ctx.graph_elements["area_label"] = area_label

    # 5. Draw Circle components
    if show_circle:
        if "circle" not in ctx.graph_elements:
            max_dot = Dot(axes.c2p(0, 4), color=CRAFT_DOT_COLOR)
            max_label = MathTex("(0,4)", font_size=24, color=CRAFT_DOT_COLOR).next_to(max_dot, UP + RIGHT, buff=0.1)
            
            circle_center = axes.c2p(0, 2)
            scr_radius = axes.c2p(0, 2)[1] - axes.c2p(0, 0)[1]
            circle = Circle(radius=scr_radius, color=CRAFT_CIRCLE_COLOR).move_to(circle_center)
            circle_label = MathTex("r = 2", font_size=24, color=CRAFT_CIRCLE_COLOR).next_to(circle, LEFT, buff=0.2)
            circle_center_dot = Dot(circle_center, color=CRAFT_CIRCLE_COLOR)
            
            ctx.scene.play(Create(max_dot), Write(max_label), run_time=0.8)
            ctx.scene.play(
                Create(circle_center_dot),
                Create(circle),
                Write(circle_label),
                run_time=1.5
            )
            ctx.graph_elements["max_dot"] = max_dot
            ctx.graph_elements["max_label"] = max_label
            ctx.graph_elements["circle"] = circle
            ctx.graph_elements["circle_label"] = circle_label
            ctx.graph_elements["circle_center_dot"] = circle_center_dot

    ctx.scene.wait(1.5)


class LiveHistogram(VGroup):
    """Histogram whose bar geometry is derived from a live stage tracker."""

    STAGE_COUNTS = (
        (1, 1, 2, 1, 1, 1),
        (1, 2, 3, 2, 2, 1),
        (1, 3, 5, 4, 3, 1),
        (1, 4, 7, 6, 4, 1),
    )

    def __init__(self, axes, stage_tracker: ValueTracker):
        self.axes = axes
        self.stage_tracker = stage_tracker
        self._bars = always_redraw(self._build_bars)
        super().__init__(self._bars)

    def _build_bars(self):
        stage = min(int(round(self.stage_tracker.get_value())), len(self.STAGE_COUNTS) - 1)
        bars = VGroup()
        for center, count in zip((6, 12, 18, 24, 30, 36), self.STAGE_COUNTS[stage]):
            height = max(0.18, count / 8 * self.axes.y_length)
            bars.add(
                Rectangle(
                    width=self.axes.x_length / 8,
                    height=height,
                    stroke_color=CRAFT_CURVE_COLOR,
                    fill_color=CRAFT_CURVE_COLOR,
                    fill_opacity=0.58,
                ).move_to(self.axes.c2p(center, 0) + UP * (height / 2))
            )
        return bars


def plot_dice_distribution(
    ctx: CraftContext,
    heading: Optional[str] = None,
    dice_rolls: Optional[Sequence[int]] = None,
):
    """Show actual dice faces and a histogram that grows toward a bell shape."""
    ctx.prepare_beat("plot")

    if heading:
        heading_mob = create_mixed_text(
            wrap_text(format_title_text(heading), max_chars_per_line=22),
            font_size=CRAFT_BODY_FONT_SIZE,
            color=CRAFT_TEXT_COLOR,
            weight=BOLD,
        )
        fit_to_frame(heading_mob, 0.88, 0.12)
        heading_mob.to_edge(UP, buff=0.35)
        ctx.add_fixed(heading_mob)
        ctx.scene.play(FadeIn(heading_mob, shift=UP * 0.12), run_time=0.8)
        ctx.current_heading = heading_mob

    axes = ctx.graph_elements.get("dice_axes")
    if axes is None:
        axes = Axes(
            x_range=[0, 42, 6],
            y_range=[0, 8, 2],
            x_length=4.0 if ctx.orientation == "portrait" else 6.0,
            y_length=3.0 if ctx.orientation == "portrait" else 3.6,
            tips=False,
            axis_config={"color": CRAFT_AXES_COLOR, "stroke_opacity": 0.7},
        ).move_to(DOWN * (0.7 if ctx.orientation == "portrait" else 0.4))
        axes.x_axis.add_numbers([6, 12, 18, 24, 30, 36], font_size=18, color=CRAFT_TEXT_COLOR)
        x_label = Text("sum of dice", font_size=22, color=CRAFT_TEXT_COLOR).next_to(axes, DOWN, buff=0.18)
        y_label = Text("frequency", font_size=22, color=CRAFT_TEXT_COLOR).rotate(PI / 2).next_to(axes, LEFT, buff=0.18)
        ctx.scene.play(Create(axes), FadeIn(VGroup(x_label, y_label)), run_time=1.0)
        ctx.graph_elements["dice_axes"] = axes
        ctx.graph_elements["dice_axis_labels"] = VGroup(x_label, y_label)

        dice = VGroup()
        values = tuple(dice_rolls or (3, 5, 2, 4, 6, 1))
        if len(values) != 6 or any(value not in range(1, 7) for value in values):
            raise ValueError("dice_rolls must contain exactly six values in the range 1..6")
        for value in values:
            die = RoundedRectangle(
                corner_radius=0.08,
                width=0.48,
                height=0.48,
                stroke_color=CRAFT_AREA_COLOR,
                fill_color=CRAFT_AREA_COLOR,
                fill_opacity=0.18,
            )
            die_label = Text(str(value), font_size=24, color=CRAFT_AREA_COLOR).move_to(die)
            dice.add(VGroup(die, die_label))
        dice.arrange(RIGHT, buff=0.1).move_to(UP * 2.05)
        dice_caption = Text("one roll of six fair dice", font_size=22, color=CRAFT_TEXT_COLOR).next_to(dice, DOWN, buff=0.12)
        ctx.scene.play(Create(dice), FadeIn(dice_caption), run_time=1.2)
        ctx.graph_elements["dice_faces"] = dice
        ctx.graph_elements["dice_caption"] = dice_caption
        trial_tracker = ValueTracker(0)
        trial_label = always_redraw(
            lambda: MathTex(
                rf"n={[1, 10, 100, 1000][min(int(round(trial_tracker.get_value())), 3)]}",
                color=CRAFT_AREA_COLOR,
                font_size=26,
            ).move_to(axes.c2p(4, 7.35))
        )
        ctx.scene.play(FadeIn(trial_label), run_time=0.5)
        ctx.graph_elements["trial_tracker"] = trial_tracker
        ctx.graph_elements["trial_label"] = trial_label

    # Roll each persistent die independently. A staggered local spin and
    # bounce reads as six dice being thrown, rather than one rigid row rotating.
    dice = ctx.graph_elements["dice_faces"]
    roll_animations = []
    for die in dice:
        center = die.get_center().copy()
        die.generate_target()
        die.target.shift(UP * 0.16)
        die.target.rotate(PI, about_point=center)
        first_roll = MoveToTarget(die)
        die.generate_target()
        die.target.shift(DOWN * 0.16)
        die.target.rotate(PI, about_point=center)
        second_roll = MoveToTarget(die)
        roll_animations.append(
            Succession(
                first_roll,
                second_roll,
            )
        )
    ctx.scene.play(
        LaggedStart(*roll_animations, lag_ratio=0.12),
        run_time=1.8,
        rate_func=rate_functions.ease_in_out_sine,
    )

    stage = int(ctx.graph_elements.get("dice_stage", 0))
    trial_tracker = ctx.graph_elements.get("trial_tracker")
    if trial_tracker is not None:
        ctx.scene.play(
            trial_tracker.animate.set_value((1, 10, 100, 1000)[min(stage, 3)]),
            run_time=0.7,
        )
    stage_tracker = ctx.graph_elements.get("dice_stage_tracker")
    histogram = ctx.graph_elements.get("dice_histogram")
    if stage_tracker is None:
        stage_tracker = ValueTracker(0)
        histogram = LiveHistogram(axes, stage_tracker)
        ctx.scene.play(FadeIn(histogram), run_time=1.0)
        ctx.graph_elements["dice_stage_tracker"] = stage_tracker
        ctx.graph_elements["dice_histogram"] = histogram
    else:
        ctx.scene.play(
            stage_tracker.animate.set_value(min(stage, 3)),
            run_time=1.2,
            rate_func=rate_functions.ease_in_out_sine,
        )
    ctx.graph_elements["dice_stage"] = min(stage + 1, 3)

    if "dice_mean_line" not in ctx.graph_elements:
        mean_line = DashedLine(
            axes.c2p(21, 0),
            axes.c2p(21, 7.5),
            color=CRAFT_AREA_COLOR,
            dash_length=0.12,
        )
        mean_label = MathTex(r"\mu=21", color=CRAFT_AREA_COLOR, font_size=26).move_to(
            axes.c2p(21, 7.75)
        )
        ctx.scene.play(Create(mean_line), FadeIn(mean_label), run_time=0.9)
        ctx.graph_elements["dice_mean_line"] = mean_line
        ctx.graph_elements["dice_mean_label"] = mean_label

    if stage >= 1 and "dice_normal_curve" not in ctx.graph_elements:
        normal_curve = axes.plot(
            lambda x: 6.8 * math.exp(-0.5 * ((x - 21) / 6.0) ** 2),
            x_range=[6, 36],
            color=CRAFT_AREA_COLOR,
            stroke_width=5,
        )
        ctx.scene.play(Create(normal_curve), run_time=1.3)
        ctx.graph_elements["dice_normal_curve"] = normal_curve

    note = Text(
        ["one trial", "more trials", "bell shape emerging", "normal-like shape"][min(stage, 3)],
        font_size=24,
        color=CRAFT_CURVE_COLOR,
    ).next_to(axes, UP, buff=0.18)
    fit_to_frame(note, 0.82, 0.10)
    ctx.scene.play(FadeIn(note, shift=UP * 0.1), run_time=0.5)
    ctx.scene.wait(0.8)
    # Give the slower voiceover room to explain the current distribution while
    # the histogram remains visible and the scene does not end in a dead hold.
    ctx.smooth_wait(1.2)
    ctx.temporary_labels.append(note)
