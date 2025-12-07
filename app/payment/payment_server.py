# backend/app/payment/payment_server.py

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Supabase client
from supabase import create_client, Client

load_dotenv()

router = APIRouter(prefix="/payment", tags=["payment"])

# -------------------------------------------------------
# PayU + Supabase CONFIG
# -------------------------------------------------------

PAYU_KEY = os.getenv("PAYU_KEY")
PAYU_SALT = os.getenv("PAYU_SALT")
# Use test by default; set PAYU_BASE_URL in env for production (https://secure.payu.in/_payment)
PAYU_BASE_URL = os.getenv("PAYU_BASE_URL", "https://test.payu.in/_payment")

# Set these via env to the correct frontend URLs in production
PAYU_SURL = os.getenv("PAYU_SURL", "http://localhost:8000/payment/payu_success")
PAYU_FURL = os.getenv("PAYU_FURL", "http://localhost:8000/payment/payu_failure")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not all([PAYU_KEY, PAYU_SALT, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
    print("⚠ WARNING: Missing PayU or Supabase environment variables (some features may not work)")

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# -------------------------------------------------------
# INR → USD Conversion
# -------------------------------------------------------

def convert_inr_to_usd(amount_in_inr: float) -> float:
    try:
        url = "https://api.exchangerate.host/convert?from=INR&to=USD"
        res = requests.get(url, timeout=5).json()
        rate = res.get("result")
        if not rate:
            return round(amount_in_inr / 83, 2)
        return round(amount_in_inr * rate, 2)
    except Exception:
        return round(amount_in_inr / 83, 2)


# -------------------------------------------------------
# Helper Functions
# -------------------------------------------------------

def generate_txnid() -> str:
    return secrets.token_hex(12)


def sanitize_productinfo(plan: str, billing_period: str) -> str:
    """
    Returns a PayU-safe productinfo string. Avoids parentheses and spaces.
    Example: "pro_quarterly"
    """
    p = str(plan).strip().lower().replace(" ", "_")
    b = str(billing_period).strip().lower().replace(" ", "_")
    return f"{p}_{b}"


def generate_request_hash(params: Dict[str, str]) -> str:
    """
    PayU hash format:
    hash_string = key|txnid|amount|productinfo|firstname|email|udf1|...|udf10|salt
    """
    seq = [
        PAYU_KEY or "",
        params.get("txnid", ""),
        params.get("amount", ""),
        params.get("productinfo", ""),
        params.get("firstname", ""),
        params.get("email", "")
    ]
    # add udf1..udf10 in order
    for i in range(1, 11):
        seq.append(params.get(f"udf{i}", ""))

    seq.append(PAYU_SALT or "")
    joined = "|".join(seq)
    return hashlib.sha512(joined.encode("utf-8")).hexdigest().lower()


def verify_response_hash(posted: Dict[str, str]) -> bool:
    """
    Verify response hash from PayU.
    Reverse format:
    hash_string = salt|status|udf10|udf9|...|udf1|email|firstname|productinfo|amount|txnid|key
    """
    received_hash = (posted.get("hash") or "").lower()
    if not received_hash:
        return False

    seq = [PAYU_SALT or "", posted.get("status", "")]

    # udf10 down to udf1
    for i in range(10, 0, -1):
        seq.append(posted.get(f"udf{i}", ""))

    seq.extend([
        posted.get("email", ""),
        posted.get("firstname", ""),
        posted.get("productinfo", ""),
        posted.get("amount", ""),
        posted.get("txnid", ""),
        PAYU_KEY or ""
    ])

    joined = "|".join(seq)
    calc = hashlib.sha512(joined.encode("utf-8")).hexdigest().lower()
    return calc == received_hash


def compute_subscription_dates(billing_period: str) -> Tuple[datetime, datetime]:
    start = datetime.utcnow()
    bp = str(billing_period or "").lower()
    if bp == "monthly":
        end = start + timedelta(days=30)
    elif bp == "quarterly":
        end = start + timedelta(days=90)
    elif bp == "yearly":
        end = start + timedelta(days=365)
    else:
        end = start + timedelta(days=30)
    return start, end


# -------------------------------------------------------
# Pydantic Request Model
# -------------------------------------------------------

class CreatePaymentRequest(BaseModel):
    user_id: str
    plan: str
    billing_period: str
    firstname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    amount: str  # INR string or numeric


# -------------------------------------------------------
# 1) CREATE PAYMENT
# -------------------------------------------------------

@router.post("/create")
async def create_payment(req: CreatePaymentRequest):
    if not PAYU_KEY or not PAYU_SALT:
        raise HTTPException(status_code=500, detail="PayU not configured on server")

    txnid = generate_txnid()

    # --- Format amount to 2 decimal places (required by PayU) ---
    try:
        amount_val = float(req.amount)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount format")

    amount_str = "{:.2f}".format(amount_val)

    # --- Safe productinfo ---
    productinfo = sanitize_productinfo(req.plan, req.billing_period)

    # Build params with udf1..udf10 explicitly (PayU expects position)
    params = {
        "key": PAYU_KEY,
        "txnid": txnid,
        "amount": amount_str,
        "productinfo": productinfo,
        "firstname": req.firstname or "User",
        "email": req.email or "user@example.com",
        "phone": req.phone or "",
        "surl": PAYU_SURL,
        "furl": PAYU_FURL,
        # udf fields (udf1 used for user id)
        "udf1": req.user_id,
        "udf2": "",
        "udf3": "",
        "udf4": "",
        "udf5": "",
        "udf6": "",
        "udf7": "",
        "udf8": "",
        "udf9": "",
        "udf10": "",
        # Some merchant setups still require this param for PayU; harmless in most cases
        "service_provider": "payu_paisa"
    }

    # Create pending record in Supabase
    if supabase:
        try:
            supabase.table("payments").insert({
                "txnid": txnid,
                "user_id": req.user_id,
                "plan": req.plan,
                "billing_period": req.billing_period,
                "amount_in_inr": amount_val,
                "amount_in_usd": convert_inr_to_usd(amount_val),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            # don't crash the request — log and continue
            print("⚠ Failed to insert pending payment:", e)

    # Generate hash
    params["hash"] = generate_request_hash(params)

    # Build auto-submit HTML form (PayU requires POST)
    inputs = "\n".join(
        f'<input type="hidden" name="{k}" value="{v}" />'
        for k, v in params.items()
    )

    form_html = f"""
    <html>
        <head><title>Redirecting...</title></head>
        <body onload="document.forms[0].submit();">
            <form method="post" action="{PAYU_BASE_URL}">
                {inputs}
            </form>
        </body>
    </html>
    """

    return JSONResponse({"form": form_html, "txnid": txnid})


# -------------------------------------------------------
# 2) PAYMENT SUCCESS CALLBACK
# -------------------------------------------------------

@router.post("/payu_success")
async def payu_success(request: Request):
    posted = dict(await request.form())

    status = posted.get("status", "")
    txnid = posted.get("txnid", "")
    user_id = posted.get("udf1", "")
    # Try to parse amount robustly
    try:
        amount_inr = float(posted.get("amount", "0") or 0)
    except Exception:
        amount_inr = 0.0

    amount_usd = convert_inr_to_usd(amount_inr)
    productinfo = posted.get("productinfo", "")

    # Parse plan + billing period if possible
    plan = ""
    billing_period = "monthly"
    if productinfo and "_" in productinfo:
        parts = productinfo.split("_", 1)
        plan = parts[0].lower()
        billing_period = parts[1] if len(parts) > 1 else "monthly"
    else:
        # fallback parsing for older formats
        plan = productinfo.split(" ")[0].lower() if productinfo else ""
        if "(" in productinfo and ")" in productinfo:
            try:
                billing_period = productinfo.split("(")[1].split(")")[0]
            except Exception:
                billing_period = "monthly"

    # Verify hash
    verified = verify_response_hash(posted)

    # Update payment row
    if supabase:
        try:
            supabase.table("payments").update({
                "status": "success" if verified and status.lower() == "success" else "failed",
                "amount_in_inr": amount_inr,
                "amount_in_usd": amount_usd,
                "response": posted,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("txnid", txnid).execute()
        except Exception as e:
            print("⚠ Failed updating payment:", e)

    # Upgrade subscription if valid
    if verified and status.lower() == "success" and user_id:
        try:
            start, end = compute_subscription_dates(billing_period)
            tier = "pro" if plan == "pro" else "standard"

            if supabase:
                supabase.table("users").update({
                    "subscription_tier": tier,
                    "subscription_status": "active",
                    "subscription_start_date": start.isoformat(),
                    "subscription_end_date": end.isoformat(),
                    "last_payment_inr": amount_inr,
                    "last_payment_usd": amount_usd,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", user_id).execute()
        except Exception as e:
            print("⚠ Failed upgrading subscription:", e)

    html = f"""
    <html>
        <body>
            <h2>Payment Success</h2>
            <p>Transaction ID: {txnid}</p>
            <p>Paid: ₹{amount_inr} (~${amount_usd})</p>
            <a href="/">Return to App</a>
        </body>
    </html>
    """
    return HTMLResponse(html)


# -------------------------------------------------------
# 3) PAYMENT FAILURE CALLBACK
# -------------------------------------------------------

@router.post("/payu_failure")
async def payu_failure(request: Request):
    posted = dict(await request.form())
    txnid = posted.get("txnid", "")

    if supabase:
        try:
            supabase.table("payments").update({
                "status": "failed",
                "response": posted,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("txnid", txnid).execute()
        except Exception as e:
            print("⚠ Failed updating failure:", e)

    html = f"""
    <html>
        <body>
            <h2>Payment Failed</h2>
            <p>Transaction ID: {txnid}</p>
            <a href="/">Return to App</a>
        </body>
    </html>
    """
    return HTMLResponse(html)


# -------------------------------------------------------
# Export router for app.main
# -------------------------------------------------------

def get_router():
    return router
