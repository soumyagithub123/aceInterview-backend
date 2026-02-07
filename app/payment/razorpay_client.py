# app/payment/razorpay_client.py

import os
import razorpay

# Razorpay credentials (from .env)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError("❌ Razorpay keys not configured in environment")

# Razorpay client instance
razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

# Optional: timeout & retry safety
razorpay_client.set_app_details({
    "title": "Interview Assistant",
    "version": "1.0.0"
})
