"""Smoke test: verify NvidiaNimProvider succeeds with a real API call."""
import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure NIM env vars are set
os.environ["NVIDIA_NIM_API_KEY"] = "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"
os.environ["NVIDIA_NIM_BASE_URL"] = "https://integrate.api.nvidia.com/v1"

# Test models in order of preference
MODELS = [
    "meta/llama-3.2-3b-instruct",
    "nvidia/nemotron-mini-4b-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
]

success = False
for model in MODELS:
    os.environ["NVIDIA_NIM_MODEL"] = model
    print(f"\n--- Trying model: {model} ---", flush=True)
    try:
        from app.llm_provider import NvidiaNimProvider
        provider = NvidiaNimProvider()
        start = time.monotonic()
        resp = provider.generate(
            system="Reply with exactly one word.",
            user_message="Say OK",
            max_tokens=20,
        )
        elapsed = time.monotonic() - start
        print(f"ELAPSED:  {elapsed:.1f}s", flush=True)
        print(f"PROVIDER: {resp.provider_name}", flush=True)
        print(f"MODEL:    {resp.model}", flush=True)
        print(f"TEXT:     {resp.text!r}", flush=True)
        print(f"IN TOK:   {resp.input_tokens}", flush=True)
        print(f"OUT TOK:  {resp.output_tokens}", flush=True)
        print("STATUS:   SUCCESS", flush=True)
        success = True
        break
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}", flush=True)

if not success:
    print("\nAll NIM models failed.", flush=True)
    sys.exit(1)