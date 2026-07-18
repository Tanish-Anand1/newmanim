# Vivacity Video Platform

FastAPI service for turning a structured storyboard or topic request into a Manim video through an async job API.

The backend keeps HTTP requests short: `POST /api/generate` creates a persisted job and returns immediately. Local development can execute jobs in-process; production uses Redis-backed RQ workers. The frontend can read status through `GET /api/jobs/{job_id}` or subscribe to `GET /api/jobs/{job_id}/stream` with Server-Sent Events.

A Next.js UI lives in `frontend/`. It accepts topic inputs, submits them for async rendering, and exposes beat-level edit requests after completion.

## Setup

```powershell
cd C:\PROJECTS\newmanim
.\manim-env\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set:

```text
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key
GOOGLE_API_KEY=your-key
LLM_PROVIDER=anthropic
LLM_PROVIDER_FAILOVER=1
LLM_PROVIDER_FALLBACKS=anthropic,openai,gemini
ADMIN_TOKEN=your-internal-debug-token
```

Only one provider key is required. When multiple keys are configured, quota and service failures move to the next provider without consuming a render retry. If all providers are unavailable, topic requests can use the local conservative storyboard builder when `ALLOW_LOCAL_STORYBOARD_FALLBACK=1`; direct storyboard requests are unaffected.

`CHEAP_LLM_PROVIDER=gemini` is used for a job's first generation attempt. `LLM_PROVIDER` is the paid escalation provider for later attempts. When a retry identifies one broken beat, it requests only that beat block rather than a full scene rewrite. The default template profile uses `TEMPLATE_PLANNER=heuristic`, so it does not need a second LLM call after storyboard drafting.

Optional Supabase storage is used only when `SUPABASE_URL`, a Supabase key, and `SUPABASE_BUCKET` are all present. Otherwise final videos are copied into `outputs/` and served from `/outputs/...`.

SQLite is the default:

```text
DATABASE_URL=sqlite:///./vivacity.db
```

Later, swapping to Postgres is a single config change by replacing `DATABASE_URL` with a Postgres SQLAlchemy URL.

## Run Locally

```powershell
.\start_dev.ps1
```

Open the API docs at:

```text
http://127.0.0.1:8000/docs
```

`start_dev.ps1` writes job runs outside the project tree by default, under `../vivacity_job_runs`, so generated scene files do not trigger dev-server reloads during a render. Set `VIVACITY_PORT=8001` before running the script if port 8000 is already occupied.

The default local mode is `JOB_EXECUTION_MODE=inline`. To exercise the production queue locally, run Redis, set `JOB_EXECUTION_MODE=rq`, run the API, and start one or more workers in separate terminals:

```powershell
.\start_worker.ps1
```

Use Postgres with multiple RQ workers for concurrent production traffic. SQLite is only appropriate for local development.

Run the frontend in another terminal:

```powershell
cd C:\PROJECTS\newmanim\frontend
copy .env.example .env.local
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

Dataset collection and merge utilities live in `tools/`; their generated JSONL assets live in `data/`.

## API

### POST `/api/storyboard/draft`

Request:

```json
{
  "topic": "Taylor series",
  "duration_seconds": 60,
  "audience": "JEE aspirants"
}
```

Response:

```json
{
  "storyboard": "# Approach: ...\n[0-4] ON SCREEN: ... | VO: \"...\"",
  "estimated_cost_usd": 0.01,
  "cost_breakdown": {}
}
```

This endpoint only drafts storyboard text for API inspection. It does not create a Job and does not render video.

### POST `/api/generate/batch`

Accepts up to `BATCH_MAX_ITEMS` generation requests and persists them as one short API operation. Use worker execution for batches larger than `INLINE_BATCH_MAX_ITEMS`.

Send a stable `Idempotency-Key` header to single-job `POST /api/generate` requests. Exact repeated requests also use a versioned content fingerprint when `reuse_existing` is enabled, preventing duplicate provider and render charges.

### POST `/api/generate`

Direct storyboard request:

```json
{
  "scene_name": "ConicsScene",
  "orientation": "portrait",
  "storyboard": "TITLE: ...\nTARGET LENGTH: 60\n\n[0-4] ON SCREEN: ... | VO: \"...\""
}
```

Topic request:

```json
{
  "topic": "Taylor series expansion of sin(x)",
  "duration_seconds": 60,
  "audience": "JEE aspirants",
  "scene_name": "TaylorSeriesScene",
  "orientation": "portrait"
}
```

Response:

```json
{
  "job_id": "uuid"
}
```

The endpoint requires a structured storyboard with beat lines in this form:

```text
[start_sec-end_sec] ON SCREEN: viewer-facing action | VO: "voiceover line"
```

Silent beats must use:

```text
VO: (silent)
```

The endpoint rejects empty storyboards, unedited template placeholders, invalid scene class names, overlapping beat ranges, and storyboards with an implied duration above 180 seconds.

