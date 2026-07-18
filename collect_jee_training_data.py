"""
Phase 1 data collection: extract topics from the JEE/NEET benchmark dataset,
then run each topic through your existing pipeline (Claude/OpenAI) to
generate real (storyboard, verified-code) training pairs for fine-tuning.

USAGE:
    python collect_jee_training_data.py
"""

import requests
import json
import time
import io
import base64
from pathlib import Path
from datasets import load_dataset
from google import genai
from google.genai import types

def encode_image_to_base64(pil_image):
    """Convert a PIL Image to base64-encoded PNG bytes for the Anthropic API."""
    buffer = io.BytesIO()
    # Ensure RGB mode - some exam scan images may be grayscale/palette mode,
    # which can cause encoding issues
    if pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

import os

OUTPUT_FILE = Path("jee_training_pairs.jsonl")
BASE_URL = "http://127.0.0.1:8000"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

if not ADMIN_TOKEN:
    print("ERROR: set ADMIN_TOKEN environment variable before running this script.")
    print('  $env:ADMIN_TOKEN = "your-actual-admin-token"')
    exit(1)

# ------------------------------------------------------------------
# Step 1: Load benchmark, extract underlying concept per question
# ------------------------------------------------------------------
def extract_topics_from_benchmark(max_questions=100):
    """
    Pull questions from the JEE/NEET benchmark, use a vision-capable model
    to identify the underlying physics/math concept per question, dedupe
    into a clean topic list. max_questions caps cost during a first pass -
    raise it once this is confirmed working.
    """
    ds = load_dataset("Reja1/jee-neet-benchmark", split="test")
    print(f"Dataset loaded: {len(ds)} rows. Fields: {list(ds[0].keys())}")
    print(">>> VERIFY the 'image' and 'subject' field names below actually match the above <<<")
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    topics = set()
    for i, row in enumerate(ds):
        if i >= max_questions:
            break
        # Adjust field name based on actual dataset schema - check
        # ds[0] structure first, this assumes an 'image' field
        image = row.get("image")
        subject = row.get("subject", "")

        if image is None:
            continue

        try:
            image_b64 = encode_image_to_base64(image)
        except Exception as e:
            print(f"  Skipping row {i}, image encoding failed: {e}")
            continue

        # Ask the model to name ONE concise topic, not solve the question
        resp = client.models.generate_content(
            model=gemini_model,
            contents=[
                (
                    "Name the single underlying physics/math concept this exam "
                    "question tests, in 3-6 words, suitable as a video topic "
                    "(e.g. 'Projectile motion range formula', 'Bohr model energy levels'). "
                    "Just the topic, nothing else."
                ),
                types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(max_output_tokens=50),
        )
        topic = resp.text.strip()
        topics.add((subject, topic))
        print(f"[{i}] {subject}: {topic}")
        time.sleep(0.5)  # basic rate-limit courtesy

    return list(topics)


# ------------------------------------------------------------------
# Step 2: Run each topic through your existing pipeline, save clean results
# ------------------------------------------------------------------
def load_already_collected_topics():
    """Check which topics already succeeded in a prior run, so reruns skip them."""
    if not OUTPUT_FILE.exists():
        return set()
    done = set()
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            done.add(row["topic"])
    return done


def collect_pairs_from_topics(topics, delay_seconds=15):
    already_done = load_already_collected_topics()
    if already_done:
        print(f"Skipping {len(already_done)} topics already collected in a prior run")

    pairs_collected = 0
    consecutive_failures = 0
    last_error_snippet = None
    MAX_CONSECUTIVE_FAILURES = 3

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for subject, topic in topics:
            if topic in already_done:
                continue

            print(f"Generating: {topic} ({subject})")
            resp = requests.post(
                f"{BASE_URL}/api/generate",
                json={
                    "topic": topic,
                    "audience": "JEE/NEET aspirants",
                    "duration_seconds": 60,
                    "orientation": "portrait",
                    "scene_name": "".join(c for c in topic.title() if c.isalnum())[:40],
                },
            )
            if resp.status_code != 200:
                print(f"  Request failed: {resp.status_code}")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n{MAX_CONSECUTIVE_FAILURES} consecutive request failures - "
                          "stopping early. Check server/API status before rerunning.")
                    break
                continue

            job_id = resp.json()["job_id"]

            # Poll until done - reuse your existing polling pattern
            job = None
            while True:
                job_resp = requests.get(
                    f"{BASE_URL}/api/internal/jobs/{job_id}",
                    headers={"x-admin-token": ADMIN_TOKEN},
                )
                if job_resp.status_code != 200:
                    print(f"  Job lookup failed: HTTP {job_resp.status_code} - {job_resp.text[:200]}")
                    print("  Check ADMIN_TOKEN is correct. Skipping this topic.")
                    break
                job = job_resp.json()
                if job["status"] in ("complete", "failed"):
                    break
                time.sleep(3)

            if job is None:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n{MAX_CONSECUTIVE_FAILURES} consecutive failures - stopping early.")
                    break
                continue

            if job["status"] == "complete":
                pair = {
                    "topic": topic,
                    "subject": subject,
                    "storyboard": job["generated_storyboard"],
                    "code": job["raw_code"],
                    "attempt_number": job["attempt_number"],
                }
                out.write(json.dumps(pair) + "\n")
                pairs_collected += 1
                print(f"  SUCCESS - saved (attempt {job['attempt_number']}/4)")
                consecutive_failures = 0  # reset on any real success
            else:
                error_snippet = job.get("error", "")[:100]
                print(f"  FAILED - not saved: {error_snippet}")

                # Circuit breaker: if the SAME error repeats consecutively,
                # it's very likely a persistent problem (exhausted billing
                # quota, service outage), not transient - stop instead of
                # burning through every remaining topic on a guaranteed
                # repeat failure, which is what happened last run (90+
                # identical 429 quota errors in a row).
                if error_snippet == last_error_snippet:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                last_error_snippet = error_snippet

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\nSame error repeated {MAX_CONSECUTIVE_FAILURES}x in a row - "
                          "this looks persistent (exhausted billing quota, outage, etc.), "
                          "not transient. Stopping early. Fix the underlying issue, then "
                          "rerun - already-collected pairs are safe and won't be redone.")
                    break

    print(f"\nTotal pairs collected: {pairs_collected}")
    return pairs_collected


if __name__ == "__main__":
    print("--- Extracting topics from benchmark ---")
    topics = extract_topics_from_benchmark(max_questions=100)
    print(f"\nExtracted {len(topics)} unique topics")

    print("\n--- Generating training pairs (this will cost real API money) ---")
    print("Each topic runs through your full pipeline - review cost_breakdown")
    print("per job if you want to estimate total spend before running all topics.")
    collect_pairs_from_topics(topics)
