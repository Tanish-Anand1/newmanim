"""Exercise the queued Vivacity API and report completion/cost percentiles.

Examples:
    python tools/load_test.py --count 50 --concurrency 8
    python tools/load_test.py --count 200 --concurrency 24
    python tools/load_test.py --count 1000 --concurrency 80 --report data/load-1000.json

Run against Postgres + Redis + multiple RQ workers. This creates real jobs and
can call paid providers when the selected pipeline/profile requires them.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STORYBOARD = """# Approach: concise animated definition and example
[0-5] ON SCREEN: Graph axes and a curve appear while a tracer dot moves along the curve | VO: \"Observe the changing value.\"
[5-10] ON SCREEN: A vector arrow labeled F grows from the origin | VO: \"Now focus on the vector.\"
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load-test queued Vivacity video generation.")
    parser.add_argument("--base-url", default=os.getenv("VIVACITY_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--count", type=int, required=True, help="Number of real video jobs to submit.")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent submit/poll clients.")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--report", type=Path, default=None)
    return parser.parse_args()


def request_json(
    url: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, method=method, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def submit_one(base_url: str, index: int, timeout: float) -> tuple[str, float]:
    request_id = uuid.uuid4().hex[:10]
    payload = {
        "storyboard": DEFAULT_STORYBOARD,
        "scene_name": f"LoadScene{index}_{request_id}",
        "orientation": "portrait",
        "pipeline_profile": "template",
        "reuse_existing": False,
    }
    started = time.monotonic()
    response = request_json(f"{base_url}/api/generate", method="POST", payload=payload, timeout=timeout)
    return str(response["job_id"]), started


def wait_for_completion(base_url: str, job_id: str, started: float, poll_seconds: float, timeout: float) -> dict:
    while True:
        job = request_json(f"{base_url}/api/jobs/{job_id}", timeout=timeout)
        if job["status"] in {"complete", "failed"}:
            return {
                "job_id": job_id,
                "status": job["status"],
                "elapsed_seconds": time.monotonic() - started,
                "estimated_cost_usd": float(job.get("estimated_cost_usd") or 0.0),
                "failure_code": job.get("failure_code"),
            }
        time.sleep(poll_seconds)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) * fraction) + 0.999999) - 1))]


def sample_queue_depth(base_url: str, admin_token: str, stop_event: threading.Event, samples: list[dict]) -> None:
    headers = {"x-admin-token": admin_token}
    while not stop_event.is_set():
        try:
            summary = request_json(f"{base_url}/api/internal/operations/summary", timeout=10, headers=headers)
            queue = summary.get("queue", {})
            samples.append(
                {
                    "timestamp": time.time(),
                    "queued": queue.get("queued"),
                    "active": queue.get("active"),
                    "rq_queue_depth": queue.get("rq_queue_depth"),
                    "active_workers": queue.get("active_workers"),
                }
            )
        except (HTTPError, URLError, TimeoutError, ValueError):
            pass
        stop_event.wait(5.0)


def main() -> int:
    args = parse_args()
    if args.count < 1 or args.concurrency < 1:
        raise SystemExit("--count and --concurrency must be positive.")
    base_url = args.base_url.rstrip("/")
    started = time.monotonic()
    submitted: list[tuple[str, float]] = []
    submit_errors: list[str] = []
    queue_samples: list[dict] = []
    monitor_stop = threading.Event()
    admin_token = os.getenv("ADMIN_TOKEN")
    monitor = None
    if admin_token:
        monitor = threading.Thread(
            target=sample_queue_depth,
            args=(base_url, admin_token, monitor_stop, queue_samples),
            daemon=True,
        )
        monitor.start()

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(submit_one, base_url, index, args.request_timeout) for index in range(args.count)]
        for future in as_completed(futures):
            try:
                submitted.append(future.result())
            except (HTTPError, URLError, KeyError, TimeoutError) as exc:
                submit_errors.append(f"{type(exc).__name__}: {exc}")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(wait_for_completion, base_url, job_id, submitted_at, args.poll_seconds, args.request_timeout)
            for job_id, submitted_at in submitted
        ]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except (HTTPError, URLError, TimeoutError) as exc:
                results.append({"status": "poll_error", "error": f"{type(exc).__name__}: {exc}"})

    monitor_stop.set()
    if monitor is not None:
        monitor.join(timeout=6)

    completed = [result for result in results if result.get("status") == "complete"]
    failed = [result for result in results if result.get("status") != "complete"]
    elapsed = [float(result["elapsed_seconds"]) for result in completed]
    costs = [float(result["estimated_cost_usd"]) for result in completed]
    report = {
        "submitted": len(submitted),
        "submit_errors": submit_errors,
        "completed": len(completed),
        "failed": len(failed),
        "wall_seconds": round(time.monotonic() - started, 3),
        "p50_time_to_complete_seconds": percentile(elapsed, 0.50),
        "p95_time_to_complete_seconds": percentile(elapsed, 0.95),
        "average_cost_usd": (sum(costs) / len(costs)) if costs else None,
        "p95_cost_usd": percentile(costs, 0.95),
        "queue_depth_samples": queue_samples,
        "failures": failed,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if not failed and not submit_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
