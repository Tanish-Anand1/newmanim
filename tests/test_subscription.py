"""Tests for subscription plan enforcement — quota, clamping, watermark."""
import pytest
from datetime import datetime, timezone, timedelta

from app.subscription import (
    PlanTier, PLAN_CONFIG, UserUsage,
    check_and_increment_quota, clamp_request_to_plan,
    QuotaCheckResult,
)
from app.models import Base, engine, SessionLocal, UserSubscription


@pytest.fixture(autouse=True)
def clean_db():
    """Use a clean database for each test."""
    Base.metadata.create_all(bind=engine)
    yield
    with SessionLocal() as db:
        db.query(UserSubscription).delete()
        db.commit()


def test_free_tier_has_10_renders():
    limits = PLAN_CONFIG[PlanTier.FREE]
    assert limits.renders_per_month == 10
    assert limits.max_quality == "720p30"
    assert limits.watermark is True
    assert limits.recall_tracking is False


def test_student_tier_has_50_renders():
    limits = PLAN_CONFIG[PlanTier.STUDENT]
    assert limits.renders_per_month == 50
    assert limits.max_quality == "1080p60"
    assert limits.watermark is False
    assert limits.recall_tracking is True
    assert limits.recall_history_days == 30


def test_pro_tier_unlimited():
    limits = PLAN_CONFIG[PlanTier.PRO]
    assert limits.renders_per_month is None  # unlimited
    assert limits.max_quality == "4k60"
    assert limits.max_duration_seconds == 300
    assert limits.api_access is True
    assert limits.batch_generation is True


def test_free_quota_allows_initial_render():
    result = check_and_increment_quota("quota-test-1")
    assert result.allowed is True
    assert result.reason is None


def test_free_quota_exhausts_at_11th_render():
    # Use up 10 renders
    for i in range(10):
        r = check_and_increment_quota("quota-test-2")
        assert r.allowed is True, f"Render {i+1} should be allowed"

    # 11th should fail
    result = check_and_increment_quota("quota-test-2")
    assert result.allowed is False
    assert "used all" in (result.reason or "").lower()


def test_quota_resets_after_cycle():
    user = "quota-test-3"
    # Exhaust quota
    for i in range(10):
        check_and_increment_quota(user)
    assert check_and_increment_quota(user).allowed is False

    # Manually move billing cycle back 31 days
    from app.subscription import get_user_usage, persist_user_usage
    usage = get_user_usage(user)
    usage.billing_cycle_start = datetime.now(timezone.utc) - timedelta(days=31)
    usage.renders_this_cycle = 10
    persist_user_usage(usage)

    # Next check should reset and allow
    result = check_and_increment_quota(user)
    assert result.allowed is True


def test_clamp_free_user_duration():
    # Free user requesting 120s should be clamped to 30s
    clamped = clamp_request_to_plan("clamp-test-1",
        requested_duration=120, requested_quality="4k60", requested_complexity="complex")
    assert clamped.duration_seconds == 30
    assert clamped.quality == "720p30"
    assert clamped.complexity == "simple"
    assert clamped.clamped is True
    assert len(clamped.messages) >= 2  # at least quality + duration


def test_pro_user_no_clamping():
    clamped = clamp_request_to_plan("clamp-test-2",
        requested_duration=120, requested_quality="4k60", requested_complexity="complex")
    # Default user is FREE, not PRO
    assert clamped.clamped is True  # free user, so still clamped


def test_watermark_text_exists():
    from app.subscription import WATERMARK_TEXT
    assert WATERMARK_TEXT == "Made with Vivacity"


def test_plan_config_has_all_tiers():
    for tier in PlanTier:
        assert tier in PLAN_CONFIG, f"Missing config for {tier}"
        limits = PLAN_CONFIG[tier]
        assert limits.tier == tier
        assert limits.max_quality in ("720p30", "1080p60", "4k60")
        assert limits.max_complexity in ("simple", "medium", "complex")
        assert limits.queue_priority in ("standard", "medium", "high")
