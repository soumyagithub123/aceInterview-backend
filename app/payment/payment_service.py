# app/payment/payment_service.py

import os
import hmac
import hashlib
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4

from app.payment.razorpay_client import razorpay_client
from app.payment.payment_models import CreateOrderRequest, VerifyPaymentRequest
from app.supabase_client import get_supabase_service_client

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")


# -------------------------------------------------
# Create Razorpay Order
# -------------------------------------------------
def create_razorpay_order(payload: CreateOrderRequest) -> Dict:
    """
    Creates a Razorpay order.
    Amount is expected in INR; Razorpay needs paise.
    """
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise Exception("Razorpay keys not configured")

    # Attach ALL required metadata in notes
    order_data = {
        "amount": payload.amount * 100,  # INR -> paise
        "currency": payload.currency,
        "payment_capture": 1,
        "notes": {
            "user_id": payload.user_id,
            "plan": payload.plan or "basic",
            "billing_period": payload.billing_period or "monthly",
        },
    }

    order = razorpay_client.order.create(order_data)

    return {
        "order_id": order["id"],
        "amount": payload.amount * 100,  # Return in paisa
        "currency": payload.currency,
        "razorpay_key": RAZORPAY_KEY_ID,
    }


# -------------------------------------------------
# Verify Payment Signature
# -------------------------------------------------
def verify_razorpay_payment(payload: VerifyPaymentRequest) -> Dict:
    """
    Verifies Razorpay payment signature
    """
    if not RAZORPAY_KEY_SECRET:
        raise Exception("Razorpay secret not configured")

    body = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"

    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_signature != payload.razorpay_signature:
        raise ValueError("Invalid Razorpay payment signature")

    return {
        "status": "success",
        "payment_id": payload.razorpay_payment_id,
        "order_id": payload.razorpay_order_id,
    }


# -------------------------------------------------
# 💾 DATABASE OPERATIONS
# -------------------------------------------------

def save_payment_transaction(
    user_id: str,
    razorpay_order_id: str,
    amount: int,
    currency: str,
    plan_type: str,
    billing_period: str,
    status: str = "created"
) -> Dict:
    """
    Saves payment transaction to database
    """
    supabase = get_supabase_service_client()
    
    try:
        result = supabase.table("payment_transactions").insert({
            "user_id": user_id,
            "razorpay_order_id": razorpay_order_id,
            "amount": amount * 100,  # Convert to paise
            "currency": currency,
            "plan_type": plan_type,
            "billing_period": billing_period,
            "status": status,
        }).execute()
        
        print(f"💾 Transaction saved: {razorpay_order_id}")
        return result.data[0] if result.data else {}
        
    except Exception as e:
        print(f"❌ Failed to save transaction: {e}")
        raise


def update_payment_transaction(
    razorpay_order_id: str,
    razorpay_payment_id: Optional[str] = None,
    razorpay_signature: Optional[str] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    failure_reason: Optional[str] = None,
    payment_captured_at: Optional[datetime] = None
) -> Dict:
    """
    Updates payment transaction status
    """
    supabase = get_supabase_service_client()
    
    update_data = {}
    
    if razorpay_payment_id:
        update_data["razorpay_payment_id"] = razorpay_payment_id
    if razorpay_signature:
        update_data["razorpay_signature"] = razorpay_signature
    if status:
        update_data["status"] = status
    if payment_method:
        update_data["payment_method"] = payment_method
    if failure_reason:
        update_data["failure_reason"] = failure_reason
    if payment_captured_at:
        update_data["payment_captured_at"] = payment_captured_at.isoformat()
    
    try:
        result = (
            supabase.table("payment_transactions")
            .update(update_data)
            .eq("razorpay_order_id", razorpay_order_id)
            .execute()
        )
        
        print(f"💾 Transaction updated: {razorpay_order_id} → {status}")
        return result.data[0] if result.data else {}
        
    except Exception as e:
        print(f"❌ Failed to update transaction: {e}")
        raise


def update_user_subscription(
    user_id: str,
    subscription_tier: str,
    subscription_status: str,
    start_date: datetime,
    end_date: datetime
) -> Dict:
    """
    Updates user subscription in users table
    """
    supabase = get_supabase_service_client()
    
    try:
        result = (
            supabase.table("users")
            .update({
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status,
                "subscription_start_date": start_date.isoformat(),
                "subscription_end_date": end_date.isoformat(),
            })
            .eq("id", user_id)
            .execute()
        )
        
        print(f"💾 Subscription updated: {user_id} → {subscription_tier}")
        return result.data[0] if result.data else {}
        
    except Exception as e:
        print(f"❌ Failed to update subscription: {e}")
        raise


def log_subscription_history(
    user_id: str,
    razorpay_order_id: str,
    subscription_tier: str,
    start_date: datetime,
    end_date: datetime,
    change_reason: str = "payment"
) -> Dict:
    """
    Logs subscription change to history table
    """
    supabase = get_supabase_service_client()
    
    try:
        # Get payment transaction id
        transaction = (
            supabase.table("payment_transactions")
            .select("id")
            .eq("razorpay_order_id", razorpay_order_id)
            .single()
            .execute()
        )
        
        payment_transaction_id = transaction.data.get("id") if transaction.data else None
        
        # Insert history
        result = (
            supabase.table("subscription_history")
            .insert({
                "user_id": user_id,
                "subscription_tier": subscription_tier,
                "subscription_status": "active",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "payment_transaction_id": payment_transaction_id,
                "change_reason": change_reason,
            })
            .execute()
        )
        
        print(f"📝 Subscription history logged: {user_id}")
        return result.data[0] if result.data else {}
        
    except Exception as e:
        print(f"❌ Failed to log subscription history: {e}")
        # Don't raise - this is not critical
        return {}


def get_user_plan_limits(user_id: str) -> Dict:
    """
    Gets user's current plan limits
    """
    supabase = get_supabase_service_client()
    
    try:
        result = supabase.rpc("get_user_quota", {"p_user_id": user_id}).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return {}
        
    except Exception as e:
        print(f"❌ Failed to get plan limits: {e}")
        return {}


def check_feature_access(user_id: str, feature: str) -> bool:
    """
    Checks if user can access a feature
    feature: 'copilot_session' or 'mock_interview'
    """
    supabase = get_supabase_service_client()
    
    try:
        result = supabase.rpc(
            "check_user_limit",
            {"p_user_id": user_id, "p_feature": feature}
        ).execute()
        
        return result.data if result.data is not None else False
        
    except Exception as e:
        print(f"❌ Failed to check feature access: {e}")
        return False