`orientation` may be `portrait` or `landscape`. The API render path always passes Manim `--resolution` explicitly: `1080,1920` for portrait and `1920,1080` for landscape.

For topic requests, the backend drafts the storyboard inside the background job and immediately renders from it. Auto-approving removes the checkpoint that catches wrong math or wrong pedagogy before rendering. The generated storyboard is stored as `generated_storyboard` on the Job so it can be audited later through the API. Topic-based requests use `TOPIC_MAX_TARGET_SECONDS`, default `240`, so derivations can use more beats than short direct-storyboard jobs.

### GET `/api/jobs/{job_id}`

Returns the public job state used by the frontend. It does not include generated storyboard text, raw code, raw tracebacks, or model feedback.

```json
{
  "id": "uuid",
  "status": "rendering",
  "progress_message": "Rendering video (attempt 1 of 4).",
  "output_video_url": null,
  "orientation": "portrait",
  "duration_seconds": 60,
  "estimated_cost_usd": 0.12,
  "parent_job_id": null,
  "edited_beat_number": null,
  "beats": []
}
```

### GET `/api/internal/jobs/{job_id}`

Returns the internal debug payload, including `generated_storyboard`, raw scene code when present, full error details, and full cost breakdown. This endpoint requires:

```http
x-admin-token: your-internal-debug-token
```

The internal payload includes the pipeline version, captured provider/model configuration, persisted scene code, full cost breakdown by model, worker lease state, render seconds, and compute-cost estimate.

### GET `/api/internal/operations/summary`

Requires `x-admin-token`. Returns queue depth, active workers, 24-hour completion/failure counts, first-attempt success rate, rolling average cost for the latest 100 completed jobs, average and p95 cost, average and p95 wall time, projected daily spend, and the concurrent-worker count implied by `TARGET_VIDEOS_PER_DAY`.

### GET `/api/internal/dead-letter`

Requires `x-admin-token`. Returns jobs whose pipeline exhausted its retry budget or whose queue worker encountered an unhandled exception.

Health probes:

```text
GET /health/live
GET /health/ready
```

### GET `/api/jobs/{job_id}/stream`

Server-Sent Events stream. It emits a `job` event when the job row changes and closes after `complete` or `failed`.

Frontend fallback: poll `GET /api/jobs/{job_id}` every 3 seconds when SSE is unavailable.

### GET `/api/jobs/{job_id}/beats`

Returns beat metadata and one thumbnail per beat for completed jobs:

```json
[
  {
    "beat_number": 1,
    "start": 0,
    "end": 4,
    "on_screen": "...",
    "vo_text": "...",
    "thumbnail_url": "/outputs/job_beat_01.png"
  }
]
```

### POST `/api/jobs/{job_id}/beats/{beat_number}/regenerate`

Request:

```json
{
  "on_screen": "Edited visual description",
  "vo_text": "Edited voiceover line"
}
```

This creates a new Job linked to the original via `parent_job_id`. The backend patches only the selected beat section in the previous Manim code, re-renders the full scene, checks sampled frames, and muxes the updated beat audio.

### GET `/api/jobs/{job_id}/beats/{beat_number}/params`

Returns numeric beat tuning parameters extracted from the generated code:

```json
{
  "scale": 1.0,
  "gap": 2.3,
  "speed": 1.0
}
```

### PATCH `/api/jobs/{job_id}/beats/{beat_number}/params`

Request:

```json
{
  "scale": 1.1,
  "gap": 2.0,
  "speed": 0.8
}
```

This creates a render-only child Job. The backend replaces only the matching `beatN_scale`, `beatN_gap`, and `beatN_speed` numeric assignments in the stored Manim code, re-renders the full scene, checks sampled frames for visible boundary overflow, and muxes audio. It does not call Claude and records the edit in the `render_only` cost bucket.

## Job Lifecycle

Statuses:

```text
queued
generating_voiceover
generating_code
rendering
retrying
muxing
complete
failed
```

Pipeline:

1. Parse the storyboard into beats: start time, end time, on-screen action, and voiceover text.
2. Generate one OpenAI TTS audio clip per voiced beat. Silent beats become generated silence.
3. Measure each beat clip and build a per-beat timing table for the selected provider.
4. Use the selected pipeline profile to build the scene. `template` asks a low-cost model for constrained JSON and compiles it through deterministic Manim templates. `legacy` requests open-ended Manim code and retains the deeper repair loop.
5. Render with an explicit per-job resolution selected from the requested orientation.
6. If render fails, send the traceback and previous code back into the retry loop.
7. Compare rendered duration against the summed beat timing targets. Large drift fails the attempt.
8. Check for text/equation lifecycle defects such as adding replacement text without transforming or removing prior mobjects.
9. On configured spot-check/manual runs, extract sampled frames and run the vision-based quality check across accuracy, depth, logical flow, visual relevance, and element layout.
10. Fail and retry when a paid quality check runs and accuracy or element layout scores fall below the configured threshold.
11. Apply a mild residual audio timing correction, mux audio and video, upload or copy the final mp4, and mark the job complete.

