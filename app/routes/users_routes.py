from fastapi import APIRouter, HTTPException, Depends, Header
from app.supabase_client import (
    get_supabase_client,
    get_supabase_service_client,
)

router = APIRouter(prefix="/api/users", tags=["users"])


# --------------------------------------------------
# 🔐 AUTH: Get current user from Supabase JWT
# --------------------------------------------------
def get_current_user_from_token(
    authorization: str = Header(None)
):
    """
    Extract authenticated user from Supabase JWT
    Header: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )

    token = authorization.replace("Bearer ", "").strip()

    try:
        # ✅ ANON client is correct for auth verification
        anon_supabase = get_supabase_client()
        res = anon_supabase.auth.get_user(token)

        if not res or not res.user:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
            )

        return res.user

    except Exception as e:
        print("❌ Auth error:", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )


# --------------------------------------------------
# 👤 GET CURRENT USER PROFILE
# --------------------------------------------------
@router.get("/me")
def get_current_user_profile(
    current_user=Depends(get_current_user_from_token),
):
    """
    Returns the current user's profile.
    Auto-creates the user row if missing.
    """

    # 🔥 SERVICE ROLE client (bypasses RLS)
    supabase = get_supabase_service_client()

    try:
        # 1️⃣ Try to fetch existing user
        res = (
            supabase
            .table("users")
            .select(
                "id, email, subscription_tier, subscription_status, "
                "subscription_start_date, subscription_end_date"
            )
            .eq("id", current_user.id)
            .execute()
        )

        if res.data and len(res.data) > 0:
            return res.data[0]

        # 2️⃣ User not found → auto-create
        print(
            f"⚠️ User {current_user.id} not found. Auto-creating..."
        )

        new_user_payload = {
            "id": current_user.id,
            "email": current_user.email,
        }

        create_res = (
            supabase
            .table("users")
            .insert(new_user_payload)
            .select()
            .single()
            .execute()
        )

        if create_res.data:
            print(
                f"✅ User {current_user.id} created successfully."
            )
            return create_res.data

        # Fallback (should not happen)
        return new_user_payload

    except Exception as e:
        import traceback

        traceback.print_exc()
        print("❌ Error fetching/creating user:", e)

        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}",
        )
