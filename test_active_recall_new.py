import json
import logging
import sys
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from app.main import app
from app.models import SessionLocal, Job, JobStatus, init_db

logging.basicConfig(level=logging.INFO)

def main():
    init_db()
    db = SessionLocal()
    
    # 1. Setup jobs for testing
    completed_jobs = db.query(Job).filter(Job.status == JobStatus.complete, Job.storyboard.isnot(None)).all()
    if not completed_jobs:
        print("No completed jobs found with a storyboard. Creating a dummy completed job...")
        dummy_job = Job(
            id=str(uuid.uuid4()),
            status=JobStatus.complete,
            storyboard="[0-5] ON SCREEN: Introduction | VO: 'Intro'",
            generated_storyboard="[0-5] ON SCREEN: Introduction | VO: 'Intro'",
            request_payload={"topic": "Test Active Recall Concept"},
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5",
            cost_breakdown={}
        )
        db.add(dummy_job)
        db.commit()
        db.refresh(dummy_job)
        completed_jobs = [dummy_job]
        
    incomplete_job = db.query(Job).filter(Job.status != JobStatus.complete).first()
    if not incomplete_job:
        incomplete_job = Job(status=JobStatus.queued)
        db.add(incomplete_job)
        db.commit()
        db.refresh(incomplete_job)

    client = TestClient(app)
    job = completed_jobs[0]
    
    # Reset practice questions and cost breakdown
    job.practice_questions = None
    job.cost_breakdown = {}
    job.estimated_cost_usd = 0.0
    db.commit()
    db.refresh(job)
    
    print(f"Testing Job ID: {job.id}")
    
    # --- Test 1: Fresh Generation with Retry (First response is invalid JSON) ---
    print("\n--- Test 1: Fresh Generation with Retry ---")
    with patch("app.llm_provider.get_llm_provider") as mock_get_provider:
        mock_llm = mock_get_provider.return_value
        
        mock_response_bad = MagicMock()
        mock_response_bad.text = 'invalid json'
        mock_response_bad.input_tokens = 100
        mock_response_bad.output_tokens = 10
        mock_response_bad.model = "claude-haiku-4-5"
        
        mock_response_good = MagicMock()
        mock_response_good.text = '[{"question": "Q1", "answer": "A1", "explanation": "E1"}, {"question": "Q2", "answer": "A2", "explanation": "E2"}, {"question": "Q3", "answer": "A3", "explanation": "E3"}]'
        mock_response_good.input_tokens = 150
        mock_response_good.output_tokens = 90
        mock_response_good.model = "claude-haiku-4-5"
        
        mock_llm.generate.side_effect = [mock_response_bad, mock_response_good]
        
        response1 = client.post(f"/api/jobs/{job.id}/practice-questions")
        assert response1.status_code == 200, f"Expected 200, got {response1.status_code}"
        
        data1 = response1.json()
        print("PASS: Fresh generation succeeded after retry!")
        print("Response structure:", data1)
        
        # Verify schema
        assert data1["job_id"] == job.id
        assert len(data1["questions"]) == 3
        assert data1["questions"][0]["question"] == "Q1"
        assert data1["questions"][0]["answer"] == "A1"
        assert data1["questions"][0]["explanation"] == "E1"
        assert "cost_usd" in data1
        print(f"PASS: Verified response schema, cost: {data1['cost_usd']}")
        
        # Verify LLM was called twice (due to retry)
        assert mock_llm.generate.call_count == 2
        print("PASS: LLM was called exactly twice (once for initial fail, once for retry).")
        
        # Verify cost logging in DB
        db.refresh(job)
        pq_breakdown = job.cost_breakdown.get("practice_questions", {})
        assert pq_breakdown["calls"] == 2
        assert pq_breakdown["input_tokens"] == 250
        assert pq_breakdown["output_tokens"] == 100
        assert pq_breakdown["cost_usd"] > 0
        assert job.estimated_cost_usd == pq_breakdown["cost_usd"]
        print("PASS: Verified cost logging in database and cost_breakdown.")
        
    # --- Test 2: Cache Hit (No LLM calls) ---
    print("\n--- Test 2: Cache Hit ---")
    with patch("app.llm_provider.get_llm_provider") as mock_get_provider:
        mock_llm = mock_get_provider.return_value
        
        response2 = client.post(f"/api/jobs/{job.id}/practice-questions")
        assert response2.status_code == 200
        data2 = response2.json()
        
        assert data2 == data1
        assert mock_llm.generate.call_count == 0
        print("PASS: Cache hit returned identical response instantly with no new LLM calls!")

    # --- Test 3: Regenerate (Forces new LLM call) ---
    print("\n--- Test 3: Regenerate ---")
    with patch("app.llm_provider.get_llm_provider") as mock_get_provider:
        mock_llm = mock_get_provider.return_value
        
        mock_response_new = MagicMock()
        mock_response_new.text = '[{"question": "New Q1", "answer": "New A1", "explanation": "New E1"}, {"question": "New Q2", "answer": "New A2", "explanation": "New E2"}, {"question": "New Q3", "answer": "New A3", "explanation": "New E3"}]'
        mock_response_new.input_tokens = 110
        mock_response_new.output_tokens = 85
        mock_response_new.model = "claude-haiku-4-5"
        mock_llm.generate.return_value = mock_response_new
        
        response3 = client.post(f"/api/jobs/{job.id}/practice-questions?regenerate=true")
        assert response3.status_code == 200
        data3 = response3.json()
        
        assert data3["questions"][0]["question"] == "New Q1"
        assert mock_llm.generate.call_count == 1
        
        # Verify cost incremented in DB
        db.refresh(job)
        pq_breakdown = job.cost_breakdown.get("practice_questions", {})
        assert pq_breakdown["calls"] == 3
        print("PASS: Regenerate successfully forced new LLM call and incremented DB cost statistics!")

    # --- Test 4: 404 Not Found ---
    print("\n--- Test 4: 404 Not Found ---")
    fake_id = str(uuid.uuid4())
    resp_404 = client.post(f"/api/jobs/{fake_id}/practice-questions")
    assert resp_404.status_code == 404
    print("PASS: Returned 404 for non-existent job ID.")

    # --- Test 5: 422 Unprocessable (Incomplete Job) ---
    print("\n--- Test 5: 422 Incomplete Job ---")
    resp_422 = client.post(f"/api/jobs/{incomplete_job.id}/practice-questions")
    assert resp_422.status_code == 422
    print("PASS: Returned 422 for incomplete job.")

    # --- Test 6: Verify public job endpoint contains practice_questions ---
    print("\n--- Test 6: Public Job Get Endpoint Response contains practice_questions ---")
    resp_public = client.get(f"/api/jobs/{job.id}")
    assert resp_public.status_code == 200
    pub_data = resp_public.json()
    assert "practice_questions" in pub_data
    assert len(pub_data["practice_questions"]) == 3
    assert pub_data["practice_questions"][0]["question"] == "New Q1"
    print("PASS: Verified that practice_questions are included in the public job response shape!")

    db.close()
    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
