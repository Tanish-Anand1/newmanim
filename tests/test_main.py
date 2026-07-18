from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.main as main
from app.models import Base, Job, JobStatus, SessionLocal, init_db


def test_health_live():
    client = TestClient(main.app)
    assert client.get("/health/live").json() == {"status": "ok"}


def test_openai_tts_uses_the_hd_default_when_creating_jobs():
    assert main.configured_tts_model("openai") == "tts-1-hd"
    assert main.configured_tts_model("silent") is None


def test_batch_creation_collapses_equivalent_requests(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'batch.db'}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    storyboard = '[0-3] ON SCREEN: Show the definition | VO: "Define it."'
    requests = [
        main.GenerateRequest(storyboard=storyboard, scene_name="FirstScene"),
        main.GenerateRequest(storyboard=storyboard, scene_name="SecondScene"),
    ]
    with session_local() as db:
        results = main.create_generation_jobs_batch(requests, db)
        assert db.scalar(select(func.count(Job.id))) == 1

    assert results[0][0].id == results[1][0].id
    assert results[0][1] is False
    assert results[1][1] is True


def test_direct_storyboard_uses_topic_header_for_positive_content_gate():
    topic = "VSEPR using NH3 and CH4 with bond angles 109.5 and 107 degrees"
    generic_request = main.GenerateRequest(
        storyboard=(
            f"# Topic: {topic}\n"
            '[0-5] ON SCREEN: Molecular structure | VO: "Observe the core idea."'
        ),
        scene_name="VSEPRScene",
    )
    try:
        main.validate_generate_request(generic_request)
    except ValueError as exc:
        assert "topic-term coverage" in str(exc)
    else:
        raise AssertionError("Expected a direct storyboard missing its declared topic entities to fail")

    specific_request = main.GenerateRequest(
        storyboard=(
            f"# Topic: {topic}\n"
            '[0-5] ON SCREEN: VSEPR models of NH3 and CH4 | VO: "Compare their bond angles."\n'
            '[5-10] ON SCREEN: Mark 109.5° and 107° | VO: "A lone pair compresses the ammonia angle."'
        ),
        scene_name="VSEPRScene",
    )
    main.validate_generate_request(specific_request)


def test_direct_storyboard_does_not_treat_scene_name_as_topic():
    request = main.GenerateRequest(
        storyboard=(
            '[0-6] ON SCREEN: Define \\(I=\\int_{0}^{\\pi}x\\sin x\\,dx\\) for integration by parts. '
            '| VO: "Let I be the integral from zero to pi of x sine x."\n'
            '[6-12] ON SCREEN: Choose \\(u=x\\), \\(dv=\\sin x\\,dx\\), \\(du=dx\\), and \\(v=-\\cos x\\). '
            '| VO: "Choose u equals x and integrate dv to get negative cosine x."\n'
            '[12-18] ON SCREEN: Substitute into \\(I=uv-\\int v\\,du\\) and simplify the boundary terms. '
            '| VO: "Substitute these choices, then evaluate the boundary contribution and remaining cosine integral."\n'
            '[18-24] ON SCREEN: Conclude \\(I=\\pi\\) after both definite terms are evaluated. '
            '| VO: "The cosine integral vanishes, leaving the exact result I equals pi."'
        ),
        scene_name="IntegrationByPartsRenderGuard",
    )

    main.validate_generate_request(request)


def test_generate_accepts_topic_request(monkeypatch):
    init_db()
    calls = []

    def fake_topic_pipeline(*args):
        calls.append(args)

    monkeypatch.setattr(main, "run_topic_pipeline_for_job", fake_topic_pipeline)
    monkeypatch.setattr(main, "execution_mode", lambda: "inline")
    client = TestClient(main.app)

    response = client.post(
        "/api/generate",
        json={
            "topic": "Taylor series expansion of sin(x)",
            "duration_seconds": 60,
            "audience": "JEE aspirants",
            "scene_name": "TaylorSeriesScene",
            "orientation": "landscape",
            "reuse_existing": False,
        },
    )

    assert response.status_code == 200
    assert calls
    job_id = response.json()["job_id"]
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        assert job is not None
        assert job.storyboard is None
        assert job.generated_storyboard is None
        assert job.orientation == "landscape"
    finally:
        db.close()


