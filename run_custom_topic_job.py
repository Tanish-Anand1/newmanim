import uuid
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job

def main():
    job_id = str(uuid.uuid4())
    topic = (
        "Analyze the cubic curve f(x) = x³ − 3x² + 4. "
        "Prove that the tangent line at its local minimum intersects the curve again at P(−1,0). "
        "Calculate the exact area enclosed between the curve and this tangent line. "
        "Finally, construct a circle centered on the y-axis tangent to the minimum tangent line and passing through the local maximum of the curve, solving for its radius."
    )
    
    payload = {
        "topic": topic,
        "duration_seconds": 120,
        "audience": "Advanced High School Calculus Student",
        "scene_name": "CubicTangentCircleAnalysis",
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
            scene_name="CubicTangentCircleAnalysis",
            orientation="portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created custom job {job_id}")

    print("Running custom topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=120,
            audience="Advanced High School Calculus Student",
            scene_name="CubicTangentCircleAnalysis",
            orientation="portrait",
            pipeline_profile="craft"
        )
        print(f"Job {job_id} run completed successfully.")
    except Exception as e:
        print(f"Error running job {job_id}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
