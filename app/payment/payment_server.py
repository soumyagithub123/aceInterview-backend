import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

import requests
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from supabase import create_client, Client

load_dotenv()

router = APIRouter(prefix="/payment", tags=["payment"])

# -------------------------------------------------------
# PayU + Supabase CONFIG
# -------------------------------------------------------

PAYU_KEY = os.getenv("PAYU_KEY")
PAYU_SALT = os.getenv("PAYU_SALT")
PAYU_BASE_URL = os.getenv("PAYU_BASE_URL", "https://test.payu.in/_payment")

PAYU_SURL = os.getenv("PAYU_SURL", "http://localhost:8000/payment/payu_success")
PAYU_FURL = os.getenv("PAYU_FURL", "http://localhost:8000/payment/payu_failure")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not all([PAYU_KEY, PAYU_SALT, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
    print("⚠ WARNING: Missing PayU or Supabase environment variables")

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

def _amt_2dp(x: str) -> str:
    return str(Decimal(str(x)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))

def generate_payu_hash(params: Dict[str, str], key: str, salt: str) -> str:
    # PayU merchant-hosted hash sequence:
    # key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
    
    amt = _amt_2dp(params["amount"])

    udf1 = params.get("udf1", "")
    udf2 = params.get("udf2", "")
    udf3 = params.get("udf3", "")
    udf4 = params.get("udf4", "")
    udf5 = params.get("udf5", "")

    # Note: PayU expects UDF1-5 populated if used, and UDF6-10 empty (|||||) before salt
    # Structure: ...|udf5|udf6|udf7|udf8|udf9|udf10|salt
    # If UDF6-10 are empty, that results in 6 pipes: ||||||salt
    
    raw = (
        f"{key}|{params['txnid']}|{amt}|{params['productinfo']}|"
        f"{params['firstname']}|{params['email']}|"
        f"{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    )

    return hashlib.sha512(raw.encode("utf-8")).hexdigest().lower()


def verify_response_hash(posted: Dict[str, str]) -> bool:
    received_hash = posted.get("hash", "")

    # Reverse hash sequence for verification
    # salt|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
    
    seq = [PAYU_SALT, posted.get("status", "")]
    
    # Add UDF 10 down to 1
    for i in range(10, 0, -1):
        seq.append(posted.get(f"udf{i}", ""))

    seq.extend([
        posted.get("email", ""),
        posted.get("firstname", ""),
        posted.get("productinfo", ""),
        posted.get("amount", ""),
        posted.get("txnid", ""),
        PAYU_KEY
    ])

    calc = hashlib.sha512("|".join(seq).encode()).hexdigest().lower()
    return calc == received_hash.lower()


def compute_subscription_dates(billing_period: str) -> Tuple[datetime, datetime]:
    start = datetime.utcnow()
    bp = billing_period.lower()

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
    amount: str  # Send as string to preserve precision


# -------------------------------------------------------
# 1) CREATE PAYMENT
# -------------------------------------------------------

@router.post("/create")
async def create_payment(req: CreatePaymentRequest):

    if not PAYU_KEY or not PAYU_SALT:
        raise HTTPException(500, "PayU not configured")

    txnid = generate_txnid()

    # PayU requires EXACT key name "txnid"
    amount_str = _amt_2dp(req.amount)
    productinfo = f"{req.plan.lower()} subscription ({req.billing_period.lower()})"
    
    # Use provided firstname or fallback to "User"
    # IMPORTANT: The hash will be calculated on THIS value. 
    # If the user edits the name in the HTML form before submitting, the hash will fail.
    first_name_val = req.firstname if req.firstname and req.firstname.strip() else "User"

    params = {
        "key": PAYU_KEY,
        "txnid": txnid,
        "amount": amount_str,
        "productinfo": productinfo,
        "firstname": first_name_val,
        "email": req.email if req.email else "user@example.com",
        "phone": req.phone if req.phone else "9999999999", 
        "surl": PAYU_SURL,
        "furl": PAYU_FURL,

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
    }

    # Generate the hash using the parameters prepared above
    params["hash"] = generate_payu_hash(params, PAYU_KEY, PAYU_SALT)

    # Insert pending row in Supabase
    if supabase:
        try:
            supabase.table("payments").insert({
                "txn_id": txnid,
                "user_id": req.user_id,
                "plan": req.plan,
                "billing_period": req.billing_period,
                "amount": float(req.amount),
                "amount_in_inr": float(req.amount),
                "amount_in_usd": convert_inr_to_usd(float(req.amount)),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            print("⚠ Failed to insert pending payment:", e)

    # Return auto-submitting HTML form to PayU
    inputs = "\n".join(
        f'<input type="hidden" name="{k}" value="{v}" />'
        for k, v in params.items()
    )

    form_html = f"""
    <html>
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

    form = await request.form()
    posted = dict(form)

    status = posted.get("status", "")
    txnid = posted.get("txnid", "")
    user_id = posted.get("udf1", "")
    amount_inr = float(posted.get("amount", "0"))

    amount_usd = convert_inr_to_usd(amount_inr)

    productinfo = posted.get("productinfo", "")

    # Extract plan and billing period
    # Safely handle format "pro subscription (monthly)"
    try:
        plan = productinfo.split(" ")[0].lower()
        if "(" in productinfo and ")" in productinfo:
            billing_period = productinfo.split("(")[1].split(")")[0]
        else:
            billing_period = "monthly"
    except Exception:
        plan = "standard"
        billing_period = "monthly"

    verified = verify_response_hash(posted)

    # Update payment row
    if supabase:
        try:
            supabase.table("payments").update({
                "status": "success" if verified else "failed",
                "amount_in_inr": amount_inr,
                "amount_in_usd": amount_usd,
                "response": posted,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("txn_id", txnid).execute()
        except Exception as e:
            print("⚠ Failed updating payment:", e)

    # If payment valid → update user's subscription
    if verified and status.lower() == "success" and user_id:
        try:
            start, end = compute_subscription_dates(billing_period)
            tier = "pro" if plan == "pro" else "standard"

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

    form = await request.form()
    posted = dict(form)

    txnid = posted.get("txnid", "")

    if supabase:
        try:
            supabase.table("payments").update({
                "status": "failed",
                "response": posted,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("txn_id", txnid).execute()
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