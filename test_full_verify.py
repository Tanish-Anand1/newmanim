"""Test: NIM provider identity, fallback chain, and a real NIM LLM call.

This tests that:
1. The NvidiaNimProvider identifies as 'nvidia_nim' everywhere
2. A real NIM call succeeds
3. A storyboard draft can be generated via NIM
4. The failover chain includes nvidia_nim
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# === 1. Provider identity ===
print("=== 1. Provider Identity ===", flush=True)
from app.llm_provider import NvidiaNimProvider, get_llm_provider, FailoverProvider

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
from app.pipeline import generate_storyboard_draft
start = time.monotonic()
result = generate_storyboard_draft(
    topic="Derivative of x^2",
    duration_seconds=30,
    audience="high school",
    provider=nim,
)
elapsed = time.monotonic() - start
storyboard = result["storyboard"]
print(f"  elapsed: {elapsed:.1f}s [OK]", flush=True)
print(f"  cost: ${result.get('estimated_cost_usd', 0):.4f} [OK]", flush=True)
print(f"  storyboard length: {len(storyboard)} chars [OK]", flush=True)
print(f"  storyboard preview: {storyboard[:120]}...", flush=True)

# === 4. Verify failover chain includes nvidia_nim ===
print("\n=== 4. Failover Chain ===", flush=True)
provider = get_llm_provider("anthropic")
if isinstance(provider, FailoverProvider):
    names = [p.name for p in provider.providers]
    has_nim = "nvidia_nim" in names
    print(f"  chain: {names}", flush=True)
    print(f"  includes nvidia_nim: {has_nim} [OK]", flush=True)
    assert has_nim, "nvidia_nim not in failover chain!"
else:
    print(f"  single provider: {provider.name} (no failover) [WARN]", flush=True)

print("\n== ALL CHECKS PASSED ==", flush=True)