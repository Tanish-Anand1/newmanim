# ─── Vivacity Database Helpers (Supabase) ─────────────────────────────────────
import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

_client: Optional[Client] = None

def get_supabase() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


# ─── Users ────────────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[dict]:
    res = get_supabase().table("users").select("*").eq("email", email).single().execute()
    return res.data if res.data else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    res = get_supabase().table("users").select("*").eq("id", user_id).single().execute()
    return res.data if res.data else None





# ─── Sessions ─────────────────────────────────────────────────────────────────

def create_session(user_id: str, title: str = "New Session") -> dict:
    res = get_supabase().table("sessions").insert({
        "user_id": user_id,
        "title": title,
    }).execute()
    return res.data[0]


def get_user_sessions(user_id: str, limit: int = 50) -> list:
    res = (
        get_supabase()
        .table("sessions")
        .select("id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def update_session_title(session_id: str, user_id: str, title: str):
    get_supabase().table("sessions").update({"title": title}).eq("id", session_id).eq("user_id", user_id).execute()


def delete_session(session_id: str, user_id: str):
    get_supabase().table("sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()


# ─── Messages ─────────────────────────────────────────────────────────────────

def save_message(session_id: str, user_id: str, role: str, content: str) -> dict:
    res = get_supabase().table("messages").insert({
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "content": content,
    }).execute()
    return res.data[0]


def get_session_messages(session_id: str, user_id: str) -> list:
    res = (
        get_supabase()
        .table("messages")
        .select("id, role, content, created_at")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


# ─── Generations ──────────────────────────────────────────────────────────────

def create_generation(user_id: str, session_id: str, prompt: str, fmt: str, lang: str) -> dict:
    res = get_supabase().table("generations").insert({
        "user_id": user_id,
        "session_id": session_id,
        "prompt": prompt,
        "format": fmt,
        "lang": lang,
        "status": "pending",
    }).execute()
    return res.data[0]


def update_generation(gen_id: str, **kwargs):
    get_supabase().table("generations").update(kwargs).eq("id", gen_id).execute()


def get_user_generations(user_id: str, limit: int = 100) -> list:
    res = (
        get_supabase()
        .table("generations")
        .select("id, session_id, prompt, status, video_url, format, lang, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─── Memory Notes ─────────────────────────────────────────────────────────────

def get_memory_notes(user_id: str) -> list:
    res = (
        get_supabase()
        .table("memory_notes")
        .select("id, note, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def add_memory_note(user_id: str, note: str) -> dict:
    res = get_supabase().table("memory_notes").insert({"user_id": user_id, "note": note}).execute()
    return res.data[0]


def delete_memory_note(note_id: str, user_id: str):
    get_supabase().table("memory_notes").delete().eq("id", note_id).eq("user_id", user_id).execute()


# ─── User Settings ────────────────────────────────────────────────────────────

def get_user_settings(user_id: str) -> dict:
    res = get_supabase().table("user_settings").select("*").eq("user_id", user_id).single().execute()
    return res.data or {}


def save_user_settings(user_id: str, **kwargs):
    get_supabase().table("user_settings").upsert({"user_id": user_id, **kwargs}).execute()
