"""
Billing Router
===============
Routes:
  GET  /billing/plans              — all plans with features
  GET  /billing/my-subscription    — current user's subscription + usage
  GET  /billing/usage              — quick usage status (for dashboard header)
  POST /billing/create-order       — create Razorpay order (Step 1 of checkout)
  POST /billing/verify-payment     — verify signature + activate (Step 2)
  POST /billing/webhook            — Razorpay webhook (server-to-server)
  POST /billing/cancel             — cancel subscription (downgrades to free at period end)
  GET  /billing/history            — payment history for user
"""
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.connection import get_db
from app.core.logging import get_logger
from app.models.subscription import (
    CreateOrderRequest, CreateOrderResponse,
    VerifyPaymentRequest, VerifyPaymentResponse,
    UsageStatus,
)
from app.services import subscription_service, razorpay_service

log = get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

PLANS = subscription_service.PLANS


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans():
    """Return all available plans. No auth required — used on the pricing page."""
    return {
        "plans": [
            {
                "id": plan_id,
                "name": plan["name"],
                "price_inr": plan["price_inr"],
                "analyses_per_month": plan["analyses_per_month"],
                "features": plan["features"],
                "is_popular": plan_id == "basic",
            }
            for plan_id, plan in PLANS.items()
        ]
    }


# ── Current subscription ───────────────────────────────────────────────────────

