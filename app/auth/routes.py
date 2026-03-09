import json
import os
from datetime import datetime, timezone
from typing import Optional
from urllib import request, error

from fastapi import APIRouter, Depends, Header, HTTPException

from app.auth.schemas import (
    RequestOtpBody,
    RequestOtpResponse,
    VerifyOtpBody,
    VerifyOtpResponse,
    ResendOtpBody,
    ResendOtpResponse,
    ForgotPasswordBody,
    ForgotPasswordResponse,
    ResetPasswordBody,
    ResetPasswordResponse,
    ChangePasswordBody,
    ChangePasswordResponse,
)
from app.auth.otp_service import generate_otp, hash_otp, otp_expiry_time, verify_otp
from app.core.email_sender import send_otp_email, send_password_reset_otp_email
from app.core.firebase_admin import get_firebase_auth
from app.core.firestore import get_db

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header.")
    return parts[1].strip()


def get_current_user(authorization: Optional[str] = Header(default=None)):
    token = get_bearer_token(authorization)
    firebase_auth = get_firebase_auth()
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


def verify_firebase_password(email: str, password: str) -> bool:
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="FIREBASE_WEB_API_KEY is missing.")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with request.urlopen(req, timeout=10) as res:
            return res.status == 200
    except error.HTTPError:
        return False
    except Exception:
        return False


@router.post("/register/request-otp", response_model=RequestOtpResponse)
def request_otp(body: RequestOtpBody):
    email = normalize_email(body.email)

    # 1) Enforce AUB domain (SECURITY)
    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    existing_user = None
    try:
        existing_user = firebase_auth.get_user_by_email(email)
    except Exception:
        existing_user = None

    if existing_user:
        user_doc = db.collection("users").document(existing_user.uid).get()
        if user_doc.exists and user_doc.to_dict().get("isVerified") is True:
            raise HTTPException(status_code=400, detail="EMAIL_EXISTS")

    try:
        now_iso = datetime.now(timezone.utc).isoformat()

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        expires_at_iso = otp_expiry_time().isoformat()

        pending_ref = db.collection("pending_registrations").document(email)
        pending_doc = pending_ref.get()
        resend_count = 1
        if pending_doc.exists:
            pending_data = pending_doc.to_dict() or {}
            resend_count = int(pending_data.get("resendCount", 0)) + 1

        pending_ref.set({
            "email": email,
            "password": body.password,
            "otpHash": otp_hash,
            "expiresAt": expires_at_iso,
            "createdAt": now_iso,
            "verifyAttempts": 0,
            "resendCount": resend_count,
            "used": False,
            "lastSentAt": now_iso,
            "existingUid": existing_user.uid if existing_user else None,
        }, merge=True)

        send_otp_email(email, otp)

        if pending_doc.exists:
            return RequestOtpResponse(message="PENDING_VERIFICATION")

        return RequestOtpResponse(message="OTP sent to your email.")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Request OTP failed: {str(e)}")

@router.post("/register/verify-otp", response_model=VerifyOtpResponse)
def verify_otp_endpoint(body: VerifyOtpBody):
    email = normalize_email(body.email)
    otp_input = body.otp.strip()

    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    # 1) Basic OTP format check (digits only)
    if not otp_input.isdigit():
        raise HTTPException(status_code=400, detail="OTP must be 6 digits.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    pending_ref = db.collection("pending_registrations").document(email)
    pending_doc = pending_ref.get()

    if not pending_doc.exists:
        raise HTTPException(status_code=400, detail="No OTP request found. Request OTP again.")

    data = pending_doc.to_dict()

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
        pending_ref.update({"verifyAttempts": attempts + 1})
        raise HTTPException(status_code=400, detail="Incorrect OTP.")

    password = data.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="OTP data corrupted. Request OTP again.")

    existing_user = None
    try:
        existing_user = firebase_auth.get_user_by_email(email)
    except Exception:
        existing_user = None

    if existing_user:
        uid = existing_user.uid
        firebase_auth.update_user(uid, password=password, disabled=False)
    else:
        user = firebase_auth.create_user(
            email=email,
            password=password,
            disabled=False,
        )
        uid = user.uid

    db.collection("users").document(uid).set({
        "email": email,
        "isVerified": True,
        "verifiedAt": now.isoformat(),
        "createdAt": data.get("createdAt", now.isoformat()),
    }, merge=True)

    pending_ref.update({
        "used": True,
        "usedAt": now.isoformat(),
    })

    return VerifyOtpResponse(message="Email verified ✅ Account activated.")

