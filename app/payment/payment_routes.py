# app/payment/payment_routes.py

import os
import hmac
import hashlib
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Depends
from app.routes.users_routes import get_current_user_from_token

from app.payment.payment_models import (
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from app.payment.payment_service import (
    create_razorpay_order,
    verify_razorpay_payment,
    save_payment_transaction,
    update_payment_transaction,
    update_user_subscription,
    log_subscription_history,
)

from app.supabase_client import get_supabase_service_client

router = APIRouter(prefix="/api/payments", tags=["payments"])


# -------------------------------------------------
# Create Order (Frontend → Backend)
# -------------------------------------------------
@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    current_user=Depends(get_current_user_from_token)
):
    """
    Creates Razorpay order and saves transaction record
    """
    try:
        # 🔥 Inject user_id from token
        payload.user_id = current_user.id
        
        # Create Razorpay order
        order_response = create_razorpay_order(payload)
        
        # 💾 Save transaction in database
        save_payment_transaction(
            user_id=current_user.id,
            razorpay_order_id=order_response["order_id"],
            amount=payload.amount,
            currency=payload.currency,
            plan_type=payload.plan or "basic",
            billing_period=payload.billing_period or "monthly",
            status="created"
        )
        
        print(f"✅ Order created: {order_response['order_id']} for user {current_user.id}")
        
        return order_response
        
    except Exception as e:
        print(f"❌ Order creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------
# Verify Payment (Frontend → Backend)
# -------------------------------------------------
@router.post("/verify-payment", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    current_user=Depends(get_current_user_from_token)
):
    """
    Verifies payment signature and updates transaction status
    """
    try:
        # Verify signature
        verification = verify_razorpay_payment(payload)
        
        # 💾 Update transaction status
        update_payment_transaction(
            razorpay_order_id=payload.razorpay_order_id,
            razorpay_payment_id=payload.razorpay_payment_id,
            razorpay_signature=payload.razorpay_signature,
            status="authorized"
        )
        
        print(f"✅ Payment verified: {payload.razorpay_payment_id}")
        
        return verification
        
    except ValueError as e:
        print(f"❌ Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------
# Razorpay Webhook (Razorpay → Backend)
# -------------------------------------------------
@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """
    Handles Razorpay webhook events:
    - payment.captured → Activates subscription
    - payment.failed → Marks transaction as failed
    """
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    # -------------------------------------------------
    # Verify webhook signature
    # -------------------------------------------------
    expected_signature = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if signature != expected_signature:
        print("❌ Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    print(f"📨 Webhook received: {event}")

    # -------------------------------------------------
    # Handle payment.captured
    # -------------------------------------------------
    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})

        payment_id = payment.get("id")
        order_id = payment.get("order_id")
        amount = payment.get("amount")
        payment_method = payment.get("method")
        notes = payment.get("notes", {})

        user_id = notes.get("user_id")
        plan = notes.get("plan")
        billing_period = notes.get("billing_period", "monthly")

        if not user_id or not plan:
            print("❌ Missing user_id or plan in webhook")
            raise HTTPException(
                status_code=400,
                detail="Missing user_id or plan in Razorpay notes"
            )

        # -------------------------------------------------
        # Calculate subscription validity
        # -------------------------------------------------
        now = datetime.utcnow()

        if billing_period == "monthly":
            end_date = now + timedelta(days=30)
        elif billing_period == "quarterly":
            end_date = now + timedelta(days=90)
        elif billing_period == "yearly":
            end_date = now + timedelta(days=365)
        else:
            end_date = now + timedelta(days=30)

        try:
            # -------------------------------------------------
            # 1. Update transaction status to captured
            # -------------------------------------------------
            update_payment_transaction(
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                status="captured",
                payment_method=payment_method,
                payment_captured_at=now
            )

            # -------------------------------------------------
            # 2. Update user subscription
            # -------------------------------------------------
            update_user_subscription(
                user_id=user_id,
                subscription_tier=plan,
                subscription_status="active",
                start_date=now,
                end_date=end_date
            )

            # -------------------------------------------------
            # 3. Log subscription history
            # -------------------------------------------------
            log_subscription_history(
                user_id=user_id,
                razorpay_order_id=order_id,
                subscription_tier=plan,
                start_date=now,
                end_date=end_date,
                change_reason="payment"
            )

            print(
                f"✅ Payment captured successfully\n"
                f"   User: {user_id}\n"
                f"   Plan: {plan} ({billing_period})\n"
                f"   Payment ID: {payment_id}\n"
                f"   Valid till: {end_date.isoformat()}"
            )

        except Exception as e:
            print(f"❌ Failed to process payment webhook: {e}")
            # Don't raise exception - webhook should return 200 even on internal error
            # Razorpay will retry if we return non-200

    # -------------------------------------------------
    # Handle payment.failed
    # -------------------------------------------------
    elif event == "payment.failed":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        
        payment_id = payment.get("id")
        order_id = payment.get("order_id")
        error_code = payment.get("error_code")
        error_description = payment.get("error_description")

        try:
            update_payment_transaction(
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                status="failed",
                failure_reason=f"{error_code}: {error_description}"
            )
            
            print(f"❌ Payment failed: {payment_id} - {error_description}")
            
        except Exception as e:
            print(f"❌ Failed to update failed payment: {e}")

    return {"status": "ok"}


# -------------------------------------------------
# Get User Payment History
# -------------------------------------------------
@router.get("/history")
def get_payment_history(current_user=Depends(get_current_user_from_token)):
    """
    Returns user's payment history
    """
    try:
        supabase = get_supabase_service_client()
        
        result = (
            supabase.table("payment_transactions")
            .select("*")
            .eq("user_id", current_user.id)
            .order("created_at", desc=True)
            .execute()
        )
        
        return {"payments": result.data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------
# Get User Quota/Limits
# -------------------------------------------------
@router.get("/quota")
def get_user_quota(current_user=Depends(get_current_user_from_token)):
    """
    Returns user's current usage quota
    """
    try:
        supabase = get_supabase_service_client()
        
        # Call PostgreSQL function
        result = supabase.rpc("get_user_quota", {"p_user_id": current_user.id}).execute()
        
        if result.data and len(result.data) > 0:
            quota = result.data[0]
            return {
                "copilot": {
                    "used": quota.get("copilot_used", 0),
                    "total": quota.get("copilot_total", 0),
                    "remaining": quota.get("copilot_remaining", 0)
                },
                "mock_interview": {
                    "used": quota.get("mock_used", 0),
                    "total": quota.get("mock_total", 0),
                    "remaining": quota.get("mock_remaining", 0)
                },
                "is_unlimited": quota.get("is_unlimited", False)
            }
        else:
            return {"error": "User quota not found"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))