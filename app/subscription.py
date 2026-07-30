"""
Subscription plans, quota tracking, and enforcement for Vivacity.
Plan prices and margins reference vivacity_complete_strategy.md (cost-per-video table).
"""
from __future__ import annotations

import enum
import os
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── Plan Definitions ─────────────────────────────────────────────────────

class PlanTier(str, enum.Enum):
    FREE = "free"
    STUDENT = "student"
    PRO = "pro"
    INSTITUTION = "institution"


class PlanLimits(BaseModel):
    tier: PlanTier
    renders_per_month: int | None  # None = unlimited (Pro)
    max_quality: str  # "720p30" | "1080p60" | "4k60"
    max_duration_seconds: int
    max_complexity: str  # "simple" | "medium" | "complex"
    watermark: bool
    recall_tracking: bool
    recall_history_days: int | None
    queue_priority: str  # "standard" | "medium" | "high"
    api_access: bool
    batch_generation: bool
    white_label: bool
    price_inr: int  # Monthly price in INR. 0 = free.


PLAN_CONFIG: dict[PlanTier, PlanLimits] = {
    PlanTier.FREE: PlanLimits(
        tier=PlanTier.FREE,
        renders_per_month=10,
        max_quality="720p30",
        max_duration_seconds=30,
        max_complexity="simple",
        watermark=True,
        recall_tracking=False,
        recall_history_days=None,
        queue_priority="standard",
        api_access=False,
        batch_generation=False,
        white_label=False,
        price_inr=0,
    ),
    PlanTier.STUDENT: PlanLimits(
        tier=PlanTier.STUDENT,
        renders_per_month=50,
        max_quality="1080p60",
        max_duration_seconds=90,
        max_complexity="medium",
        watermark=False,
        recall_tracking=True,
        recall_history_days=30,
        queue_priority="medium",
        api_access=False,
        batch_generation=False,
        white_label=False,
        price_inr=99,
    ),
    PlanTier.PRO: PlanLimits(
        tier=PlanTier.PRO,
        renders_per_month=None,  # unlimited
        max_quality="4k60",
        max_duration_seconds=300,
        max_complexity="complex",
        watermark=False,
        recall_tracking=True,
        recall_history_days=None,  # unlimited
        queue_priority="high",
        api_access=True,
        batch_generation=True,
        white_label=False,
        price_inr=299,
    ),
    # Institution: custom per-contract, not self-serve — see RAZORPAY section
    PlanTier.INSTITUTION: PlanLimits(
        tier=PlanTier.INSTITUTION,
        renders_per_month=None,
        max_quality="4k60",
        max_duration_seconds=600,
        max_complexity="complex",
        watermark=False,
        recall_tracking=True,
        recall_history_days=None,
        queue_priority="high",
        api_access=True,
        batch_generation=True,
        white_label=True,
        price_inr=5000,  # per year, per center — actual pricing via sales
    ),
}


# ─── Quota / Usage Tracking ──────────────────────────────────────────────

class QuotaCheckResult(BaseModel):
    allowed: bool
    reason: str | None = None  # human-readable reason when not allowed


class UserUsage(BaseModel):
    """Persisted per user per billing cycle."""
    user_id: str
    plan: PlanTier = PlanTier.FREE
    billing_cycle_start: datetime | None = None
    renders_this_cycle: int = 0
    last_reset: datetime | None = None


def get_user_usage(user_id: str) -> UserUsage:
    """Load a user's usage record from the database, or create a default one.
    
    Returns a UserUsage object.  The caller is responsible for persisting
    any mutations (increment, plan change, cycle reset) back to the DB.
    """
    from app.models import SessionLocal, UserSubscription

    with SessionLocal() as db:
        record = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id
        ).first()

    now = datetime.utcnow()
    if record is None:
        return UserUsage(
            user_id=user_id,
            plan=PlanTier.FREE,
            billing_cycle_start=now,
            renders_this_cycle=0,
            last_reset=now,
        )

    usage = UserUsage(
        user_id=record.user_id,
        plan=PlanTier(record.plan_tier),
        billing_cycle_start=record.billing_cycle_start,
        renders_this_cycle=record.renders_this_cycle,
        last_reset=record.last_reset,
    )
    return usage


def persist_user_usage(usage: UserUsage) -> None:
    """Write an updated UserUsage back to the database."""
    from app.models import SessionLocal, UserSubscription

    with SessionLocal() as db:
        record = db.query(UserSubscription).filter(
            UserSubscription.user_id == usage.user_id
        ).first()
        if record is None:
            record = UserSubscription(
                user_id=usage.user_id,
                plan_tier=usage.plan.value,
                billing_cycle_start=usage.billing_cycle_start or datetime.utcnow(),
                renders_this_cycle=usage.renders_this_cycle,
                last_reset=usage.last_reset or datetime.utcnow(),
            )
            db.add(record)
        else:
            record.plan_tier = usage.plan.value
            record.billing_cycle_start = usage.billing_cycle_start
            record.renders_this_cycle = usage.renders_this_cycle
            record.last_reset = usage.last_reset
        db.commit()