@router.post("/register/resend-otp", response_model=ResendOtpResponse)
def resend_otp(body: ResendOtpBody):
    email = normalize_email(body.email)

    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    existing_user = None
    try:
        existing_user = firebase_auth.get_user_by_email(email)
    except Exception:
        existing_user = None

    if existing_user:
        user_doc = db.collection("users").document(existing_user.uid).get()
        if user_doc.exists and user_doc.to_dict().get("isVerified") is True:
            raise HTTPException(status_code=400, detail="EMAIL_EXISTS")

    pending_ref = db.collection("pending_registrations").document(email)
    pending_doc = pending_ref.get()
    if not pending_doc.exists:
        raise HTTPException(status_code=400, detail="No OTP request found. Register again.")

    data = pending_doc.to_dict()
    now = datetime.now(timezone.utc)

    resend_count = int(data.get("resendCount", 0))
    if resend_count >= 3:
        raise HTTPException(status_code=429, detail="Too many resends. Try again later.")

    last_sent = data.get("lastSentAt")
    if last_sent:
        last_sent_dt = datetime.fromisoformat(last_sent)
        if (now - last_sent_dt).total_seconds() < 30:
            raise HTTPException(status_code=429, detail="Please wait 30 seconds before resending.")

    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at_iso = otp_expiry_time().isoformat()

    pending_ref.update({
        "otpHash": otp_hash,
        "expiresAt": expires_at_iso,
        "verifyAttempts": 0,
        "used": False,
        "resendCount": resend_count + 1,
        "lastSentAt": now.isoformat(),
    })

    send_otp_email(email, otp)

    return ResendOtpResponse(message="OTP resent. Check your email.")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordBody):
    email = normalize_email(body.email)

    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    try:
        user = firebase_auth.get_user_by_email(email)
    except Exception:
        return ForgotPasswordResponse(
            message="If the email exists, a reset code has been sent."
        )

    uid = user.uid
    now_iso = datetime.now(timezone.utc).isoformat()

    otp = generate_otp()
    otp_hash = hash_otp(otp)
    expires_at_iso = otp_expiry_time().isoformat()

    db.collection("password_reset_requests").document(uid).set({
        "email": email,
        "uid": uid,
        "otpHash": otp_hash,
        "expiresAt": expires_at_iso,
        "createdAt": now_iso,
        "verifyAttempts": 0,
        "used": False,
    })

    try:
        send_password_reset_otp_email(email, otp)
    except Exception:
        pass

    return ForgotPasswordResponse(
        message="If the email exists, a reset code has been sent."
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(body: ResetPasswordBody):
    email = normalize_email(body.email)
    otp_input = body.otp.strip()

    if not email.endswith("@mail.aub.edu"):
        raise HTTPException(status_code=400, detail="Only @mail.aub.edu emails are allowed.")

    if not otp_input.isdigit():
        raise HTTPException(status_code=400, detail="OTP must be 6 digits.")

    firebase_auth = get_firebase_auth()
    db = get_db()

    try:
        user = firebase_auth.get_user_by_email(email)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    uid = user.uid
    reset_ref = db.collection("password_reset_requests").document(uid)
    reset_doc = reset_ref.get()

    if not reset_doc.exists:
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    data = reset_doc.to_dict()

    if data.get("used") is True:
        raise HTTPException(status_code=400, detail="Code already used.")

    expires_at_iso = data.get("expiresAt")
    if not expires_at_iso:
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromisoformat(expires_at_iso)
    if now > expires_at:
        raise HTTPException(status_code=400, detail="Code expired.")

    otp_hash = data.get("otpHash")
    if not otp_hash or not verify_otp(otp_input, otp_hash):
        attempts = int(data.get("verifyAttempts", 0))
        reset_ref.update({"verifyAttempts": attempts + 1})
        raise HTTPException(status_code=400, detail="Invalid or expired code.")

    firebase_auth.update_user(uid, password=body.new_password)

    reset_ref.update({
        "used": True,
        "usedAt": now.isoformat(),
    })

    return ResetPasswordResponse(message="Password reset successful.")


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(body: ChangePasswordBody, user=Depends(get_current_user)):
    firebase_auth = get_firebase_auth()

    uid = user.get("uid")
    email = user.get("email")

    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if not email:
        try:
            firebase_user = firebase_auth.get_user(uid)
            email = firebase_user.email
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token.")

    if not email:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if not verify_firebase_password(email, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    firebase_auth.update_user(uid, password=body.new_password)

    return ChangePasswordResponse(message="Password changed successfully.")
