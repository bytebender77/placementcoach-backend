from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class PlanOut(BaseModel):
    id: str
    name: str
    price_inr: int
    analyses_per_month: int
    features: Dict[str, Any]


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: str
    plan: Optional[PlanOut] = None
    status: str
    current_period_start: datetime
    current_period_end: datetime
    analyses_used_this_period: int
    analyses_remaining: int          # -1 = unlimited
    is_active: bool
    days_remaining: int


class CreateOrderRequest(BaseModel):
    plan_id: str                     # 'basic' | 'pro'


class CreateOrderResponse(BaseModel):
    razorpay_order_id: str
    amount: int                      # in paise (₹49 = 4900 paise)
    currency: str
    plan_id: str
    plan_name: str
    key_id: str                      # Razorpay public key — safe to expose


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str


class VerifyPaymentResponse(BaseModel):
    success: bool
    message: str
    subscription: Optional[SubscriptionOut] = None


class UsageStatus(BaseModel):
    """What the frontend shows in the header/dashboard."""
    plan_id: str
    plan_name: str
    analyses_used: int
    analyses_limit: int              # -1 = unlimited
    analyses_remaining: int          # -1 = unlimited
    period_end: datetime
    days_remaining: int
    can_analyse: bool
    features: Dict[str, Any]
    upgrade_required: bool
    upgrade_message: str
