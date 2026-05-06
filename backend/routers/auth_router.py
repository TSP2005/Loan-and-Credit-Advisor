"""
Authentication router: signup (2-step OTP), login endpoints.
"""
import random
import string
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, status
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.models import SignupRequest, LoginRequest, TokenResponse, AuthResponse
from auth.service import user_service
from auth.jwt_handler import create_access_token
from logger import get_logger, log_action

logger = get_logger("auth_router")
router = APIRouter(prefix="/auth", tags=["Authentication"])

# ─── In-memory OTP store ──────────────────────────────────────────────────────
# { email: { otp, expires_at, attempts, pending_user } }
_otp_store: dict = {}
OTP_TTL_MINUTES = 10
MAX_ATTEMPTS = 3


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _is_otp_valid(record: dict, submitted_otp: str) -> tuple[bool, str]:
    if datetime.now(timezone.utc) > record["expires_at"]:
        return False, "OTP expired. Please request a new one."
    if record["attempts"] >= MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Please request a new OTP."
    if record["otp"] != submitted_otp:
        record["attempts"] += 1
        remaining = MAX_ATTEMPTS - record["attempts"]
        return False, f"Incorrect OTP. {remaining} attempt(s) remaining."
    return True, "OK"


# ─── Step 1: Initiate signup — validate & send OTP ───────────────────────────
@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """Validate signup data and send OTP to email. Does NOT create account yet."""
    log_action(logger, "info", "auth_router", "SIGNUP_INITIATE",
               f"username={request.username} | email={request.email}")
    try:
        # Check username / email availability before sending OTP
        user_service.check_availability(request.username, request.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    otp = _generate_otp()
    _otp_store[request.email] = {
        "otp": otp,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        "attempts": 0,
        "pending_user": {
            "username": request.username,
            "password": request.password,
            "full_name": request.full_name,
            "email": request.email,
        },
    }

    # Send OTP email
    from email_service import send_otp_email
    sent = send_otp_email(request.email, otp, request.full_name)
    if not sent:
        # Dev fallback: log OTP if email fails (remove in production)
        log_action(logger, "warning", "auth_router", "OTP_EMAIL_FAILED",
                   f"email={request.email} | otp={otp} (logged for dev)")

    log_action(logger, "info", "auth_router", "OTP_SENT",
               f"email={request.email} | expires_in={OTP_TTL_MINUTES}m")
    return AuthResponse(
        success=True,
        message=f"Verification code sent to {request.email}",
        data={"email": request.email},
    )


# ─── Step 2: Verify OTP — create account & return token ─────────────────────
@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(body: dict):
    """Verify OTP and create the user account."""
    email = body.get("email", "").strip().lower()
    submitted_otp = body.get("otp", "").strip()

    record = _otp_store.get(email)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending verification for this email. Please sign up first.",
        )

    valid, msg = _is_otp_valid(record, submitted_otp)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # OTP valid — create account
    pending = record["pending_user"]
    try:
        user = user_service.register_user(
            username=pending["username"],
            password=pending["password"],
            full_name=pending["full_name"],
            email=pending["email"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_action(logger, "error", "auth_router", "REGISTER_ERROR", str(e))
        raise HTTPException(status_code=500, detail="Account creation failed")

    # Clean up OTP store
    _otp_store.pop(email, None)

    token = create_access_token(data={"sub": user["user_id"], "username": user["username"]})
    log_action(logger, "info", "auth_router", "OTP_VERIFIED_ACCOUNT_CREATED",
               f"user_id={user['user_id']} | username={user['username']}")
    return TokenResponse(
        access_token=token,
        user_id=user["user_id"],
        username=user["username"],
        full_name=user["full_name"],
    )


# ─── Resend OTP ───────────────────────────────────────────────────────────────
@router.post("/resend-otp", response_model=AuthResponse)
async def resend_otp(body: dict):
    """Resend a fresh OTP to the email."""
    email = body.get("email", "").strip().lower()
    record = _otp_store.get(email)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending signup for this email.",
        )

    new_otp = _generate_otp()
    record["otp"] = new_otp
    record["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    record["attempts"] = 0

    from email_service import send_otp_email
    send_otp_email(email, new_otp, record["pending_user"]["full_name"])
    log_action(logger, "info", "auth_router", "OTP_RESENT", f"email={email}")
    return AuthResponse(success=True, message=f"New code sent to {email}")


# ─── Login ────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate an existing user."""
    log_action(logger, "info", "auth_router", "LOGIN_ATTEMPT",
               f"username={request.username}")
    try:
        user = user_service.authenticate_user(request.username, request.password)
        token = create_access_token(data={"sub": user["user_id"], "username": user["username"]})
        log_action(logger, "info", "auth_router", "LOGIN_SUCCESS",
                   f"user_id={user['user_id']}")
        return TokenResponse(
            access_token=token,
            user_id=user["user_id"],
            username=user["username"],
            full_name=user["full_name"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Login failed")
