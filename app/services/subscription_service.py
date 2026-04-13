"""
Subscription Service
=====================
All subscription business logic lives here.
The router calls these functions — no business logic in routes.

Key responsibilities:
  - Provision free plan on user registration
  - Check quota before any chargeable action
  - Record usage after successful action
  - Activate/upgrade subscription after payment
  - Handle period resets (monthly rollover)
  - Return usage status for the dashboard
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import HTTPException, status

from app.core.logging import get_logger

log = get_logger(__name__)

# ── Plan definitions (mirrors DB, used for in-memory checks) ──────────────────
PLANS = {
    "free":  {"name": "Starter", "price_inr": 0,   "analyses_per_month": 3,  "features": {"opportunities": False, "career_path": False, "history_days": 0,    "mock_interview": False, "diff_view": False}},
    "basic": {"name": "Basic",   "price_inr": 49,  "analyses_per_month": 15, "features": {"opportunities": True,  "career_path": True,  "history_days": 30,   "mock_interview": False, "diff_view": True}},
    "pro":   {"name": "Pro",     "price_inr": 149, "analyses_per_month": -1, "features": {"opportunities": True,  "career_path": True,  "history_days": 9999, "mock_interview": True,  "diff_view": True, "linkedin_optimizer": True}},
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _days_remaining(period_end: datetime) -> int:
    now = datetime.now(timezone.utc)
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    delta = period_end - now
    return max(0, delta.days)


def _analyses_remaining(sub: dict, plan: dict) -> int:
    limit = plan["analyses_per_month"]
    if limit == -1:
        return -1
    return max(0, limit - sub["analyses_used_this_period"])


def _build_subscription_out(sub: dict, plan: dict) -> dict:
    remaining = _analyses_remaining(sub, plan)
    return {
        "id": str(sub["id"]),
        "user_id": str(sub["user_id"]),
        "plan_id": sub["plan_id"],
        "plan": {
            "id": plan["analyses_per_month"],
            "name": plan["name"],
            "price_inr": plan["price_inr"],
            "analyses_per_month": plan["analyses_per_month"],
            "features": plan["features"],
        },
        "status": sub["status"],
        "current_period_start": sub["current_period_start"],
        "current_period_end": sub["current_period_end"],
        "analyses_used_this_period": sub["analyses_used_this_period"],
        "analyses_remaining": remaining,
        "is_active": sub["status"] == "active",
        "days_remaining": _days_remaining(sub["current_period_end"]),
    }


# ── Public service functions ──────────────────────────────────────────────────

async def provision_free_plan(user_id: str, db) -> None:
    """
    Called at user registration. Gives every new user the free plan.
    Idempotent — safe to call multiple times.
    """
    existing = await db.fetchrow(
        "SELECT id FROM subscriptions WHERE user_id = $1", user_id
    )
    if existing:
        return

    period_end = datetime.now(timezone.utc) + timedelta(days=30)
    await db.execute(
        """
        INSERT INTO subscriptions (user_id, plan_id, status, current_period_end)
        VALUES ($1, 'free', 'active', $2)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id, period_end,
    )
    log.info("free_plan_provisioned", user_id=user_id)


async def get_subscription(user_id: str, db) -> dict:
    """Fetch the user's current subscription with plan details."""
    sub = await db.fetchrow(
        """
        SELECT s.*, p.name as plan_name, p.price_inr, p.analyses_per_month, p.features
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = $1
        """,
        user_id,
    )
    if not sub:
        # Auto-provision if somehow missing (safety net)
        await provision_free_plan(user_id, db)
        return await get_subscription(user_id, db)

    sub = dict(sub)

    # Check if period has expired and reset it
    period_end = sub["current_period_end"]
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)

    if period_end < datetime.now(timezone.utc) and sub["plan_id"] == "free":
        # Free plan resets automatically every 30 days
        new_start = datetime.now(timezone.utc)
        new_end   = new_start + timedelta(days=30)
        await db.execute(
            """
            UPDATE subscriptions
            SET current_period_start = $1,
                current_period_end   = $2,
                analyses_used_this_period = 0,
                updated_at = NOW()
            WHERE user_id = $3
            """,
            new_start, new_end, user_id,
        )
        sub["current_period_start"] = new_start
        sub["current_period_end"]   = new_end
        sub["analyses_used_this_period"] = 0

    return sub