def test_generate_rejects_storyboard_and_topic_together():
    client = TestClient(main.app)

    response = client.post(
        "/api/generate",
        json={
            "storyboard": '[0-3] ON SCREEN: Title | VO: "Hello"',
            "topic": "Taylor series",
            "duration_seconds": 30,
            "audience": "JEE aspirants",
            "scene_name": "TaylorSeriesScene",
        },
    )

    assert response.status_code == 422


def test_public_job_response_hides_generated_storyboard():
    init_db()
    db = SessionLocal()
    try:
        job = Job(
            scene_name="AuditScene",
            storyboard='[0-3] ON SCREEN: Title | VO: "Hello"',
            generated_storyboard='[0-3] ON SCREEN: Title | VO: "Hello"',
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = TestClient(main.app).get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    assert "generated_storyboard" not in response.json()
    assert "error" not in response.json()


def test_internal_job_response_includes_generated_storyboard(monkeypatch):
    init_db()
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    db = SessionLocal()
    try:
        job = Job(
            scene_name="AuditScene",
            storyboard='[0-3] ON SCREEN: Title | VO: "Hello"',
            generated_storyboard='[0-3] ON SCREEN: Title | VO: "Hello"',
            quality_scores=[{"accuracy": 5, "depth": 4, "logical_flow": 5, "visual_relevance": 5, "element_layout": 5}],
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = TestClient(main.app).get(f"/api/internal/jobs/{job_id}", headers={"x-admin-token": "admin-test"})

    assert response.status_code == 200
    assert response.json()["generated_storyboard"].startswith("[0-3]")
    assert response.json()["quality_scores"][0]["accuracy"] == 5


def test_internal_job_response_preserves_unicode_storyboard(monkeypatch):
    init_db()
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    storyboard = '# Approach: symbols\n[0-4] ON SCREEN: θ, Σ, 90°, — | VO: "θ and Σ."'
    db = SessionLocal()
    try:
        job = Job(scene_name="UnicodeScene", storyboard=storyboard, generated_storyboard=storyboard)
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = TestClient(main.app).get(f"/api/internal/jobs/{job_id}", headers={"x-admin-token": "admin-test"})

    assert response.status_code == 200
    assert response.json()["generated_storyboard"] == storyboard
    assert "θ" in response.content.decode("utf-8")


def test_internal_job_response_requires_admin_token(monkeypatch):
    init_db()
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    db = SessionLocal()
    try:
        job = Job(scene_name="AuditScene")
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = TestClient(main.app).get(f"/api/internal/jobs/{job_id}")

    assert response.status_code == 401
def test_public_job_payload_uses_persisted_rendered_beat_windows():
    job = Job(
        status=JobStatus.complete,
        storyboard=(
            '[0-5] ON SCREEN: First | VO: "One"\n'
            '[5-10] ON SCREEN: Second | VO: "Two"'
        ),
        request_payload={
            "rendered_duration_seconds": 11.5,
            "rendered_beat_windows": [
                {"beat_number": 1, "start": 0.0, "end": 6.0},
                {"beat_number": 2, "start": 6.5, "end": 11.5},
            ],
        },
    )

    payload = main.public_job_to_dict(job)

    assert payload["duration_seconds"] == 11.5
    assert payload["beats"] == [
        {"beat_number": 1, "start": 0.0, "end": 6.0, "on_screen": "First", "vo_text": "One"},
        {"beat_number": 2, "start": 6.5, "end": 11.5, "on_screen": "Second", "vo_text": "Two"},
    ]
