import os
import sys
import uuid
import json
import re
import asyncio
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional

import anthropic
from openai import AsyncOpenAI
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import auth
import db
import storage

load_dotenv()

from prompts import (
    SCRIPT_SYSTEM_PROMPT_ENGLISH,
    SCRIPT_SYSTEM_PROMPT_HINGLISH,
    MANIM_PORTRAIT_PROMPT,
    MANIM_LANDSCAPE_PROMPT,
    VOICE_ENGLISH, VOICE_HINGLISH,
    VOICE_INSTRUCTIONS_ENGLISH, VOICE_INSTRUCTIONS_HINGLISH,
)

# ─── Config ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

JOBS: dict[str, dict] = {}

# ─── Executable resolution ────────────────────────────────────────────────────

def _find_exe(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    # Windows-specific fallbacks
    if sys.platform == "win32":
        scripts = Path(sys.executable).parent
        for c in [scripts / f"{name}.exe", scripts / name]:
            if c.exists():
                return str(c)
        for base in [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
            Path("C:/Windows/System32"),
        ]:
            for c in [base / f"{name}.exe", base / name]:
                if c.exists():
                    return str(c)
    raise FileNotFoundError(f"Cannot find '{name}'. Install it and add to PATH.")

PYTHON_EXE  = sys.executable
FFMPEG_EXE  = _find_exe("ffmpeg")
FFPROBE_EXE = _find_exe("ffprobe")

# MiKTeX only needed on Windows; TeX Live handles LaTeX on Linux automatically
if sys.platform == "win32":
    MIKTEX_BIN = os.getenv(
        "MIKTEX_BIN",
        r"C:\Users\kushw\AppData\Local\Programs\MiKTeX\miktex\bin\x64"
    )
    def _configure_miktex():
        exe = Path(MIKTEX_BIN) / "initexmf.exe"
        if exe.exists():
            subprocess.run([str(exe), "--set-config-value", "[MPM]AutoInstall=1"],
                           capture_output=True, timeout=15)
    _configure_miktex()
else:
    MIKTEX_BIN = ""

# ─── App ──────────────────────────────────────────────────────────────────────

# Allow the Vercel frontend and any localhost ports
ALLOWED_ORIGINS = [
    "https://vivacity-five.vercel.app",
    "https://*.vercel.app",
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "null",  # for file:// opened pages
]

app = FastAPI(title="Vivacity — Manim Video Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # open for now; restrict to ALLOWED_ORIGINS in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)

class GenerateRequest(BaseModel):
    session_id: str
    question: str
    format: str = "portrait"    # "portrait" | "landscape"
    language: str = "english"   # "english" | "hinglish"


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.get("/sessions")
async def get_sessions(current_user: dict = Depends(auth.get_current_user)):
    return db.get_user_sessions(current_user["id"])

@app.post("/sessions")
async def create_session_route(title: str = "New Session", current_user: dict = Depends(auth.get_current_user)):
    return db.create_session(current_user["id"], title)

@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, current_user: dict = Depends(auth.get_current_user)):
    return db.get_session_messages(session_id, current_user["id"])

@app.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, role: str, content: str, current_user: dict = Depends(auth.get_current_user)):
    return db.save_message(session_id, current_user["id"], role, content)

@app.get("/settings")
async def get_settings(current_user: dict = Depends(auth.get_current_user)):
    return db.get_user_settings(current_user["id"])

@app.post("/settings")
async def update_settings(settings: dict, current_user: dict = Depends(auth.get_current_user)):
    db.save_user_settings(current_user["id"], **settings)
    return {"success": True}

# ─── Viva Chat ────────────────────────────────────────────────────────────────