Render failures, timing drift failures, quality-check failures, and text lifecycle failures all count against the same retry budget.

## Production Throughput Path

The cost/throughput path is `pipeline_profile=template`. It avoids full-file model-generated Python on normal jobs, limits render attempts, caches identical TTS clips by content hash, persists generated code in the database, and reuses completed videos by a versioned request fingerprint. The `legacy` profile remains available for experiments and difficult custom scenes, but it is not the default path for high-volume generation.

For a local production-shaped deployment:

```powershell
copy .env.production.example .env.production
# Fill keys, POSTGRES_PASSWORD, ADMIN_TOKEN, and the real render-worker hourly cost.
docker compose --env-file .env.production -f compose.production.yml up -d --build --scale worker=30
```

SQLite is for local development. Multi-worker deployments must use Postgres and Redis. RQ workers consume the Redis queue; failed terminal jobs are retained in the database dead-letter view for review.

The default capacity-planning baseline is 180 seconds per job at 70% worker utilization. That implies 30 concurrent workers for 10,000 jobs/day. This is a planning value, not measured capacity. After representative jobs complete, use `/api/internal/operations/summary`; it replaces the fallback with observed p95 wall time and reports the required worker count.

Set these production controls explicitly:

```text
DEFAULT_PIPELINE_PROFILE=template
JOB_EXECUTION_MODE=rq
REDIS_URL=redis://redis:6379/0
COST_BUDGET_MODE=enforce
MAX_ESTIMATED_COST_USD_PER_VIDEO=0.15
JOB_COST_CEILING_USD=0.50
RENDER_COMPUTE_USD_PER_HOUR=<effective worker price>
TARGET_VIDEOS_PER_DAY=10000
```

The service records provider, TTS, and render compute cost after each call/stage. The current defaults use model-specific rates rather than one blended provider rate. Pricing defaults were checked on 2026-07-10 against the official [Anthropic model pricing](https://www.anthropic.com/pricing), [OpenAI model catalog](https://developers.openai.com/api/docs/models), [OpenAI TTS-1 page](https://developers.openai.com/api/docs/models/tts-1), and [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). Re-check and override the rate environment variables before a production launch because provider pricing changes over time.

Run `python tools/load_test.py --count 50 --concurrency 8`, then repeat at `--count 200` and `--count 1000` against Postgres, Redis, and multiple RQ workers. The report includes p50/p95 time-to-complete, completion cost, failed jobs, and queue-depth samples when `ADMIN_TOKEN` is available.

The target is only considered demonstrated after a representative load test shows required daily throughput, acceptable first-attempt success, and rolling average cost at or below the target. If the cheap first-attempt provider causes enough escalations to reduce quality or increase paid retries, the measured report must take precedence over the target assumption.

`VISION_QUALITY_CHECK_MODE=sample` with `VISION_QUALITY_SAMPLE_RATE=0.10` runs the heavier vision check on a deterministic 10% sample of jobs. Use `VISION_QUALITY_CHECK_MODE=manual` to disable automatic paid checks, or `always` for local debugging. `VISION_LABEL_COLLISION_MAX_FRAMES` caps sampled frames per validation pass. These calls are added to the configured LLM provider's cost totals.

## Learning Memory

The pipeline can accumulate reviewable external memory without changing model weights or mutating the live prompt automatically.

- Successful beat sections that pass quality checks are staged in `learning_memory/staged_reference_examples.jsonl`.
- Retry fixes that later pass validation are staged in `learning_memory/staged_failure_patterns.jsonl`.
- Approved examples and failure reminders must be manually copied into `learning_memory/approved_reference_examples.jsonl` or `learning_memory/approved_failure_patterns.jsonl` before codegen can use them.
- Per-category outcomes are appended to `learning_memory/category_success_events.jsonl`.
- Internal summary: `GET /api/internal/learning/summary` with `x-admin-token`.

This keeps weekly or ad hoc review lightweight while avoiding fully automatic prompt changes.

## Sync Limitation

Each beat's voiceover clip duration is used as an explicit timing target for that beat's animation, with automated overflow and drift checks before a job is marked complete.

This is a stronger guarantee than the original global audio stretch, but it is still bounded by the LLM's ability to hit timing targets and Manim's animation timing model. It is not frame-level lip-sync.

## Notes

- `/api/storyboard/draft` returns storyboard text for API inspection and never submits directly to rendering.
- Topic-based `/api/generate` requests auto-generate a storyboard and immediately render it; the storyboard is stored on the Job for audit.
- `ffmpeg`, `ffprobe`, and `manim` must be available on `PATH` for the active environment.
