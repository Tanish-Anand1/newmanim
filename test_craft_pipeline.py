import os
from app.models import SessionLocal, Job, JobStatus
from app.job_queue import dispatch_job

def rerun_jobs_with_craft_profile():
    with SessionLocal() as db:
        # Find 3 completed or failed storyboard jobs
        jobs = db.query(Job).filter(
            Job.job_kind == "storyboard",
            Job.storyboard.is_not(None)
        ).order_by(Job.created_at.desc()).limit(3).all()
        
        if not jobs:
            print("No existing storyboard jobs found.")
            return

        job_ids = [j.id for j in jobs]
        for j in jobs:
            j.pipeline_profile = "craft"
            j.status = JobStatus.queued
            j.attempt_number = 0
            # Inject storyboard into payload to satisfy job queue requirements
            payload = dict(j.request_payload or {})
            payload["storyboard"] = j.storyboard
            payload["scene_name"] = j.scene_name or f"test_scene_{j.id[:8]}"
            j.request_payload = payload
            
        db.commit()
        
    print(f"Dispatched {len(job_ids)} jobs for craft re-rendering.")
    for jid in job_ids:
        print(f"Processing job {jid}...")
        try:
            dispatch_job(jid)
            print(f"Successfully finished job {jid}")
        except Exception as e:
            print(f"Error processing job {jid}: {e}")

if __name__ == "__main__":
    rerun_jobs_with_craft_profile()
