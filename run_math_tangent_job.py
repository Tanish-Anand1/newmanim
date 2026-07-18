import uuid
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job

def main():
    job_id = str(uuid.uuid4())
    topic = (
        "Let f(x) = x³ − 3x² + 4 on the interval [−2, 3]. "
        "A tangent line is drawn to the curve at the point where f'(x) = 0 and f(x) is a local minimum. "
        "This tangent line intersects the curve again at a second point P. "
        "(a) Find the coordinates of P. "
        "(b) Find the area enclosed between the curve y = f(x) and the tangent line, bounded by the two intersection points. "
        "(c) If a circle is inscribed such that it's tangent to the tangent line and passes through the local maximum point of f(x), find its radius given the circle's center lies on the y-axis."
    )
    
    payload = {
        "topic": topic,
        "duration_seconds": 120,
        "audience": "Advanced High School Calculus Student",
        "scene_name": "TangentMinProblem",
        "orientation": "portrait",
    }
    
    with SessionLocal() as db:
        job = Job(
            id=job_id,
            status=JobStatus.queued,
            job_kind="topic",
            pipeline_profile="craft",
            request_payload=payload,
            scene_name="TangentMinProblem",
            orientation="portrait",
        )
        db.add(job)
        db.commit()
        print(f"Created job {job_id}")

    print("Running topic pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=topic,
            duration_seconds=120,
            audience="Advanced High School Calculus Student",
            scene_name="TangentMinProblem",
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