@router.get("/my-subscription")
async def get_my_subscription(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Full subscription details for the account settings page."""
    sub = await subscription_service.get_subscription(str(current_user["id"]), db)
    plan = PLANS.get(sub["plan_id"], PLANS["free"])

    remaining = subscription_service._analyses_remaining(sub, plan)

    return {
        "plan_id": sub["plan_id"],
        "plan_name": plan["name"],
        "price_inr": plan["price_inr"],
        "status": sub["status"],
        "analyses_used": sub["analyses_used_this_period"],
        "analyses_limit": plan["analyses_per_month"],
        "analyses_remaining": remaining,
        "current_period_end": sub["current_period_end"],
        "days_remaining": subscription_service._days_remaining(sub["current_period_end"]),
        "features": plan["features"],
        "is_active": sub["status"] == "active",
    }


@router.get("/usage", response_model=UsageStatus)
async def get_usage_status(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Lightweight endpoint for the dashboard header usage meter.
    Returns everything needed to render the quota bar and upgrade prompt.
    """
    return await subscription_service.get_usage_status(str(current_user["id"]), db)


# ── Checkout: Step 1 — Create order ───────────────────────────────────────────

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    request: CreateOrderRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Create a Razorpay order and return the order_id + amount to the frontend.
    The frontend then opens the Razorpay checkout modal with these details.

    Flow:
      1. Frontend calls this → gets order_id + amount
      2. Frontend opens Razorpay modal
      3. User pays
      4. Frontend calls /verify-payment with the payment details
    """
    plan = PLANS.get(request.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {request.plan_id}")
    if request.plan_id == "free":
        raise HTTPException(status_code=400, detail="Free plan does not require payment.")

    user_id = str(current_user["id"])
    receipt = str(uuid.uuid4())

    # Create payment row (status=created) for audit trail
    payment_id_row = await db.fetchrow(
        """
        INSERT INTO payments (user_id, plan_id, amount_inr, currency, status, razorpay_order_id)
        VALUES ($1, $2, $3, 'INR', 'created', $4)
        RETURNING id
        """,
        user_id, request.plan_id, plan["price_inr"], receipt,
    )

    try:
        order = await razorpay_service.create_order(
            amount_inr=plan["price_inr"],
            plan_id=request.plan_id,
            user_id=user_id,
            receipt=receipt,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {str(e)}")

    # Update payment row with real Razorpay order_id
    await db.execute(
        "UPDATE payments SET razorpay_order_id = $1 WHERE id = $2",
        order["id"], payment_id_row["id"],
    )

    return CreateOrderResponse(
        razorpay_order_id=order["id"],
        amount=plan["price_inr"] * 100,   # paise for Razorpay checkout
        currency="INR",
        plan_id=request.plan_id,
        plan_name=plan["name"],
        key_id=settings.RAZORPAY_KEY_ID,  # public key — safe to return
    )


# ── Checkout: Step 2 — Verify payment ─────────────────────────────────────────

@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    request: VerifyPaymentRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Verify the Razorpay signature and activate the subscription.

    Called by the frontend AFTER Razorpay checkout completes.
    The signature verification is the security boundary — only Razorpay
    knows the secret key, so a valid signature proves the payment is real.
    """
    user_id = str(current_user["id"])

    # CRITICAL: Verify signature before doing anything
    is_valid = razorpay_service.verify_payment_signature(
        razorpay_order_id=request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature,
    )

    if not is_valid:
        log.warning("invalid_payment_signature", user_id=user_id, order_id=request.razorpay_order_id)
        # Update payment status to failed
        await db.execute(
            "UPDATE payments SET status = 'failed', failure_reason = 'Invalid signature' WHERE razorpay_order_id = $1",
            request.razorpay_order_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. If money was deducted, contact support.",
        )

    # Signature valid — activate subscription
    try:
        updated_sub = await subscription_service.activate_subscription(
            user_id=user_id,
            plan_id=request.plan_id,
            razorpay_order_id=request.razorpay_order_id,
            razorpay_payment_id=request.razorpay_payment_id,
            db=db,
        )
    except Exception as e:
        log.error("subscription_activation_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Could not activate subscription. Contact support.")

    # Update payment record
    await db.execute(
        """
        UPDATE payments SET
            status = 'captured',
            razorpay_payment_id = $1,
            razorpay_signature = $2,
            captured_at = NOW()
        WHERE razorpay_order_id = $3
        """,
        request.razorpay_payment_id,
        request.razorpay_signature,
        request.razorpay_order_id,
    )

    plan = PLANS.get(request.plan_id, PLANS["free"])
    remaining = subscription_service._analyses_remaining(updated_sub, plan)

    return VerifyPaymentResponse(
        success=True,
        message=f"Welcome to {plan['name']}! Your subscription is now active.",
        subscription={
            "id": str(updated_sub["id"]),
            "user_id": user_id,
            "plan_id": request.plan_id,
            "status": "active",
            "current_period_start": updated_sub["current_period_start"],
            "current_period_end": updated_sub["current_period_end"],
            "analyses_used_this_period": 0,
            "analyses_remaining": remaining,
            "is_active": True,
            "days_remaining": subscription_service._days_remaining(updated_sub["current_period_end"]),
        },
    )


# ── Razorpay webhook (server-to-server backup) ────────────────────────────────

@router.post("/webhook")
async def razorpay_webhook(request: Request, db=Depends(get_db)):
    """
    Razorpay sends payment events to this endpoint directly.
    This is a backup to the /verify-payment flow — ensures activation
    even if the frontend call failed (network issues, user closed tab, etc.).

    Set this URL in Razorpay Dashboard → Webhooks:
    https://your-api.com/billing/webhook
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not razorpay_service.verify_webhook_signature(body, signature):
        log.warning("webhook_invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event")
    log.info("webhook_received", event_type=event_type)

    if event_type == "payment.captured":
        payload = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payload.get("order_id")
        payment_id = payload.get("id")
        notes = payload.get("notes", {})
        user_id = notes.get("user_id")
        plan_id = notes.get("plan_id")

        if user_id and plan_id and order_id:
            # Check if already activated (idempotent)
            existing = await db.fetchrow(
                "SELECT id FROM payments WHERE razorpay_payment_id = $1 AND status = 'captured'",
                payment_id,
            )
            if not existing:
                await subscription_service.activate_subscription(
                    user_id=user_id,
                    plan_id=plan_id,
                    razorpay_order_id=order_id,
                    razorpay_payment_id=payment_id,
                    db=db,
                )
                await db.execute(
                    "UPDATE payments SET status = 'captured', razorpay_payment_id = $1 WHERE razorpay_order_id = $2",
                    payment_id, order_id,
                )
                log.info("webhook_activated_subscription", user_id=user_id, plan_id=plan_id)

    elif event_type == "payment.failed":
        payload = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payload.get("order_id")
        reason = payload.get("error_description", "Unknown")
        if order_id:
            await db.execute(
                "UPDATE payments SET status = 'failed', failure_reason = $1 WHERE razorpay_order_id = $2",
                reason, order_id,
            )
            log.info("webhook_payment_failed", order_id=order_id, reason=reason)

    return {"status": "ok"}


# ── Cancel subscription ────────────────────────────────────────────────────────

@router.post("/cancel")
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Cancel the current subscription. Downgrades to free at end of period.
    Does NOT immediately revoke access.
    """
    await subscription_service.cancel_subscription(str(current_user["id"]), db)
    return {
        "success": True,
        "message": "Subscription cancelled. You'll retain access until the period ends.",
    }


# ── Payment history ────────────────────────────────────────────────────────────

@router.get("/history")
async def payment_history(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return last 10 payments for the account settings page."""
    rows = await db.fetch(
        """
        SELECT id, plan_id, amount_inr, status, payment_method,
               razorpay_payment_id, created_at, captured_at
        FROM payments
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 10
        """,
        str(current_user["id"]),
    )
    return {"payments": [dict(r) for r in rows]}
