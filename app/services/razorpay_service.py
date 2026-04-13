"""
Razorpay Integration
=====================
Handles:
  1. Creating a Razorpay order (returns order_id to frontend)
  2. Verifying webhook HMAC signature (validates payment)
  3. Capturing payment details for the audit log

Why Razorpay?
  - Only serious INR payment gateway for India
  - Supports UPI, cards, net banking, wallets
  - No monthly fee — 2% per transaction
  - Webhook-based confirmation is the correct flow

Payment flow:
  Frontend: Open Razorpay checkout → User pays → Razorpay calls webhook
  Backend:  Verify HMAC → Activate subscription → Return success to frontend

NEVER trust the frontend to confirm payment.
ALWAYS verify via webhook signature before activating.
"""
import hmac
import hashlib
import json
import httpx
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


# ── Razorpay API client ───────────────────────────────────────────────────────

def _auth() -> tuple:
    return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)

RAZORPAY_BASE = "https://api.razorpay.com/v1"


async def create_order(amount_inr: int, plan_id: str, user_id: str, receipt: str) -> dict:
    """
    Create a Razorpay order.
    amount_inr is in rupees — we convert to paise (× 100) here.

    Returns the order dict including `id` (razorpay_order_id).
    """
    payload = {
        "amount":   amount_inr * 100,    # Razorpay uses paise
        "currency": "INR",
        "receipt":  receipt,             # Internal reference (payment UUID)
        "notes": {
            "user_id": user_id,
            "plan_id": plan_id,
        },
        "payment_capture": 1,            # Auto-capture on success
    }

    async with httpx.AsyncClient(auth=_auth(), timeout=10) as client:
        resp = await client.post(f"{RAZORPAY_BASE}/orders", json=payload)

    if resp.status_code not in (200, 201):
        log.error("razorpay_order_failed", status=resp.status_code, body=resp.text)
        raise RuntimeError(f"Razorpay order creation failed: {resp.text}")

    order = resp.json()
    log.info("razorpay_order_created", order_id=order["id"], amount=amount_inr, plan=plan_id)
    return order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature sent by Razorpay.
    This is the ONLY authoritative confirmation that a payment succeeded.

    Never activate a subscription without this check passing.
    """
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        key=settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    result = hmac.compare_digest(expected, razorpay_signature)
    if not result:
        log.warning(
            "razorpay_signature_mismatch",
            order_id=razorpay_order_id,
            payment_id=razorpay_payment_id,
        )
    return result


def verify_webhook_signature(payload_body: bytes, razorpay_signature: str) -> bool:
    """
    Verify webhook event signature.
    Used for server-to-server webhook calls from Razorpay.
    """
    expected = hmac.new(
        key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


async def get_payment_details(razorpay_payment_id: str) -> Optional[dict]:
    """Fetch payment details from Razorpay API for audit."""
    try:
        async with httpx.AsyncClient(auth=_auth(), timeout=10) as client:
            resp = await client.get(f"{RAZORPAY_BASE}/payments/{razorpay_payment_id}")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.warning("razorpay_fetch_payment_failed", payment_id=razorpay_payment_id, error=str(e))
    return None
