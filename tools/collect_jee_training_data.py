"""
Batch collector for JEE/NEET benchmark topics and Vivacity jobs.

Default behavior keeps the earlier 100-question workflow:
1. Extract up to N topic labels from the benchmark images.
2. Submit each topic to the async rendering API.
3. Wait for completion, then append successful pairs to a JSONL file.

The script is intentionally configurable so the same path can be used for
larger production runs:
- `JEE_MAX_QUESTIONS` / `--limit` controls how many benchmark rows are sampled.
- `JEE_WORKERS` / `--workers` controls concurrent job submissions.
- `BATCH_REQUEST_DELAY_SECONDS` / `--delay` adds throttling between topic
  extraction requests and between sequential submissions when workers=1.
- `CLEANUP_JOB_ARTIFACTS=1` removes finished job outputs after they are saved.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import requests
from datasets import load_dataset
from dotenv import load_dotenv

from app.llm_provider import get_llm_provider


load_dotenv(dotenv_path=PROJECT_DIR / ".env")

OUTPUT_DIR = PROJECT_DIR / "outputs"
WORK_ROOT = Path(os.environ.get("VIVACITY_WORK_ROOT", str(PROJECT_DIR.parent / "vivacity_job_runs"))).resolve()
OUTPUT_FILE = Path(os.environ.get("JEE_OUTPUT_FILE", str(PROJECT_DIR / "data" / "jee_training_pairs.jsonl")))
BASE_URL = os.environ.get("VIVACITY_API_BASE_URL", "http://127.0.0.1:8001")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

DEFAULT_LIMIT = int(os.environ.get("JEE_MAX_QUESTIONS", "100"))
DEFAULT_WORKERS = max(1, int(os.environ.get("JEE_WORKERS", "1")))
DEFAULT_DELAY_SECONDS = float(os.environ.get("BATCH_REQUEST_DELAY_SECONDS", "3"))
DEFAULT_POLL_INTERVAL_SECONDS = float(os.environ.get("JEE_POLL_INTERVAL_SECONDS", "3"))
DEFAULT_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("JEE_REQUEST_TIMEOUT_SECONDS", "60"))
DEFAULT_SUBMIT_RETRIES = int(os.environ.get("JEE_SUBMIT_RETRIES", "3"))
MAX_CONSECUTIVE_QUOTA_ERRORS = int(os.environ.get("JEE_MAX_CONSECUTIVE_QUOTA_ERRORS", "3"))
MAX_QUESTIONS = DEFAULT_LIMIT
CLEANUP_JOB_ARTIFACTS = os.environ.get("CLEANUP_JOB_ARTIFACTS", "1").strip().lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class CollectorConfig:
    limit: int
    workers: int
    delay_seconds: float
    poll_interval_seconds: float
    request_timeout_seconds: float
    submit_retries: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect JEE/NEET training pairs from the benchmark dataset.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum benchmark rows to inspect.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent jobs to run.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay in seconds between topic extraction requests.")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS, help="Polling interval for job status.")
    parser.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS, help="HTTP timeout for API calls.")
    parser.add_argument("--submit-retries", type=int, default=DEFAULT_SUBMIT_RETRIES, help="Retries for transient job submission failures.")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> CollectorConfig:
    return CollectorConfig(
        limit=max(1, args.limit),
        workers=max(1, args.workers),
        delay_seconds=max(0.0, args.delay),
        poll_interval_seconds=max(0.5, args.poll_interval),
        request_timeout_seconds=max(5.0, args.request_timeout),
        submit_retries=max(1, args.submit_retries),
    )


def is_provider_quota_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "usage limits" in lowered
        or "current quota" in lowered
        or "insufficient_quota" in lowered
        or "rate limit" in lowered
        or "429 too many requests" in lowered
        or "resource_exhausted" in lowered
        or "resource exhausted" in lowered
    )


def parse_retry_after(header_value: str | None, default_seconds: int = 30) -> int:
    if not header_value:
        return default_seconds
    try:
        return max(1, int(float(header_value)))
    except ValueError:
        return default_seconds


def safe_scene_name(topic: str) -> str:
    return "".join(ch for ch in topic.title() if ch.isalnum())[:40] or "TopicScene"


def load_existing_topics() -> set[str]:
    topics: set[str] = set()
    if not OUTPUT_FILE.exists():
        return topics
    with OUTPUT_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            topic = record.get("topic")
            if topic:
                topics.add(topic)
    return topics


def cleanup_job_artifacts(job: dict) -> None:
    job_id = job.get("id")
    if not job_id:
        return
    output_url = job.get("output_video_url")
    if isinstance(output_url, str) and output_url.startswith("/outputs/"):
        output_path = OUTPUT_DIR / output_url.removeprefix("/outputs/")
        if output_path.exists():
            output_path.unlink()
    work_dir = WORK_ROOT / job_id
    if work_dir.exists() and work_dir.is_dir():
        shutil.rmtree(work_dir, ignore_errors=True)


def extract_topics_from_benchmark(config: CollectorConfig, stop_event: threading.Event) -> list[tuple[str, str]]:
    """
    Pull benchmark questions, infer the underlying topic, and dedupe the list.
    The default limit stays at 100 so the behavior matches the earlier script.
    """
    ds = load_dataset("Reja1/jee-neet-benchmark", split="test")
    print(f"Dataset loaded: {len(ds)} rows. Fields: {list(ds[0].keys())}")
    print(">>> VERIFY the 'image' and 'subject' field names below actually match the above <<<")
    provider = get_llm_provider()

    topics: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    consecutive_quota_errors = 0

    for i, row in enumerate(ds):
        if stop_event.is_set():
            break
        if i >= config.limit:
            break

        image = row.get("image")
        subject = row.get("subject", "")
        if image is None:
            continue

        fd, temp_name = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        frame_path = Path(temp_name)
        try:
            image.save(frame_path, format="PNG")
            prompt = (
                "Name the single underlying physics/math concept this exam "
                "question tests, in 3-6 words, suitable as a video topic "
                "(e.g. 'Projectile motion range formula', 'Bohr model energy levels'). "
                "Just the topic, nothing else."
            )
            resp = provider.inspect_image(frame_path=frame_path, prompt=prompt, max_tokens=50)
        except Exception as exc:
            message = str(exc)
            print(f"  Topic extraction failed at row {i}: {message[:200]}")
            if is_provider_quota_error(message):
                consecutive_quota_errors += 1
                if consecutive_quota_errors >= MAX_CONSECUTIVE_QUOTA_ERRORS:
                    print("  STOPPING - repeated provider quota/rate-limit failures during topic extraction.")
                    break
            else:
                consecutive_quota_errors = 0
            continue
        finally:
            frame_path.unlink(missing_ok=True)

        topic = resp.text.strip()
        if not topic:
            print(f"  Topic extraction returned no text at row {i}; skipping.")
            consecutive_quota_errors = 0
            continue

        pair = (subject, topic)
        if pair in seen:
            continue
        seen.add(pair)
        topics.append(pair)
        consecutive_quota_errors = 0
        print(f"[{i}] {subject}: {topic}")
        if config.delay_seconds > 0:
            time.sleep(config.delay_seconds)

    return topics


def submit_job(topic: str, subject: str, config: CollectorConfig, stop_event: threading.Event) -> tuple[str | None, str | None]:
    payload = {
        "topic": topic,
        "audience": "JEE/NEET aspirants",
        "duration_seconds": 60,
        "orientation": "portrait",
        "scene_name": safe_scene_name(topic),
    }
    retries = 0
    backoff_seconds = 5.0

    while retries < config.submit_retries and not stop_event.is_set():
        try:
            resp = requests.post(f"{BASE_URL}/api/generate", json=payload, timeout=config.request_timeout_seconds)
        except requests.RequestException as exc:
            retries += 1
            if retries >= config.submit_retries:
                return None, f"Request failed: {exc}"
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 60.0)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()["job_id"], None
            except Exception as exc:
                return None, f"Invalid generate response: {exc}"

        if resp.status_code == 429:
            retries += 1
            sleep_for = parse_retry_after(resp.headers.get("Retry-After"))
            print(f"  Rate-limited submitting {topic} ({subject}); retrying in {sleep_for}s.")
            time.sleep(sleep_for)
            continue

        return None, f"Request failed: {resp.status_code} {resp.text[:200]}"

    return None, "Submit retries exhausted."


def poll_job(job_id: str, config: CollectorConfig, stop_event: threading.Event) -> tuple[dict | None, str | None]:
    while not stop_event.is_set():
        try:
            job_resp = requests.get(
                f"{BASE_URL}/api/internal/jobs/{job_id}",
                headers={"x-admin-token": ADMIN_TOKEN},
                timeout=config.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            print(f"  Job lookup failed for {job_id}: {exc}")
            time.sleep(config.poll_interval_seconds)
            continue

        if job_resp.status_code == 429:
            sleep_for = parse_retry_after(job_resp.headers.get("Retry-After"))
            print(f"  Poll rate-limited for {job_id}; sleeping {sleep_for}s.")
            time.sleep(sleep_for)
            continue

        if job_resp.status_code != 200:
            return None, f"Job lookup failed: HTTP {job_resp.status_code} - {job_resp.text[:200]}"

        job = job_resp.json()
        if job["status"] in ("complete", "failed"):
            return job, None
        time.sleep(config.poll_interval_seconds)

    return None, "Stopped."


def process_topic(pair: tuple[str, str], config: CollectorConfig, stop_event: threading.Event) -> dict:
    subject, topic = pair
    if stop_event.is_set():
        return {"status": "skipped", "topic": topic, "subject": subject, "reason": "batch stopped"}

    if config.delay_seconds > 0 and config.workers == 1:
        time.sleep(config.delay_seconds)

    job_id, error = submit_job(topic, subject, config, stop_event)
    if not job_id:
        return {"status": "failed", "topic": topic, "subject": subject, "reason": error or "submit failed"}

    job, error = poll_job(job_id, config, stop_event)
    if not job:
        return {"status": "failed", "topic": topic, "subject": subject, "reason": error or "poll failed"}

    if job["status"] == "complete":
        pair_record = {
            "topic": topic,
            "subject": subject,
            "storyboard": job["generated_storyboard"],
            "code": job["raw_code"],
            "attempt_number": job["attempt_number"],
        }
        return {
            "status": "success",
            "topic": topic,
            "subject": subject,
            "job": job,
            "record": pair_record,
        }

    error_text = job.get("error", "") or ""
    if is_provider_quota_error(error_text):
        return {
            "status": "quota",
            "topic": topic,
            "subject": subject,
            "job": job,
            "reason": error_text[:200],
        }
    return {
        "status": "failed",
        "topic": topic,
        "subject": subject,
        "job": job,
        "reason": error_text[:200] if error_text else "job failed",
    }


def collect_pairs_from_topics(topics: Iterable[tuple[str, str]], config: CollectorConfig) -> int:
    pairs_collected = 0
    already_collected = load_existing_topics()
    stop_event = threading.Event()
    file_lock = threading.Lock()
    consecutive_quota_errors = 0

    pending: list[cf.Future] = []
    with OUTPUT_FILE.open("a", encoding="utf-8") as out, cf.ThreadPoolExecutor(max_workers=config.workers) as executor:
        for subject, topic in topics:
            if topic in already_collected:
                print(f"Skipping already saved: {topic} ({subject})")
                continue
            future = executor.submit(process_topic, (subject, topic), config, stop_event)
            pending.append(future)

        for future in cf.as_completed(pending):
            try:
                result = future.result()
            except Exception as exc:
                print(f"  FAILED - worker crashed: {exc}")
                continue
            status = result.get("status")
            topic = result.get("topic", "")
            subject = result.get("subject", "")

            if status == "success":
                with file_lock:
                    out.write(json.dumps(result["record"], ensure_ascii=False) + "\n")
                    out.flush()
                pairs_collected += 1
                already_collected.add(topic)
                consecutive_quota_errors = 0
                job = result.get("job", {})
                print(f"  SUCCESS - saved (attempt {job.get('attempt_number', '?')}/4)")
                job_data = result.get("job")
                if job_data and CLEANUP_JOB_ARTIFACTS:
                    cleanup_job_artifacts(job_data)
                continue

            if status == "quota":
                consecutive_quota_errors += 1
                print(f"  FAILED - not saved: {result.get('reason', '')}")
                job_data = result.get("job")
                if job_data and CLEANUP_JOB_ARTIFACTS:
                    cleanup_job_artifacts(job_data)
                if consecutive_quota_errors >= MAX_CONSECUTIVE_QUOTA_ERRORS:
                    print("  STOPPING - repeated provider quota/rate-limit failures during generation.")
                    stop_event.set()
                    break
                continue

            consecutive_quota_errors = 0
            print(f"  FAILED - not saved: {result.get('reason', '')}")
            job_data = result.get("job")
            if job_data and CLEANUP_JOB_ARTIFACTS:
                cleanup_job_artifacts(job_data)

        if stop_event.is_set():
            for future in pending:
                future.cancel()

    print(f"\nTotal pairs collected: {pairs_collected}")
    return pairs_collected


def main() -> None:
    if not ADMIN_TOKEN:
        print("ERROR: set ADMIN_TOKEN environment variable before running this script.")
        print('  $env:ADMIN_TOKEN = "your-actual-admin-token"')
        raise SystemExit(1)

    args = parse_args()
    config = build_config(args)
    stop_event = threading.Event()

    print("--- Extracting topics from benchmark ---")
    topics = extract_topics_from_benchmark(config, stop_event)
    print(f"\nExtracted {len(topics)} unique topics")

    print("\n--- Generating training pairs (this will cost real API money) ---")
    print("Each topic runs through your full pipeline - review cost_breakdown")
    print("per job if you want to estimate total spend before running all topics.")
    print(f"Collector config: limit={config.limit}, workers={config.workers}, delay={config.delay_seconds}s")
    collect_pairs_from_topics(topics, config)


if __name__ == "__main__":
    main()
