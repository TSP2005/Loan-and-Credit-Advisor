"""
JWT token creation and validation.
"""
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("jwt_handler")
security = HTTPBearer()


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    log_action(logger, "info", "jwt_handler", "TOKEN_CREATED",
               f"user_id={data.get('sub', 'unknown')} | expires_in={settings.ACCESS_TOKEN_EXPIRE_MINUTES}min")
    return token


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            log_action(logger, "warning", "jwt_handler", "TOKEN_INVALID", "missing sub claim")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        log_action(logger, "debug", "jwt_handler", "TOKEN_VALIDATED",
                   f"user_id={user_id} | valid=true")
        return payload
    except JWTError as e:
        log_action(logger, "warning", "jwt_handler", "TOKEN_VALIDATION_FAILED",
                   f"error={str(e)} | valid=false")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired or invalid")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Dependency to get the current authenticated user from JWT."""
    token = credentials.credentials
    payload = verify_token(token)
    return payload
