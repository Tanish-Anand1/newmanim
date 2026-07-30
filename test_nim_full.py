"""Test NIM provider identity and API call only (no pipeline import)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# === 1. Provider identity ===
print("=== 1. Provider Identity ===", flush=True)
from app.llm_provider import NvidiaNimProvider

nim = NvidiaNimProvider()
assert nim.name == "nvidia_nim", f"Expected nvidia_nim, got {nim.name}"
print(f"  name: {nim.name} [OK]", flush=True)
print(f"  model: {nim.model} [OK]", flush=True)

# === 2. NIM actually works ===
print("\n=== 2. NIM Chat Completion ===", flush=True)
resp = nim.generate(
    system="Reply with exactly one word.",
    user_message="Say OK",
    max_tokens=20,
)
assert resp.provider_name == "nvidia_nim", f"Expected nvidia_nim, got {resp.provider_name}"
assert resp.text.strip() == "OK", f"Expected 'OK', got {resp.text!r}"
print(f"  provider: {resp.provider_name} [OK]", flush=True)
print(f"  model: {resp.model} [OK]", flush=True)
print(f"  text: {resp.text!r} [OK]", flush=True)
print(f"  tokens: {resp.input_tokens} in / {resp.output_tokens} out [OK]", flush=True)

# === 3. Storyboard generation via NIM ===
print("\n=== 3. Storyboard Generation via NIM ===", flush=True)

# Simple prompt to test if NIM can generate a storyboard
import time
start = time.monotonic()
system = """You are a storyboard writer for a math education video.
Generate a storyboard with time-stamped beats.
Format: [start-end] ON SCREEN: visual | VO: narration"""
user = "Topic: Derivative of x^2. Duration: 30 seconds. Audience: high school."

resp2 = nim.generate(system=system, user_message=user, max_tokens=2000)
elapsed = time.monotonic() - start

print(f"  elapsed: {elapsed:.1f}s [OK]", flush=True)
print(f"  output length: {len(resp2.text)} chars [OK]", flush=True)
# Show first and last beat
lines = [l.strip() for l in resp2.text.split('\n') if l.strip()]
for line in lines[:3]:
    print(f"  {line}", flush=True)
print(f"  ...", flush=True)
for line in lines[-2:]:
    print(f"  {line}", flush=True)

print("\n== ALL CHECKS PASSED ==", flush=True)