async def get_usage_status(user_id: str, db) -> dict:
    """
    Returns everything the frontend needs to display the usage meter
    and decide whether to show the upgrade prompt.
    """
    sub  = await get_subscription(user_id, db)
    plan = PLANS.get(sub["plan_id"], PLANS["free"])

    limit     = plan["analyses_per_month"]
    used      = sub["analyses_used_this_period"]
    remaining = _analyses_remaining(sub, plan)
    can_analyse = (limit == -1) or (used < limit)
    upgrade_required = not can_analyse

    if upgrade_required:
        upgrade_message = (
            f"You've used all {limit} analyses this month. "
            f"Upgrade to Basic (₹49/mo) for 15 analyses or Pro (₹149/mo) for unlimited."
        )
    elif limit != -1 and used >= max(1, limit - 1):
        upgrade_message = f"Only {remaining} analysis left this month. Consider upgrading."
    else:
        upgrade_message = ""

    return {
        "plan_id": sub["plan_id"],
        "plan_name": plan["name"],
        "analyses_used": used,
        "analyses_limit": limit,
        "analyses_remaining": remaining,
        "period_end": sub["current_period_end"],
        "days_remaining": _days_remaining(sub["current_period_end"]),
        "can_analyse": can_analyse,
        "features": plan["features"],
        "upgrade_required": upgrade_required,
        "upgrade_message": upgrade_message,
    }


async def check_quota(user_id: str, event_type: str, db) -> None:
    """
    Gate function — call this BEFORE any chargeable action.
    Raises HTTP 402 if the user is over quota.
    """
    sub  = await get_subscription(user_id, db)
    plan = PLANS.get(sub["plan_id"], PLANS["free"])

    # Check analysis quota
    if event_type == "analysis":
        limit = plan["analyses_per_month"]
        used  = sub["analyses_used_this_period"]
        if limit != -1 and used >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "message": f"You've used all {limit} analyses this month.",
                    "used": used,
                    "limit": limit,
                    "upgrade_url": "/pricing",
                    "plans": {
                        "basic": {"name": "Basic", "price_inr": 49,  "analyses": 15},
                        "pro":   {"name": "Pro",   "price_inr": 149, "analyses": "unlimited"},
                    },
                },
            )

    # Check feature flags
    features = plan["features"]
    feature_gates = {
        "opportunity":  "opportunities",
        "career_path":  "career_path",
        "mock_interview": "mock_interview",
        "linkedin":     "linkedin_optimizer",
    }
    if event_type in feature_gates:
        flag = feature_gates[event_type]
        if not features.get(flag, False):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "FEATURE_LOCKED",
                    "message": f"This feature requires a paid plan.",
                    "feature": event_type,
                    "upgrade_url": "/pricing",
                },
            )


async def record_usage(user_id: str, event_type: str, analysis_id: Optional[str], db) -> None:
    """
    Record a usage event and increment the counter.
    Call this AFTER the action succeeds.
    """
    # Only count analyses against the monthly quota (not plans/career paths)
    if event_type == "analysis":
        await db.execute(
            """
            UPDATE subscriptions
            SET analyses_used_this_period = analyses_used_this_period + 1,
                updated_at = NOW()
            WHERE user_id = $1
            """,
            user_id,
        )

    # Always log the event for billing audit
    await db.execute(
        """
        INSERT INTO usage_events (user_id, event_type, analysis_id)
        VALUES ($1, $2, $3)
        """,
        user_id, event_type, analysis_id,
    )


async def activate_subscription(
    user_id: str,
    plan_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    db,
) -> dict:
    """
    Called after webhook verifies a successful payment.
    Upgrades the user's plan and resets the period.
    """
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")

    now       = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)

    await db.execute(
        """
        UPDATE subscriptions SET
            plan_id                    = $1,
            status                     = 'active',
            current_period_start       = $2,
            current_period_end         = $3,
            analyses_used_this_period  = 0,
            razorpay_subscription_id   = $4,
            updated_at                 = NOW()
        WHERE user_id = $5
        """,
        plan_id, now, period_end, razorpay_order_id, user_id,
    )

    log.info("subscription_activated", user_id=user_id, plan_id=plan_id, order_id=razorpay_order_id)

    return await get_subscription(user_id, db)


async def cancel_subscription(user_id: str, db) -> None:
    """Downgrade to free at end of period (not immediate)."""
    await db.execute(
        """
        UPDATE subscriptions
        SET status = 'cancelled', updated_at = NOW()
        WHERE user_id = $1
        """,
        user_id,
    )
    log.info("subscription_cancelled", user_id=user_id)
