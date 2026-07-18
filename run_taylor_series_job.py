"""
Submit a Taylor Series video job covering all 3 problems:
  1. Taylor series for ln(x) centered at a=1, P3(x), approximating ln(1.2)
  2. Evaluating limits with Maclaurin series: lim x->0 (x cos(x) - sin(x)) / x^3
  3. 10th derivative of e^(-x^2) at x=0 via Maclaurin expansion
"""
import sys
import uuid
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from app.models import SessionLocal, Job, JobStatus
from app.pipeline import run_topic_pipeline_for_job


TOPIC = """
Taylor and Maclaurin Series — Three Core Problems

Problem 1: Taylor Series for ln(x) centered at a = 1.
Compute f(x)=ln(x) and its first four derivatives evaluated at x=1:
  f(1)=0, f'(1)=1, f''(1)=-1, f'''(1)=2, f^(4)(1)=-6.
Using the Taylor series formula f(x) = sum_{n=0}^{infty} f^(n)(a)/n! * (x-a)^n,
derive the full series:
  ln(x) = (x-1) - (x-1)^2/2 + (x-1)^3/3 - (x-1)^4/4 + ...
State the third-degree Taylor polynomial:
  P3(x) = (x-1) - (x-1)^2/2 + (x-1)^3/3
Substitute x=1.2 to approximate ln(1.2):
  P3(1.2) = 0.2 - 0.02 + 0.00267 ≈ 0.18267

Problem 2: Limit evaluation via Maclaurin series.
Use the standard expansions:
  cos(x) = 1 - x^2/2! + x^4/4! - ...
  sin(x) = x - x^3/3! + x^5/5! - ...
Expand x*cos(x) and subtract sin(x):
  x*cos(x) - sin(x) = -x^3/3 + x^5/30 - ...
Divide by x^3 and take the limit as x -> 0 to get -1/3.

Problem 3: 10th derivative of e^(-x^2) at x=0.
Start from the Maclaurin series e^u = sum_{n=0}^infty u^n/n!.
Substitute u = -x^2 to get e^(-x^2) = sum_{n=0}^infty (-1)^n x^(2n) / n!.
The x^10 term (n=5) has coefficient (-1)^5 / 5! = -1/120.
Using the Maclaurin identity coefficient = f^(10)(0)/10!, solve:
  f^(10)(0) = -10!/5! = -(10*9*8*7*6) = -30240.
"""


def main():
    job_id = str(uuid.uuid4())

    payload = {
        "topic": TOPIC,
        "duration_seconds": 180,
        "audience": "Advanced High School / Early University Calculus Student",
        "scene_name": "TaylorSeriesThreeProblems",
        "orientation": "landscape",
        "pipeline_profile": "craft",
    }

    with SessionLocal() as db:
        job = Job(
            id=job_id,
            status=JobStatus.queued,
            job_kind="topic",
            pipeline_profile="craft",
            request_payload=payload,
            scene_name="TaylorSeriesThreeProblems",
            orientation="landscape",
        )
        db.add(job)
        db.commit()
        print(f"Created job {job_id}")

    print("Running Taylor Series pipeline...")
    try:
        run_topic_pipeline_for_job(
            job_id=job_id,
            topic=TOPIC,
            duration_seconds=180,
            audience="Advanced High School / Early University Calculus Student",
            scene_name="TaylorSeriesThreeProblems",
            orientation="landscape",
            pipeline_profile="craft",
        )
        print(f"Job {job_id} completed successfully.")
    except Exception as e:
        print(f"Error running job {job_id}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
