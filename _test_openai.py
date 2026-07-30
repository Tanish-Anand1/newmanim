"""Quick test: does the OpenAI key work?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from app.llm_provider import OpenAIProvider

print("=== OpenAI Connection Test ===", flush=True)
p = OpenAIProvider()
print(f"Model: {p.model}", flush=True)
print(f"Fast model: {p.fast_model}", flush=True)

r = p.generate("Say only: OK-OPENAI", "Respond", 50)
print(f"OK: {r.text}", flush=True)
print(f"Provider: {r.provider_name}", flush=True)
print(f"Model: {r.model}", flush=True)