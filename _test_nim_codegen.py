"""Standalone test: NIM 8B for Manim code generation.

Feeds the NvidiaNimProvider a typical Manim code prompt and checks
whether it produces valid, parseable Python code or explanatory text.
"""
import os, sys, time, ast

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

os.environ["LLM_PROVIDER"] = "nvidia_nim"
os.environ["NVIDIA_NIM_MODEL"] = "meta/llama-3.1-8b-instruct"

from app.llm_provider import NvidiaNimProvider

# A typical storyboard used in the real pipeline
STORYBOARD = """[0-4] ON SCREEN: `f(x) = x^2` on a blackboard | VO: "Let's explore the derivative of x squared."
[4-8] ON SCREEN: the power rule `d/dx x^n = n x^(n-1)` | VO: "Recall the power rule: the derivative of x to the n is n times x to the n minus one."
[8-12] ON SCREEN: applying the rule: `d/dx x^2 = 2 x^(2-1) = 2x` | VO: "Applying the power rule with n equals 2, we get 2 times x to the 2 minus 1, which is 2x."
[12-16] ON SCREEN: final answer `f'(x) = 2x` | VO: "So the derivative of x squared is 2x."
"""

SCENE_NAME = "DerivativeScene"
ORIENTATION = "portrait"

# This mirrors the typical Manim codegen prompt structure from the pipeline
USER_PROMPT = f"""Write a Manim scene {SCENE_NAME} (portrait 9:16) that visualizes the storyboard below.

Storyboard:
{STORYBOARD}

Requirements:
- Use from manim_imports import *  (3b1b-style imports)
- Class name: {SCENE_NAME}
- Each beat window should be timed. Use wait() calls between animations.
- Portrait orientation: 1080x1920, use self.camera.frame_height = 16 and frame_width = 9
- Use Text, Tex, Write, Transform, FadeOut etc. from manim_imports
- Output ONLY valid Python code, no markdown fences, no explanations."""

print("=== NIM 8B Code Generation Test ===", flush=True)
print(f"Model: meta/llama-3.1-8b-instruct", flush=True)
print(f"Storyboard: {len(STORYBOARD)} chars", flush=True)
print(f"Prompt: {len(USER_PROMPT)} chars", flush=True)
print(flush=True)

provider = NvidiaNimProvider()
start = time.monotonic()

resp = provider.generate(
    system="You are a Manim animation expert. Output ONLY valid Python code. No markdown, no explanations.",
    user_message=USER_PROMPT,
    max_tokens=4000,
)
elapsed = time.monotonic() - start

text = resp.text.strip()
print(f"Elapsed: {elapsed:.1f}s", flush=True)
print(f"Provider: {resp.provider_name}", flush=True)
print(f"Model: {resp.model}", flush=True)
print(f"Input tokens: {resp.input_tokens}", flush=True)
print(f"Output tokens: {resp.output_tokens}", flush=True)
print(flush=True)

# Check 1: Does it contain explanatory text markers?
explanatory_markers = ["here's", "here is", "let me", "i'll", "i will", "the code", "explanation",
                       "this script", "this code", "sure!", "certainly", "of course", "note:"]
text_lower = text.lower()
has_explanations = sum(1 for m in explanatory_markers if m in text_lower)

# Check 2: Does it start with a code fence?
starts_with_fence = text.startswith("```")

# Check 3: Does it have class definition?
has_class = "class DerivativeScene" in text

# Check 4: Is it parseable Python?
is_parseable = False
parse_error = ""
try:
    # Remove common Manim-isms that the parser might choke on
    source = text
    if text.startswith("```"):
        source = text.split("\n", 1)[1]
        if "```" in source:
            source = source.split("```")[0]
    ast.parse(source)
    is_parseable = True
except SyntaxError as e:
    parse_error = str(e)

print("=== RESULTS ===", flush=True)
print(f"Output length: {len(text)} chars", flush=True)
print(f"Has class 'DerivativeScene': {has_class}", flush=True)
print(f"Parseable Python: {is_parseable}", flush=True)
print(f"Explanatory markers: {has_explanations}", flush=True)
print(f"Starts with fence: {starts_with_fence}", flush=True)
print(flush=True)
if parse_error:
    print(f"Parse error: {parse_error}", flush=True)
    print(flush=True)

print("--- FULL OUTPUT (first 2000 chars) ---", flush=True)
print(text[:2000], flush=True)
if len(text) > 2000:
    print(f"\n... ({len(text) - 2000} more chars)", flush=True)

# Verdict
print(flush=True)
print("=== VERDICT ===", flush=True)
if is_parseable and has_class:
    print("PASS: Generated clean, parseable Manim code.", flush=True)
elif is_parseable and not has_class:
    print("PARTIAL: Parseable Python but missing class definition.", flush=True)
elif not is_parseable and has_explanations > 3:
    print("FAIL: Generated explanatory text instead of code (3B-style failure).", flush=True)
elif not is_parseable:
    print(f"FAIL: Not parseable: {parse_error}", flush=True)
else:
    print("MIXED: Needs review.", flush=True)