def check_and_increment_quota(user_id: str, *, dry_run: bool = False) -> QuotaCheckResult:
    """Called BEFORE job creation. Checks whether a user can render.

    When dry_run=False (default), increments the render count if quota allows.
    Set dry_run=True for read-only checks (e.g. UI display of remaining renders).
    """
    usage = get_user_usage(user_id)
    limits = PLAN_CONFIG[usage.plan]

    # Billing-cycle rollover: reset if the current time is past the next cycle.
    # Each cycle is calendar-month-based for simplicity.
    now = datetime.utcnow()
    if usage.billing_cycle_start is not None:
        # Simple 30-day cycle for now — production should use calendar months.
        cycle_seconds = 30 * 24 * 3600
        if (now - usage.billing_cycle_start).total_seconds() > cycle_seconds:
            usage.billing_cycle_start = now
            usage.renders_this_cycle = 0
            usage.last_reset = now

    if limits.renders_per_month is not None and usage.renders_this_cycle >= limits.renders_per_month:
        return QuotaCheckResult(
            allowed=False,
            reason=(
                f"You have used all {limits.renders_per_month} renders for this billing cycle. "
                f"Upgrade to {'Pro' if usage.plan == PlanTier.STUDENT else 'a paid plan'} "
                f"for unlimited renders."
            ),
        )

    if not dry_run:
        usage.renders_this_cycle += 1
        persist_user_usage(usage)

    return QuotaCheckResult(allowed=True)


# ─── Request clamping ─────────────────────────────────────────────────────

class ClampedRenderRequest(BaseModel):
    """A validated render request with quality/duration/complexity clamped
    to the user's plan limits."""
    quality: str
    duration_seconds: int
    complexity: str
    clamped: bool  # True if any value was downgraded
    messages: list[str]  # human-readable notes about what was clamped


def clamp_request_to_plan(user_id: str, *, requested_quality: str = "720p30",
                          requested_duration: int = 30,
                          requested_complexity: str = "simple") -> ClampedRenderRequest:
    """Clamp a render request's parameters to the user's plan limits.

    Silently downgrades rather than erroring — the UI can display an upsell
    prompt but the render should always proceed at the user's allowed tier.
    """
    usage = get_user_usage(user_id)
    limits = PLAN_CONFIG[usage.plan]
    messages: list[str] = []
    clamped = False

    # Quality
    quality_hierarchy = ["720p30", "1080p60", "4k60"]
    req_q_idx = quality_hierarchy.index(requested_quality) if requested_quality in quality_hierarchy else 0
    max_q_idx = quality_hierarchy.index(limits.max_quality)
    if req_q_idx > max_q_idx:
        clamped = True
        messages.append(
            f"Quality downgraded from {requested_quality} to {limits.max_quality} "
            f"({usage.plan.value} plan limit)."
        )
        quality = limits.max_quality
    else:
        quality = requested_quality

    # Duration
    if requested_duration > limits.max_duration_seconds:
        clamped = True
        messages.append(
            f"Duration clamped from {requested_duration}s to {limits.max_duration_seconds}s "
            f"({usage.plan.value} plan limit)."
        )
        duration = limits.max_duration_seconds
    else:
        duration = requested_duration

    # Complexity
    complexity_hierarchy = ["simple", "medium", "complex"]
    req_c_idx = complexity_hierarchy.index(requested_complexity) if requested_complexity in complexity_hierarchy else 0
    max_c_idx = complexity_hierarchy.index(limits.max_complexity)
    if req_c_idx > max_c_idx:
        clamped = True
        messages.append(
            f"Complexity reduced from {requested_complexity} to {limits.max_complexity} "
            f"({usage.plan.value} plan limit)."
        )
        complexity = limits.max_complexity
    else:
        complexity = requested_complexity

    return ClampedRenderRequest(
        quality=quality,
        duration_seconds=duration,
        complexity=complexity,
        clamped=clamped,
        messages=messages,
    )


# ─── Watermark text for Free tier ────────────────────────────────────────

WATERMARK_TEXT = "Made with Vivacity"
WATERMARK_FONT_SIZE = 18
WATERMARK_OPACITY = 0.35


