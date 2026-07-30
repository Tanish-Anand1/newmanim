"""List available NIM models and test a few for speed."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Manually load .env
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("NVIDIA_NIM_API_KEY"),
    base_url="https://integrate.api.nvidia.com/v1",
)

# List models
print("=== Available NIM Models ===", flush=True)
models = client.models.list().data
print(f"Total: {len(models)} models", flush=True)

# Show interesting candidates (under 10B)
interesting = []
for m in models:
    mid = m.id
    if any(needle in mid.lower() for needle in ["llama-3", "mistral", "mixtral", "qwen", "nemotron", "phi", "gemma"]):
        if not any(excl in mid.lower() for excl in ["nemo", "rlhf", "dpo", "sft", "405b", "70b", "90b", "120b"]):
            interesting.append(mid)

interesting.sort()
for m in interesting:
    print(f"  {m}", flush=True)

print(flush=True)
print("=== Testing a few fast models ===", flush=True)

test_models = [
    "meta/llama-3.2-3b-instruct",     # 3B, fast
    "mistralai/mistral-7b-instruct-v0.3",  # 7B
    "meta/llama-3.1-8b-instruct",      # 8B Llama
    "nvidia/llama-3.1-nemotron-nano-8b-v1",  # 8B Nemotron
]

for model_id in test_models:
    print(f"\n--- {model_id} ---", flush=True)
    try:
        start = time.monotonic()
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Reply with exactly: MODEL_OK"}],
            max_tokens=20,
            temperature=0.1,
        )
        elapsed = time.monotonic() - start
        text = resp.choices[0].message.content.strip()
        print(f"  Time: {elapsed:.1f}s", flush=True)
        print(f"  Response: {text}", flush=True)
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"  Time: {elapsed:.1f}s", flush=True)
        print(f"  ERROR: {type(e).__name__}: {e}", flush=True)