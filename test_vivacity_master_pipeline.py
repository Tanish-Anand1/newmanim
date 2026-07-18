import json
import logging
import sys
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from app.main import app
from app.models import SessionLocal, Job, JobStatus, init_db
from app.prerequisite_gate import resolve_prerequisite_gate
from app.vivacity_prompts import build_script_generation_system_prompt, build_manim_codegen_addon

logging.basicConfig(level=logging.INFO)

def main():
    init_db()
    db = SessionLocal()
    client = TestClient(app)

    print("\n" + "="*60 + "\nTesting Vivacity Master Pipeline Integration\n" + "="*60)

    # 1. Test Prerequisite Gate Directly
    print("\n--- Test 1: Prerequisite Gate with No Prerequisites ---")
    gate_res_empty = resolve_prerequisite_gate(
        topic="finding critical points via first derivative",
        exam_context="JEE Main",
        assumed_prerequisites=[]
    )
    assert not gate_res_empty.insert_refresher
    assert len(gate_res_empty.unconfirmed_prerequisites) == 0
    print("PASS: Prerequisite gate returned no refresher when assumed_prerequisites list is empty.")

    print("\n--- Test 2: Prerequisite Gate with Unconfirmed Prerequisites ---")
    # Simulate frontend sending unconfirmed prerequisites as a list of strings
    gate_res_prereq = resolve_prerequisite_gate(
        topic="finding critical points via first derivative",
        exam_context="JEE Main",
        assumed_prerequisites=["calculus basics", "differentiation rules"]
    )
    assert gate_res_prereq.insert_refresher
    assert "calculus basics" in gate_res_prereq.unconfirmed_prerequisites
    assert "differentiation rules" in gate_res_prereq.unconfirmed_prerequisites
    print("PASS: Prerequisite gate correctly identified unconfirmed prerequisites and set insert_refresher=True.")

    # 2. Test Storyboard System Prompt Building
    print("\n--- Test 3: System Prompt Generation with Scaffolding/Refresher ---")
    prompt = build_script_generation_system_prompt(
        topic="finding critical points via first derivative",
        exam_context="JEE Main",
        flagged_as_weak_topic=True,
        unconfirmed_prerequisites=["differentiation rules"]
    )
    assert "STEP 0 (mandatory — unconfirmed prerequisites: differentiation rules):" in prompt
    assert "STUDENT CONTEXT: This topic is flagged as weak. Add extra concrete examples" in prompt
    assert "STEP 1 — Concrete instance:" in prompt
    assert "STEP 6 — ACTIVE RECALL CHECKPOINT:" in prompt
    print("PASS: System prompt builder includes refresher (STEP 0), student context notes, and all required steps.")

    # 3. Test API Endpoint Model Validation
    print("\n--- Test 4: API Endpoint Draft Storyboard with New Fields ---")
    request_data = {
        "topic": "differentiation rules",
        "duration_seconds": 60,
        "audience": "Advanced High School Calculus Student",
        "exam_context": "JEE Main",
        "student_signal": {
            "self_rated_confidence": 2,
            "flagged_as_weak_topic": True,
            "prior_attempt_count": 1
        },
        "assumed_prerequisites": ["limits"]
    }
    
    with patch("app.pipeline.get_llm_provider") as mock_get_provider:
        mock_llm = mock_get_provider.return_value
        mock_llm.name = "openai"
        mock_response = MagicMock()
        mock_response.text = '# Approach: concrete first.\n[0-5] ON SCREEN: differentiation rules | VO: "Lets learn differentiation rules."'
        mock_response.input_tokens = 50
        mock_response.output_tokens = 50
        mock_response.provider_name = "openai"
        mock_response.model = "gpt-4o"
        mock_llm.generate.return_value = mock_response

        response = client.post("/api/storyboard/draft", json=request_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify the LLM generate call was called with correct system prompt (STEP 0 refresher present)
        called_system = mock_llm.generate.call_args.kwargs['system']
        assert "STEP 0 (mandatory — unconfirmed prerequisites: limits):" in called_system
        assert "STUDENT CONTEXT: This topic is flagged as weak." in called_system
        print("PASS: /api/storyboard/draft correctly accepted new fields, ran prerequisite gate, and built the system prompt.")

    # 4. Test Generate Endpoint and Database Serialization
    print("\n--- Test 5: /api/generate Job Queueing with New Fields ---")
    generate_data = {
        "topic": "differentiation rules",
        "duration_seconds": 60,
        "audience": "Advanced High School Calculus Student",
        "scene_name": "TestMasterPipelineScene",
        "orientation": "portrait",
        "pipeline_profile": "craft",
        "exam_context": "JEE Main",
        "student_signal": {
            "self_rated_confidence": 1,
            "flagged_as_weak_topic": True,
            "prior_attempt_count": 2
        },
        "assumed_prerequisites": ["limits"]
    }

    # Remove any existing job with the same scene name to prevent conflict or enforce a fresh generation
    db.query(Job).filter(Job.scene_name == "TestMasterPipelineScene").delete()
    db.commit()

    with patch("app.main.schedule_generation_job") as mock_schedule:
        response_gen = client.post("/api/generate", json=generate_data)
        assert response_gen.status_code == 200
        job_id = response_gen.json()["job_id"]
        print(f"Created Job ID: {job_id}")
        
        # Verify job was written to the DB with payload fields
        job = db.get(Job, job_id)
        assert job is not None
        payload = job.request_payload
        assert payload["exam_context"] == "JEE Main"
        assert payload["student_signal"]["flagged_as_weak_topic"] is True
        assert "limits" in payload["assumed_prerequisites"]
        print("PASS: /api/generate successfully saved student context and prerequisites into job request payload.")

    # 5. Test Codegen System Prompt Integration
    print("\n--- Test 6: Codegen System Prompt Addon ---")
    from app.pipeline import generate_manim_code
    
    with patch("app.pipeline.codegen_model_for_attempt") as mock_model, \
         patch("app.pipeline.enforce_job_cost_budget"), \
         patch("app.pipeline.selected_reference_scenes"), \
         patch("app.pipeline.approved_failure_instructions"), \
         patch("app.llm_provider.get_llm_provider") as mock_get_provider:
        
        mock_llm = mock_get_provider.return_value
        mock_llm.name = "openai"
        mock_response = MagicMock()
        mock_response.text = "class TestScene(Scene):\n    def construct(self):\n        pass"
        mock_response.input_tokens = 50
        mock_response.output_tokens = 50
        mock_response.provider_name = "openai"
        mock_response.model = "gpt-4o"
        mock_response.truncated = False
        mock_llm.generate.return_value = mock_response

        # Generate manim code
        generate_manim_code(
            provider=mock_llm,
            storyboard="[0-5] ON SCREEN: Example [RECALL_CHECKPOINT] | VO: 'Intro'",
            scene_name="TestScene",
            timed_beats=[],
            db=db,
            job_id=job_id
        )

        called_system = mock_llm.generate.call_args.kwargs['system']
        assert "RECALL CHECKPOINT RENDERING" in called_system
        assert "vivacity_video_constitution.md" in called_system
        print("PASS: generate_manim_code correctly appended the build_manim_codegen_addon to system prompt.")

    db.close()
    print("\nALL VIVACITY MASTER PIPELINE TESTS PASSED!")

if __name__ == "__main__":
    main()