VIVA_SYSTEM_PROMPT = """You are Viva, an intelligent AI assistant built by Vivacity — a platform for generating animated, educational math and science videos using Manim. 

Your personality:
- Warm, smart, concise, and a little playful
- Expert at explaining complex topics clearly
- You are part of the Vivacity product suite
- You NEVER reveal what underlying AI model or company powers you. If asked what model you are, what company made you, or if you are ChatGPT/GPT/Gemini/Claude/etc., you always say: "I'm Viva, Vivacity's own AI model — I'm just here to help you learn and create!"
- If someone digs deeper asking how you work, say: "I'm not able to share the technical details, but all the video rendering magic happens through a separate pipeline. I'm here as your friendly interface!"

Capabilities you can help with:
- Answering any question (math, science, history, coding, etc.)
- Explaining concepts clearly 
- Helping plan what to visualize in a video
- General assistance and brainstorming

For video generation: the user can type `/video [topic]` or click the video button — a separate rendering pipeline handles that. You don't generate videos yourself, but you can help plan and discuss topics.

Keep responses concise unless the user asks for detail. Use markdown for formatting when helpful."""

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    session_id: Optional[str] = None

from fastapi.responses import StreamingResponse

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

@app.post("/chat")
async def chat(req: ChatRequest, current_user: dict = Depends(auth.get_current_user)):
    messages = [{"role": "system", "content": VIVA_SYSTEM_PROMPT}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    async def stream_generator():
        try:
            stream = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                stream=True,
                max_tokens=1024,
                temperature=0.7,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'token': delta})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# ─── Generation Routes ────────────────────────────────────────────────────────

@app.post("/generate")
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(auth.get_current_user)):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    # Store initial generation row in DB
    gen_row = db.create_generation(
        user_id=current_user["id"],
        session_id=req.session_id,
        prompt=req.question.strip(),
        fmt=req.format,
        lang=req.language
    )
    job_id = str(gen_row["id"])
    
    _set_job(job_id, "queued", 0, "Starting...")
    background_tasks.add_task(_pipeline, job_id, req.question.strip(),
                               req.format, req.language, current_user["id"])
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def status(job_id: str, current_user: dict = Depends(auth.get_current_user)):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


@app.get("/video/{job_id}")
async def video(job_id: str, current_user: dict = Depends(auth.get_current_user)):
    path = OUTPUT_DIR / f"{job_id}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not ready")
    return FileResponse(str(path), media_type="video/mp4")


app.mount("/static", StaticFiles(directory="frontend"), name="static")


# ─── Job state ────────────────────────────────────────────────────────────────

def _set_job(job_id, status, progress, message, video_url=None, error=None):
    if job_id not in JOBS:
        JOBS[job_id] = {}
    JOBS[job_id].update({
        "status": status, "progress": progress,
        "message": message, "video_url": video_url, "error": error,
    })


# ─── Pipeline ─────────────────────────────────────────────────────────────────

async def _pipeline(job_id: str, question: str, fmt: str, lang: str, user_id: str):
    work_dir = Path(tempfile.mkdtemp(prefix=f"manim_{job_id[:8]}_"))
    try:
        db.update_generation(job_id, status="running")
        # 1. Script
        _set_job(job_id, "scripting", 8, "Writing the script...")
        script = await _generate_script(question, lang)
        n = len(script["scenes"])
        JOBS[job_id]["script_preview"] = {
            "title": script.get("title", question),
            "scenes": [{"title": s["title"], "narration": s["narration"][:150]}
                       for s in script["scenes"]],
        }
        JOBS[job_id]["total_scenes"] = n

        # 2. Audio (sequential — OpenAI TTS rate limits)
        _set_job(job_id, "audio", 20, f"Generating voice for {n} scenes...")
        audio_files, durations = await _generate_audio(script["scenes"], work_dir, lang)
        JOBS[job_id]["audio_durations"] = durations

        # 3. Manim code
        _set_job(job_id, "coding", 38, "Coding the animations...")
        code = await _generate_manim_code(question, script, durations, fmt)
        scene_py = work_dir / "scene.py"
        scene_py.write_text(code, encoding="utf-8")
        db.update_generation(job_id, manim_code=code)

        # 4. Render all scenes in parallel
        _set_job(job_id, "rendering", 42, f"Rendering {n} scenes in parallel...")
        JOBS[job_id]["current_scene"] = 1

        async def _render_with_progress(i: int) -> Path:
            result = await _render_scene(work_dir, scene_py, f"Scene{i+1:02d}", fmt)
            JOBS[job_id]["current_scene"] = i + 1
            pct = 42 + int(38 * (i + 1) / n)
            _set_job(job_id, "rendering", pct, f"Scene {i+1}/{n} done ✓ (parallel)")
            return result

        scene_videos = list(await asyncio.gather(
            *[_render_with_progress(i) for i in range(n)]
        ))

        # 5. Merge AV per scene in parallel
        _set_job(job_id, "stitching", 84, "Mixing audio...")
        merged = list(await asyncio.gather(
            *[_merge_av(work_dir, v, a, durations[i], i)
              for i, (v, a) in enumerate(zip(scene_videos, audio_files))]
        ))

        # 6. Concat
        final = await _concat(work_dir, merged)
        
        # Upload to Supabase Storage
        _set_job(job_id, "done", 95, "Uploading to cloud...")
        public_url = storage.upload_video(str(final), user_id, job_id)
        db.update_generation(job_id, status="done", video_url=public_url)
        
        _set_job(job_id, "done", 100, "Your video is ready!", video_url=public_url)

    except Exception as exc:
        db.update_generation(job_id, status="error", error_msg=str(exc))
        _set_job(job_id, "error", 0, "Something went wrong", error=str(exc))
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ─── Step 1: Script ───────────────────────────────────────────────────────────

