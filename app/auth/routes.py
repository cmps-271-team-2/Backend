from app.auth.schemas import RequestOtpBody, RequestOtpResponse, VerifyOtpBody, VerifyOtpResponse
from app.auth.otp_service import generate_otp, hash_otp, otp_expiry_time, verify_otp
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core.email_sender import send_otp_email

from fastapi import APIRouter, HTTPException

from app.auth.schemas import (
    RequestOtpBody, RequestOtpResponse,
    VerifyOtpBody, VerifyOtpResponse,
    ResendOtpBody, ResendOtpResponse
)


from app.core.firebase_admin import get_firebase_auth
from app.core.firestore import get_db
from app.auth.otp_service import generate_otp, hash_otp, otp_expiry_time
from datetime import datetime, timezone

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/register/request-otp", response_model=RequestOtpResponse)
def request_otp(body: RequestOtpBody):
    email = normalize_email(body.email)

    # 1) Enforce AUB domain (SECURITY)
    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    try:
        # 2) Create Firebase user (disabled until OTP verified)
        user = firebase_auth.create_user(
            email=email,
            password=body.password,
            disabled=True,
        )
        uid = user.uid

        now_iso = datetime.now(timezone.utc).isoformat()

        # 3) Create minimal user profile in Firestore
        db.collection("users").document(uid).set({
            "email": email,
            "isVerified": False,
            "createdAt": now_iso,
        })

        # 4) Generate + hash OTP and store temporarily
        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at_iso = otp_expiry_time().isoformat()

        db.collection("otp_requests").document(uid).set({
            "email": email,
            "uid": uid,
            "otpHash": otp_hash,
            "expiresAt": expires_at_iso,
            "createdAt": now_iso,
            "verifyAttempts": 0,
            "resendCount": 1,
            "used": False,
        })

        # Send email with OTP code
        send_otp_email(email, otp)
        return RequestOtpResponse(message="OTP sent to your email.")


    except Exception as e:
        # ✅ IMPORTANT: Always raise an HTTPException, never “fall through”
        raise HTTPException(status_code=400, detail=f"Request OTP failed: {str(e)}")

@router.post("/register/verify-otp", response_model=VerifyOtpResponse)
def verify_otp_endpoint(body: VerifyOtpBody):
    email = normalize_email(body.email)
    otp_input = body.otp.strip()

    # 1) Basic OTP format check (digits only)
    if not otp_input.isdigit():
        raise HTTPException(status_code=400, detail="OTP must be 6 digits.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    # 2) Find the Firebase user by email to get UID
    try:
        user = firebase_auth.get_user_by_email(email)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found. Request OTP again.")

    uid = user.uid

    # 3) Load OTP request doc
    otp_doc_ref = db.collection("otp_requests").document(uid)
    otp_doc = otp_doc_ref.get()

    if not otp_doc.exists:
        raise HTTPException(status_code=400, detail="No OTP request found. Request OTP again.")

    data = otp_doc.to_dict()

    # 4) Check if already used
    if data.get("used") is True:
        raise HTTPException(status_code=400, detail="OTP already used. Request a new OTP.")

    # 5) Check expiry
    expires_at_iso = data.get("expiresAt")
    if not expires_at_iso:
        raise HTTPException(status_code=400, detail="OTP data corrupted. Request OTP again.")

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromisoformat(expires_at_iso)
    if now > expires_at:
        raise HTTPException(status_code=400, detail="OTP expired. Request a new OTP.")

    # 6) Rate limit attempts
    attempts = int(data.get("verifyAttempts", 0))
    if attempts >= 10:
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new OTP.")

    # 7) Verify OTP hash
    otp_hash = data.get("otpHash")
    if not otp_hash:
        raise HTTPException(status_code=400, detail="OTP data corrupted. Request OTP again.")

    if not verify_otp(otp_input, otp_hash):
        # increment attempts
        otp_doc_ref.update({"verifyAttempts": attempts + 1})
        raise HTTPException(status_code=400, detail="Incorrect OTP.")

    # ✅ OTP correct -> mark used
    otp_doc_ref.update({
        "used": True,
        "usedAt": now.isoformat(),
    })

    # 8) Enable Firebase user
    firebase_auth.update_user(uid, disabled=False)

    # 9) Update Firestore user doc
    db.collection("users").document(uid).update({
        "isVerified": True,
        "verifiedAt": now.isoformat(),
    })

    return VerifyOtpResponse(message="Email verified ✅ Account activated.")
    return RequestOtpResponse(message="OTP generated. Check your email (or backend console in dev).")

@router.post("/register/resend-otp", response_model=ResendOtpResponse)
def resend_otp(body: ResendOtpBody):
    email = normalize_email(body.email)

    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    # 1) Find user
    try:
        user = firebase_auth.get_user_by_email(email)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found. Register first.")

    uid = user.uid

    # 2) Check Firestore user verified status
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(status_code=400, detail="User profile missing. Register again.")

    user_data = user_doc.to_dict()
    if user_data.get("isVerified") is True:
        raise HTTPException(status_code=400, detail="User already verified. Please login.")

    # 3) Load OTP request doc
    otp_ref = db.collection("otp_requests").document(uid)
    otp_doc = otp_ref.get()
    if not otp_doc.exists:
        raise HTTPException(status_code=400, detail="No OTP request found. Register again.")

    data = otp_doc.to_dict()
    now = datetime.now(timezone.utc)

    # 4) Rate limiting (simple + effective)
    # Max resends: 3 total
    resend_count = int(data.get("resendCount", 0))
    if resend_count >= 3:
        raise HTTPException(status_code=429, detail="Too many resends. Try again later.")

    # Cooldown: 30 seconds between resends
    last_sent = data.get("lastSentAt")
    if last_sent:
        last_sent_dt = datetime.fromisoformat(last_sent)
        if (now - last_sent_dt).total_seconds() < 30:
            raise HTTPException(status_code=429, detail="Please wait 30 seconds before resending.")

    # 5) Generate new OTP, update Firestore
    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at_iso = otp_expiry_time().isoformat()

    otp_ref.update({
        "otpHash": otp_hash,
        "expiresAt": expires_at_iso,
        "verifyAttempts": 0,           # reset attempts for new code
        "used": False,
        "resendCount": resend_count + 1,
        "lastSentAt": now.isoformat(),
    })

    # 6) Send email
    send_otp_email(email, otp)

    return ResendOtpResponse(message="OTP resent. Check your email.")
