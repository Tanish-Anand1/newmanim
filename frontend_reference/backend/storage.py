# ─── Vivacity Storage — Supabase video upload ─────────────────────────────────
import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
BUCKET = "videos"

_client = None

def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def upload_video(local_path: str, user_id: str, job_id: str) -> str:
    """
    Upload a rendered mp4 to Supabase Storage.
    Returns the public URL of the uploaded file.
    """
    client = _get_client()
    remote_path = f"{user_id}/{job_id}.mp4"

    with open(local_path, "rb") as f:
        data = f.read()

    # Remove old file if exists (upsert)
    try:
        client.storage.from_(BUCKET).remove([remote_path])
    except Exception:
        pass

    client.storage.from_(BUCKET).upload(
        path=remote_path,
        file=data,
        file_options={"content-type": "video/mp4", "upsert": "true"},
    )

    # Build public URL
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{remote_path}"
    return public_url


def delete_video(user_id: str, job_id: str):
    """Delete a stored video (e.g. when user deletes a generation)."""
    client = _get_client()
    remote_path = f"{user_id}/{job_id}.mp4"
    try:
        client.storage.from_(BUCKET).remove([remote_path])
    except Exception:
        pass
