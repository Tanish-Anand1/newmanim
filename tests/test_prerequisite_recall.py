import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app, get_db
from app.models import Base, Job, JobStatus, RecallResponse as RecallResponseRecord
from app.prerequisite_gate import StudentSignal, TopicPrerequisites, resolve_prerequisite_gate
from app.pipeline import generate_recall_instance, recall_numeric_tokens
from app.vivacity_prompts import RECALL_CHECKPOINT_TAG, build_script_generation_system_prompt


def test_prerequisite_gate_no_gap():
    signal = StudentSignal(self_rated_confidence=3, flagged_as_weak_topic=False, unconfirmed_prerequisites=["limits"])
    topic = TopicPrerequisites(topic_id="integration by parts", prerequisites=["basic integration"])
    assert resolve_prerequisite_gate(signal, topic) == []


def test_prerequisite_gate_one_gap():
    signal = StudentSignal(
        self_rated_confidence=3,
        flagged_as_weak_topic=False,
        unconfirmed_prerequisites=["basic integration", "limits"],
    )
    topic = TopicPrerequisites(topic_id="integration by parts", prerequisites=["basic integration", "product rule"])
    assert resolve_prerequisite_gate(signal, topic) == ["basic integration"]


def test_prerequisite_gate_all_prerequisites_gap():
    signal = StudentSignal(
        self_rated_confidence=3,
        flagged_as_weak_topic=False,
        unconfirmed_prerequisites=["basic integration", "product rule"],
    )
    topic = TopicPrerequisites(topic_id="integration by parts", prerequisites=["basic integration", "product rule"])
    assert resolve_prerequisite_gate(signal, topic) == ["basic integration", "product rule"]


def test_step_zero_prompt_is_only_injected_for_a_gap():
    unchanged = build_script_generation_system_prompt(
        topic="integration by parts",
        exam_context="JEE Main",
        flagged_as_weak_topic=False,
        unconfirmed_prerequisites=[],
    )
    injected = build_script_generation_system_prompt(
        topic="integration by parts",
        exam_context="JEE Main",
        flagged_as_weak_topic=False,
        unconfirmed_prerequisites=["basic integration"],
    )
    assert "STEP 0 (mandatory" not in unchanged
    assert "STEP 0 (mandatory — unconfirmed prerequisites: basic integration):" in injected


def test_recall_generator_calls_provider_and_requires_new_numbers():
    provider = MagicMock()
    response = MagicMock()
    response.text = json.dumps(
        {
            "instance_description": "Evaluate integral from 0 to 2 of x sin(x) dx.",
            "solution_outline": "Use integration by parts with the new bounds 0 and 2.",
        }
    )
    response.input_tokens = 12
    response.output_tokens = 18
    response.model = "test-model"
    provider.name = "anthropic"
    provider.generate.return_value = response

    recall, cost = generate_recall_instance(
        provider=provider,
        topic="integration by parts",
        main_instance="[0-5] ON SCREEN: Evaluate integral from 0 to 1 of x sin(x) dx.",
        model="test-model",
        db=None,
        job_id=None,
        cost_breakdown={},
    )

    assert provider.generate.call_count == 1
    assert recall["instance_description"].startswith("Evaluate integral")
    main_numbers = recall_numeric_tokens("[0-5] ON SCREEN: Evaluate integral from 0 to 1 of x sin(x) dx.")
    recall_numbers = recall_numeric_tokens(recall["instance_description"] + " " + recall["solution_outline"])
    assert recall_numbers != main_numbers
    assert isinstance(cost, float)


def test_storyboard_script_stores_main_and_recall_instances():
    from app import pipeline

    storyboard = (
        "# Approach: concrete example first\n"
        "[0-4] ON SCREEN: Taylor series example at x=0 with f(x)=1+x | VO: \"Start with x zero.\"\n"
        "[4-8] ON SCREEN: Compare the first two polynomial terms | VO: \"Notice the terms.\"\n"
        f"[8-12] ON SCREEN: {RECALL_CHECKPOINT_TAG} Pause and try this: a new instance at x=2 with f(x)=1+2x | VO: \"Try the new instance.\"\n"
        "[12-16] ON SCREEN: Reveal the polynomial solution for x=2 | VO: \"Now compare your result.\""
    )
    first = SimpleNamespace(text=storyboard, input_tokens=10, output_tokens=20, model="test-model")
    second = SimpleNamespace(
        text=json.dumps(
            {
                "instance_description": "Taylor series at x=3 with f(x)=1+3x.",
                "solution_outline": "Substitute x=3 into the new Taylor series instance.",
            }
        ),
        input_tokens=8,
        output_tokens=12,
        model="test-model",
    )
    provider = MagicMock(name="anthropic")
    provider.name = "anthropic"
    provider.generate.side_effect = [first, second]

    draft = pipeline.generate_storyboard_draft("Taylor series", 30, "JEE aspirants", provider=provider)

    assert draft["main_instance"]
    assert draft["recall_instance"]["instance_description"]
    assert recall_numeric_tokens(draft["main_instance"]) != recall_numeric_tokens(
        draft["recall_instance"]["instance_description"]
    )
    assert draft["recall_question"]["question_id"].startswith("recall-")
    assert provider.generate.call_count == 2


def test_incorrect_recall_response_persists_and_schedules_once():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    video_id = "video-recall-test"
    question_id = "recall-question-1"
    db = TestingSession()
    db.add(
        Job(
            id=video_id,
            status=JobStatus.complete,
            request_payload={
                "recall_question": {
                    "question_id": question_id,
                    "answer": "Use integration by parts with bounds 0 and 2.",
                }
            },
        )
    )
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        with patch("app.main.queue_recall_followup") as queue_followup:
            response = client.post(
                f"/videos/{video_id}/recall-response",
                json={
                    "student_id": "student-1",
                    "question_id": question_id,
                    "answer_given": "wrong answer",
                },
            )
            assert response.status_code == 200
            assert response.json() == {"correct": False}
            queue_followup.assert_called_once_with(video_id, "student-1")

        check_db = TestingSession()
        saved = check_db.query(RecallResponseRecord).one()
        assert saved.video_id == video_id
        assert saved.student_id == "student-1"
        assert saved.correct is False
        check_db.close()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_recall_followup_is_scheduled_for_24_hours_later():
    from app import rq_queue

    queue = MagicMock()
    queue.enqueue_at.return_value.id = "scheduled-recall-job"
    before = datetime.now(timezone.utc)
    with patch("app.rq_queue.generation_queue", return_value=queue):
        job_id = rq_queue.queue_recall_followup("video-1", "student-1")

    scheduled_at = queue.enqueue_at.call_args.args[0]
    delay_seconds = (scheduled_at - before).total_seconds()
    assert 86_399 <= delay_seconds <= 86_401
    assert job_id == "scheduled-recall-job"
