from pathlib import Path

from app import pipeline, template_pipeline
from app.llm_provider import LLMResponse, ProviderUnavailableError
from app.models import Job, JobStatus, SessionLocal, init_db


class TemplateProvider:
    name = "anthropic"
    model = "claude-haiku-4-5"
    fast_model = "claude-haiku-4-5"

    def generate(self, system: str, user_message: str, max_tokens: int, model: str | None = None) -> LLMResponse:
        return LLMResponse(
            text=(
                '{"title":"Definition","beats":['
                '{"beat_number":1,"layout":"concept","heading":"Definition",'
                '"lines":["A concise statement"],"equations":[],"visual_kind":"none","visual_labels":[]}'
                "]}"
            ),
            truncated=False,
            input_tokens=100,
            output_tokens=80,
        )


class CapacityError(Exception):
    status_code = 429


def test_template_pipeline_completes_and_persists_code(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TEMPLATE_PLANNER", "llm")
    init_db()
    with SessionLocal() as db:
        job = Job(
            pipeline_profile="template",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5",
            llm_fast_model="claude-haiku-4-5",
            tts_provider="silent",
            cost_breakdown=pipeline.empty_cost_breakdown(),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    beat = pipeline.StoryboardBeat(1, 0, 1, "Show a concise definition", None)
    timed = [pipeline.TimedBeat(beat, None, 1.0, 0.0)]
    video_path = tmp_path / "render.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr(pipeline, "WORK_ROOT", tmp_path / "runs")
    monkeypatch.setattr(pipeline, "provider_for_job", lambda db, job_id: TemplateProvider())
    monkeypatch.setattr(pipeline, "generate_timed_beat_audio", lambda *args, **kwargs: timed)
    monkeypatch.setattr(
        pipeline,
        "concatenate_audio",
        lambda timed_beats, audio_dir, out_path: out_path.write_bytes(b"audio"),
    )
    monkeypatch.setattr(pipeline, "render_scene", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(pipeline, "find_rendered_video", lambda work_dir, scene_name: video_path)
    monkeypatch.setattr(
        pipeline,
        "stretch_audio_to_duration",
        lambda audio, duration, out: out.write_bytes(b"audio"),
    )
    monkeypatch.setattr(pipeline, "mux_audio_video", lambda video, audio, out: out.write_bytes(b"final"))
    monkeypatch.setattr(pipeline, "should_run_vision_quality_check", lambda job_id: True)
    monkeypatch.setattr(
        pipeline,
        "assess_video_quality",
        lambda *args, **kwargs: (_ for _ in ()).throw(CapacityError("provider quota unavailable")),
    )
    monkeypatch.setattr(template_pipeline, "get_media_duration", lambda path: 1.0)
    monkeypatch.setattr(template_pipeline, "detect_frame_overflow", lambda *args, **kwargs: [])
    monkeypatch.setattr(template_pipeline, "detect_sparse_frames", lambda *args, **kwargs: [])
    monkeypatch.setattr(template_pipeline, "upload_video", lambda final_path, job_id: "/outputs/final.mp4")

    template_pipeline.run_template_pipeline_for_job(
        job_id,
        '[0-1] ON SCREEN: Show a concise definition | VO: (silent)',
        "TemplateScene",
    )

    with SessionLocal() as db:
        completed = db.get(Job, job_id)
        assert completed.status == JobStatus.complete
        assert completed.output_video_url == "/outputs/final.mp4"
        assert "class TemplateScene(Scene):" in completed.generated_code
        assert completed.cost_breakdown["anthropic"]["calls"] == 1
