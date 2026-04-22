"""
Authentication router: signup and login endpoints.
"""
from fastapi import APIRouter, HTTPException, status
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.models import SignupRequest, LoginRequest, TokenResponse, AuthResponse
from auth.service import user_service
from auth.jwt_handler import create_access_token
from logger import get_logger, log_action

logger = get_logger("auth_router")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    """Register a new user."""
    log_action(logger, "info", "auth_router", "ENDPOINT_HIT",
               f"POST /auth/signup | username={request.username}")
    try:
        user = user_service.register_user(
            username=request.username,
            password=request.password,
            full_name=request.full_name,
            email=request.email
        )

        token = create_access_token(data={
            "sub": user["user_id"],
            "username": user["username"]
        })

        log_action(logger, "info", "auth_router", "SIGNUP_SUCCESS",
                   f"user_id={user['user_id']} | username={user['username']}")

        return TokenResponse(
            access_token=token,
            user_id=user["user_id"],
            username=user["username"],
            full_name=user["full_name"]
        )
    except ValueError as e:
        log_action(logger, "warning", "auth_router", "SIGNUP_FAILED",
                   f"username={request.username} | error={str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_action(logger, "error", "auth_router", "SIGNUP_ERROR",
                   f"username={request.username} | error={str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed")


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate an existing user."""
    log_action(logger, "info", "auth_router", "ENDPOINT_HIT",
               f"POST /auth/login | username={request.username}")
    try:
        user = user_service.authenticate_user(
            username=request.username,
            password=request.password
        )

        token = create_access_token(data={
            "sub": user["user_id"],
            "username": user["username"]
        })

        log_action(logger, "info", "auth_router", "LOGIN_SUCCESS",
                   f"user_id={user['user_id']} | username={user['username']}")

        return TokenResponse(
            access_token=token,
            user_id=user["user_id"],
            username=user["username"],
            full_name=user["full_name"]
        )
    except ValueError as e:
        log_action(logger, "warning", "auth_router", "LOGIN_FAILED",
                   f"username={request.username} | error={str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        log_action(logger, "error", "auth_router", "LOGIN_ERROR",
                   f"username={request.username} | error={str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed")
