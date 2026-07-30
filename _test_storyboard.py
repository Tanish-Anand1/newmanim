"""Debug: test storyboard generation with NIM 8B Llama."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from app.llm_provider import NvidiaNimProvider
from app.vivacity_prompts import build_script_generation_system_prompt
from app.pipeline import parse_storyboard

topic = "Derivative of x^2"
audience = "high school"
duration = 30

system = build_script_generation_system_prompt(
    topic=topic,
    exam_context="JEE/NEET",
    flagged_as_weak_topic=False,
    unconfirmed_prerequisites=[],
)

user_msg = (
    f"Topic: {topic}\n"
    f"Required topic terms to preserve: {topic}\n"
    f"Audience: {audience}\n"
    f"Target duration: {duration} seconds\n\n"
    "Draft the storyboard now. Keep math claims conservative and teachable."
)

print("=== System prompt (first 500 chars) ===", flush=True)
print(system[:500], flush=True)
print("...", flush=True)
print(flush=True)

print("=== User message ===", flush=True)
print(user_msg, flush=True)
print(flush=True)

print("=== Calling NIM 8B Llama ===", flush=True)
provider = NvidiaNimProvider()
resp = provider.generate(
    system=system,
    user_message=user_msg,
    max_tokens=2000,
)
print(f"Elapsed: {resp.elapsed_s:.1f}s" if hasattr(resp, 'elapsed_s') else "N/A", flush=True)
print(flush=True)

text = resp.text.strip()
print("=== RAW OUTPUT ===", flush=True)
print(text, flush=True)
print(flush=True)

print("=== Parse Result ===", flush=True)
beats = parse_storyboard(text)
print(f"Beats parsed: {len(beats)}", flush=True)
if beats:
    for b in beats:
        print(f"  [{b.start_sec}-{b.end_sec}] ON SCREEN: {b.on_screen_text} | VO: {b.vo_text}", flush=True)
else:
    # Show what lines exist
    for line in text.split("\n"):
        if line.strip():
            print(f"  LINE: {line}", flush=True)
        # Check what fails
        m = re.match(r"\[(\d+(?:\.\d+)?)\s*s?\s*-\s*(\d+(?:\.\d+)?)\s*s?\s*\]", line.strip(), re.I)
        if m:
            print(f"  -> has bracket match: {m.groups()}", flush=True)
        else:
            print(f"  -> NO bracket match", flush=True)