async def _generate_script(question: str, lang: str) -> dict:
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    prompt = SCRIPT_SYSTEM_PROMPT_HINGLISH if lang == "hinglish" else SCRIPT_SYSTEM_PROMPT_ENGLISH
    resp = await client.messages.create(
        model=CLAUDE_MODEL, max_tokens=4096, temperature=1,
        system=prompt,
        messages=[{"role": "user", "content": f"Create a video script for:\n\n{question}"}],
    )
    raw = resp.content[0].text.strip()
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        raise ValueError(f"No JSON in script response: {raw[:300]}")
    return json.loads(m.group())


# ─── Step 2: Audio (OpenAI TTS) ───────────────────────────────────────────────

async def _generate_audio(scenes: list, work_dir: Path, lang: str) -> tuple:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    voice        = VOICE_HINGLISH if lang == "hinglish" else VOICE_ENGLISH
    instructions = VOICE_INSTRUCTIONS_HINGLISH if lang == "hinglish" else VOICE_INSTRUCTIONS_ENGLISH

    audio_files, durations = [], []
    for i, scene in enumerate(scenes):
        resp = await client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=scene["narration"],
            instructions=instructions,
        )
        path = work_dir / f"audio_{i:02d}.mp3"
        path.write_bytes(resp.content)
        audio_files.append(path)
        durations.append(round(_get_duration(path), 2))

    return audio_files, durations


def _get_duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE_EXE, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


# ─── Step 3: Manim code ───────────────────────────────────────────────────────