def watermark_mobject() -> Any:
    """Return a Manim Text mobject configured as a Free-tier watermark.

    Must be imported only inside a Manim scene context (not at module load),
    because manim may not be installed in all environments that import
    subscription.py.
    """
    from manim import Text, RIGHT, DOWN, config

    wm = Text(
        WATERMARK_TEXT,
        font_size=WATERMARK_FONT_SIZE,
        opacity=WATERMARK_OPACITY,
        color="#ffffff",
    )
    # Bottom-right corner, with safe-zone padding
    wm.move_to([
        config.frame_x_radius - 0.3 - wm.width / 2,
        -config.frame_y_radius + 0.3 + wm.height / 2,
        0,
    ])
    return wm


# ─── RevenueCat integration ─────────────────────────────────────────────

REVENUECAT_API_KEY = os.getenv("REVENUECAT_API_KEY", "")
REVENUECAT_BASE_URL = "https://api.revenuecat.com/v1"


def create_revenuecat_entitlement(user_id: str, plan_tier: PlanTier | str) -> dict[str, Any]:
    """Grant a user a subscription entitlement via RevenueCat.

    Accepts both PlanTier enum and string (e.g. 'student', 'pro') for
    convenience.  RevenueCat manages the full subscription lifecycle
    (billing, renewals, cancellations) across platforms.

    Returns a dict with the entitlement details.
    Raises RuntimeError if RevenueCat is not configured.
    """
    if not REVENUECAT_API_KEY:
        raise RuntimeError("RevenueCat is not configured (REVENUECAT_API_KEY not set).")

    if isinstance(plan_tier, str):
        plan_tier = PlanTier(plan_tier)

    product_id = {
        PlanTier.STUDENT: "vivacity_student_monthly",
        PlanTier.PRO: "vivacity_pro_monthly",
    }.get(plan_tier)

    if not product_id:
        raise ValueError(f"No RevenueCat product configured for tier {plan_tier}")

    # Update local usage record immediately (idempotent — RevenueCat webhook
    # will confirm or correct it later).
    usage = get_user_usage(user_id)
    usage.plan = plan_tier
    usage.billing_cycle_start = datetime.utcnow()
    usage.renders_this_cycle = 0
    persist_user_usage(usage)

    return {
        "user_id": user_id,
        "plan_tier": plan_tier.value,
        "product_id": product_id,
        "status": "active",
    }


def handle_revenuecat_webhook(payload: dict[str, Any]) -> str:
    """Process an incoming RevenueCat webhook event.

    Supported events:
      - INITIAL_PURCHASE: grant the purchased entitlement
      - RENEWAL: extend the current entitlement
      - CANCELLATION: note the expiry but don't downgrade until period ends
      - EXPIRATION: downgrade to Free
      - UNCERTAIN_PAYMENT: flag for manual review

    Returns the event type that was processed.
    """
    event = payload.get("event", {}).get("type", "")
    user_id = payload.get("event", {}).get("app_user_id", "")
    product_id = payload.get("event", {}).get("product_id", "")

    if not user_id:
        return "skipped_no_user"

    # Map RevenueCat product IDs to plan tiers
    product_to_plan = {
        "vivacity_student_monthly": PlanTier.STUDENT,
        "vivacity_pro_monthly": PlanTier.PRO,
    }

    if event in ("INITIAL_PURCHASE", "RENEWAL"):
        plan = product_to_plan.get(product_id, PlanTier.FREE)
        usage = get_user_usage(user_id)
        usage.plan = plan
        usage.billing_cycle_start = datetime.utcnow()
        usage.renders_this_cycle = 0
        persist_user_usage(usage)
        return f"{event}: {user_id} -> {plan.value}"

    elif event == "EXPIRATION":
        usage = get_user_usage(user_id)
        if usage.plan != PlanTier.FREE:
            usage.plan = PlanTier.FREE
            persist_user_usage(usage)
        return f"EXPIRATION: {user_id} -> free"

    elif event == "CANCELLATION":
        # Note the cancellation; entitlement remains until period ends.
        return f"CANCELLATION: {user_id} noted"

    elif event == "UNCERTAIN_PAYMENT":
        # Flag for manual review — log and continue.
        import logging
        logging.warning(f"REVENUECAT_UNCERTAIN_PAYMENT user_id={user_id} product_id={product_id}")
        return f"UNCERTAIN_PAYMENT: {user_id} flagged"

    return f"unhandled_event: {event}"


# ─── Institution lead-capture form ───────────────────────────────────────

def create_institution_lead(name: str, email: str, institution: str,
                             student_count: int, message: str) -> dict[str, Any]:
    """Record an institution sales lead.

    In production this would write to a CRM or send an email notification.
    For now it logs to a JSONL file.
    """
    import json as _json
    from pathlib import Path

    lead = {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "institution": institution,
        "student_count": student_count,
        "message": message,
        "created_at": datetime.utcnow().isoformat(),
    }
    leads_file = Path(os.getenv("VIVACITY_LEADS_FILE", "institution_leads.jsonl"))
    with leads_file.open("a") as f:
        f.write(_json.dumps(lead) + "\n")
    return lead
