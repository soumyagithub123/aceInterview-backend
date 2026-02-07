# app/payment/payment_models.py

from pydantic import BaseModel, Field
from typing import Optional


# -------------------------
# Create Order
# -------------------------
class CreateOrderRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in INR")
    currency: str = Field(default="INR")
    plan: Optional[str] = Field(default=None, description="Plan name (basic/pro)")
    billing_period: Optional[str] = Field(default="monthly", description="Billing cycle (monthly/yearly)")
    user_id: Optional[str] = Field(default=None, description="Injected by backend")


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    razorpay_key: str


# -------------------------
# Verify Payment
# -------------------------
class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    user_id: Optional[str] = None


class VerifyPaymentResponse(BaseModel):
    status: str
    payment_id: str
    order_id: str


# -------------------------
# Webhook (internal use)
# -------------------------
class WebhookResponse(BaseModel):
    status: str