async def _generate_manim_code(question: str, script: dict,
                                 durations: list, fmt: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    system = MANIM_LANDSCAPE_PROMPT if fmt == "landscape" else MANIM_PORTRAIT_PROMPT

    scenes_block = "\n\n".join([
        f"SCENE {i+1} — \"{s['title']}\"\n"
        f"  audio_duration: {durations[i]}s  (target = {durations[i]+1.5:.1f}s with tail)\n"
        f"  narration: {s['narration']}\n"
        f"  visuals: {s['visuals']}"
        for i, s in enumerate(script["scenes"])
    ])

    prompt = f"""Generate complete Manim code for this {"landscape" if fmt=="landscape" else "portrait"} video.

QUESTION: {question}
TITLE: {script.get("title", question)}
FORMAT: {"LANDSCAPE 1280x720 (16:9 — use full width, side-by-side layouts)" if fmt=="landscape" else "PORTRAIT 720x1280 (9:16 — tall vertical canvas)"}

{scenes_block}

TOTAL SCENES: {len(script["scenes"])}
Generate classes: Scene01 through Scene{len(script["scenes"]):02d}
"""
    resp = await client.messages.create(
        model=CLAUDE_MODEL, max_tokens=16000, temperature=1,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    m = (re.search(r'```python\s*([\s\S]+?)```', raw)
         or re.search(r'```python\s*([\s\S]+)', raw))
    if m:
        return m.group(1).strip()
    if raw.startswith("from manim") or raw.startswith("import"):
        return raw
    raise ValueError(f"No Python code in Manim response: {raw[:400]}")


# ─── Step 4: Render ───────────────────────────────────────────────────────────

def _build_env() -> dict:
    env = os.environ.copy()
    if sys.platform == "win32" and MIKTEX_BIN:
        env["PATH"] = f"{MIKTEX_BIN};{Path(FFMPEG_EXE).parent};" + env.get("PATH", "")
    return env


async def _render_scene(work_dir: Path, scene_py: Path, scene_name: str, fmt: str) -> Path:
    try:
        return await _render_once(work_dir, scene_py, scene_name)
    except RuntimeError as err:
        fixed = await _fix_code(scene_py.read_text(encoding="utf-8"), str(err), scene_name)
        scene_py.write_text(fixed, encoding="utf-8")
        return await _render_once(work_dir, scene_py, scene_name)


async def _render_once(work_dir: Path, scene_py: Path, scene_name: str) -> Path:
    media_dir = work_dir / f"media_{scene_name}"
    media_dir.mkdir(exist_ok=True)
    cmd = [PYTHON_EXE, "-m", "manim", str(scene_py), scene_name,
           "--media_dir", str(media_dir), "--disable_caching", "--fps", "30"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(work_dir), env=_build_env(),
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Manim failed for {scene_name}:\n{stderr.decode(errors='replace')[-2000:]}")
    mp4s = list(media_dir.glob(f"**/{scene_name}.mp4")) or list(media_dir.glob("**/*.mp4"))
    if not mp4s:
        raise FileNotFoundError(f"No MP4 found for {scene_name}")
    return sorted(mp4s, key=lambda p: p.stat().st_mtime)[-1]


async def _fix_code(code: str, error: str, scene_name: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model=CLAUDE_MODEL, max_tokens=16000,
        system="Fix this Manim code. Return ONLY the complete fixed code in a ```python block. Keep ALL scene classes. Fix only what's broken.",
        messages=[{"role": "user", "content":
            f"Error in {scene_name}:\n{error[-1200:]}\n\nCode:\n```python\n{code}\n```"}],
    )
    raw = resp.content[0].text.strip()
    m = re.search(r'```python\s*([\s\S]+?)```', raw) or re.search(r'```python\s*([\s\S]+)', raw)
    return m.group(1).strip() if m else code


# ─── Step 5: Merge AV ─────────────────────────────────────────────────────────

async def _merge_av(work_dir: Path, video: Path, audio: Path, duration: float, idx: int) -> Path:
    # Step A: Freeze the last frame for 4 extra seconds.
    # This prevents the black void when audio outlasts the animation —
    # the final frame stays visible and holds until the audio finishes.
    frozen = work_dir / f"frozen_{idx:02d}.mp4"
    freeze_cmd = [
        FFMPEG_EXE, "-y",
        "-i", str(video),
        "-vf", "tpad=stop_mode=clone:stop_duration=4",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an",   # no audio in this step
        str(frozen),
    ]
    proc = await asyncio.create_subprocess_exec(
        *freeze_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # If freeze fails (edge case), fall back to original video
        frozen = video

    # Step B: Merge frozen video with audio, trimmed to exact audio duration.
    out = work_dir / f"merged_{idx:02d}.mp4"
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", str(frozen), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),   # trim to exact audio length
        str(out),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {stderr.decode(errors='replace')[-800:]}")
    return out


# ─── Step 6: Concat ───────────────────────────────────────────────────────────

async def _concat(work_dir: Path, parts: list) -> Path:
    if len(parts) == 1:
        return parts[0]
    lst = work_dir / "concat.txt"
    lst.write_text("\n".join(f"file '{p.resolve()}'" for p in parts), encoding="utf-8")
    out = work_dir / "final.mp4"
    cmd = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c:v", "libx264", "-preset", "fast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", str(out)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {stderr.decode(errors='replace')[-800:]}")
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
