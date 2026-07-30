import sys
import uuid
import os

os.environ["LLM_PROVIDER_FAILOVER"] = "0"

from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job

def main():
    job_id = str(uuid.uuid4())
    topic = "Visually prove that the sum of the first n odd integers equals n squared."
    
    payload = {
        "topic": topic,
        "duration_seconds": 10,
        "audience": "Beginner",
        "scene_name": "SumOfOdds",
        "orientation": "portrait",
        "pipeline_profile": "craft"
    }
    
    with SessionLocal() as db:
        job = Job(
            id=job_id,
            status=JobStatus.queued,
            job_kind="topic",
            pipeline_profile="craft",
            request_payload=payload,
            scene_name="SumOfOdds",
            orientation="portrait",
            llm_provider="gemini",
            first_attempt_llm_provider="gemini",
        )
        db.add(job)
        db.commit()
        print(f"Created custom job {job_id}")

    print("Running custom topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=10,
            audience="Beginner",
            scene_name="SumOfOdds",
            orientation="portrait",
            pipeline_profile="craft"
        )
        print(f"Job {job_id} run completed successfully.")
        
        with SessionLocal() as db:
            j = db.query(Job).filter_by(id=job_id).first()
            if j:
                print(f"Final Estimated Cost: {j.estimated_cost_usd}")
                print(f"Video URL: {j.output_video_url}")
                print(f"Generated Code: {j.generated_code[:200] if j.generated_code else 'None'}")
            else:
                print("Job not found in DB")
            
    except Exception as e:
        print(f"Error running job {job_id}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
