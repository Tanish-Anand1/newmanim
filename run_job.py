import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.job_queue import dispatch_job
from app.models import SessionLocal, Job
from app.pipeline import empty_cost_breakdown

def main():
    db = SessionLocal()
    try:
        # Read provider settings from environment
        llm_provider = os.getenv("LLM_PROVIDER", "anthropic")
        tts_provider = os.getenv("TTS_PROVIDER", "openai")
        # Create a job for a topic
        job = Job(
            job_kind="topic",
            pipeline_profile="legacy",
            llm_provider=llm_provider,
            llm_model=None,
            llm_fast_model=None,
            first_attempt_llm_provider=None,
            first_attempt_llm_model=None,
            tts_provider=tts_provider,
            tts_model=None,
            priority=0,
            request_payload={
                "topic": "Derivative of x^2",
                "duration_seconds": 30,
                "audience": "high school",
                "scene_name": "DerivativeScene",
                "orientation": "portrait"
            },
            request_fingerprint=None,
            idempotency_key=None,
            storyboard=None,
            generated_storyboard=None,
            generated_code=None,
            scene_name="DerivativeScene",
            orientation="portrait",
            estimated_cost_usd=0.0,
            cost_budget_usd=None,
        )
        # Set cost_breakdown to empty dict
        job.cost_breakdown = empty_cost_breakdown()
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"Created job {job.id}")

        # Dispatch the job (runs pipeline synchronously)
        dispatch_job(job.id)

        # Refresh to get updated fields
        db.refresh(job)
        print(f"Job status: {job.status}")
        print(f"Estimated cost: {job.estimated_cost_usd}")
        print(f"Output video URL: {job.output_video_url}")
        if job.error:
            print(f"Error: {job.error}")
    finally:
        db.close()

if __name__ == "__main__":
    main()