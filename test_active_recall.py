import json
import logging
import sys
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.models import SessionLocal, Job, JobStatus, init_db

logging.basicConfig(level=logging.INFO)

def main():
    init_db()
    db = SessionLocal()
    
    # 1. Setup jobs for testing
    completed_jobs = db.query(Job).filter(Job.status == JobStatus.complete, Job.storyboard.isnot(None)).limit(2).all()
    if not completed_jobs:
        print("No completed jobs found with a storyboard.")
        sys.exit(0)
        
    incomplete_job = db.query(Job).filter(Job.status != JobStatus.complete).first()
    if not incomplete_job:
        # Create a dummy incomplete job
        incomplete_job = Job(status=JobStatus.queued)
        db.add(incomplete_job)
        db.commit()
        db.refresh(incomplete_job)

    client = TestClient(app)
    
    # Happy Path & Cache & Regenerate tests
    print("\n" + "="*60 + "\nTesting Topic Extraction & Idempotency\n" + "="*60)
    job = completed_jobs[0]
    
    # Clear existing practice questions to test fresh generation
    job.practice_questions = None
    db.commit()
    
    print(f"Testing Job ID: {job.id}")
    
    with patch("app.llm_provider.get_llm_provider") as mock_get_provider:
        mock_llm = mock_get_provider.return_value
        # Mock response text
        mock_llm.generate.return_value.text = '[{"question": "Q1", "options": ["A", "B"], "correct_answer": "A", "explanation": "E1"}]'
        
        # Call 1: Fresh Generation
        print("\n--- Test 1: Fresh Generation ---")
        response1 = client.post(f"/api/jobs/{job.id}/practice-questions")
        if response1.status_code == 200:
            print("PASS: Fresh generation returned 200 OK")
            print("Response:", response1.json())
        else:
            print(f"FAIL: Fresh generation returned {response1.status_code}")
            
        call_count1 = mock_llm.generate.call_count
        if call_count1 == 1:
            print("PASS: LLM was called exactly once.")
        else:
            print(f"FAIL: LLM was called {call_count1} times.")
            
        # Extract the topic from the prompt that was sent to the LLM
        prompt_used = mock_llm.generate.call_args.kwargs['user_message']
        if "Video Topic: Unknown" not in prompt_used:
            print("PASS: Topic was correctly extracted and is not 'Unknown Topic'")
            # print first line with topic
            for line in prompt_used.split('\\n'):
                if line.startswith("Video Topic:"):
                    print("Extracted", line)
        else:
            print("FAIL: Topic fallback failed, still 'Unknown Topic'")
            
        # Call 2: Cache Hit
        print("\n--- Test 2: Cache Hit ---")
        response2 = client.post(f"/api/jobs/{job.id}/practice-questions")
        if response2.status_code == 200 and response2.json() == response1.json():
            print("PASS: Cache hit returned 200 OK and identical data.")
        else:
            print("FAIL: Cache hit did not return identical data.")
            
        call_count2 = mock_llm.generate.call_count
        if call_count2 == 1:
            print("PASS: LLM was NOT called again on cache hit.")
        else:
            print(f"FAIL: LLM was called {call_count2} times.")
            
        # Call 3: Regenerate
        print("\n--- Test 3: Regenerate ---")
        mock_llm.generate.return_value.text = '[{"question": "Q2", "options": ["C", "D"], "correct_answer": "D", "explanation": "E2"}]'
        response3 = client.post(f"/api/jobs/{job.id}/practice-questions?regenerate=true")
        
        if response3.status_code == 200 and response3.json() != response1.json():
            print("PASS: Regenerate returned 200 OK and new data.")
        else:
            print("FAIL: Regenerate did not return new data.")
            
        call_count3 = mock_llm.generate.call_count
        if call_count3 == 2:
            print("PASS: LLM was called exactly once more for regeneration.")
        else:
            print(f"FAIL: LLM was called {call_count3} times.")
            
    print("\n" + "="*60 + "\nTesting Negative Paths\n" + "="*60)
    
    # Test 4: 404 Not Found
    print("\n--- Test 4: 404 Not Found ---")
    fake_id = str(uuid.uuid4())
    resp_404 = client.post(f"/api/jobs/{fake_id}/practice-questions")
    if resp_404.status_code == 404:
        print("PASS: Returned 404 for non-existent job.")
    else:
        print(f"FAIL: Returned {resp_404.status_code} for non-existent job.")
        
    # Test 5: 422 Unprocessable Entity (Incomplete Job)
    print("\n--- Test 5: 422 Incomplete Job ---")
    resp_422 = client.post(f"/api/jobs/{incomplete_job.id}/practice-questions")
    if resp_422.status_code == 422:
        print("PASS: Returned 422 for incomplete job.")
    else:
        print(f"FAIL: Returned {resp_422.status_code} for incomplete job.")

    db.close()

if __name__ == "__main__":
    main()
