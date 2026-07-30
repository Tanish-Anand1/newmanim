"""Quick test: check each provider individually."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm_provider import AnthropicProvider, GeminiProvider, NvidiaNimProvider

# 1. Anthropic
print("=== Anthropic (haiku-4-5) ===", flush=True)
try:
    p = AnthropicProvider()
    r = p.generate("Say just: OK-ANTHROPIC", "Respond", 50)
    print(f"OK: {r.text[:100]}", flush=True)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", flush=True)

print(flush=True)

# 2. Gemini
print("=== Gemini (gemini-2.5-flash) ===", flush=True)
try:
    p = GeminiProvider()
    r = p.generate("Say just: OK-GEMINI", "Respond", 50)
    print(f"OK: {r.text[:100]}", flush=True)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", flush=True)

print(flush=True)

# 3. NIM (with shorter timeout via a small model)
print("=== Nvidia NIM (small model for quick test) ===", flush=True)
import os
os.environ["NVIDIA_NIM_MODEL"] = "meta/llama-3.2-3b-instruct"  # fast, for connectivity test
try:
    p = NvidiaNimProvider()
    r = p.generate("Say just: OK-NIM", "Respond", 50)
    print(f"OK: {r.text[:100]}", flush=True)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", flush=True)