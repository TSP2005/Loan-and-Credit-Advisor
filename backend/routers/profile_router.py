"""
Profile management router: update and retrieve user profiles.
"""
from fastapi import APIRouter, HTTPException, Depends, status
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.models import ProfileUpdate, UserProfile
from auth.service import user_service
from auth.jwt_handler import get_current_user
from logger import get_logger, log_action

logger = get_logger("profile_router")
router = APIRouter(prefix="/profile", tags=["Profile"])


@router.post("/update")
async def update_profile(profile: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    """Update the authenticated user's financial profile."""
    user_id = current_user.get("sub")
    log_action(logger, "info", "profile_router", "ENDPOINT_HIT",
               f"POST /profile/update | user_id={user_id}")

    try:
        profile_data = profile.model_dump(exclude_none=True)
        updated = user_service.update_profile(user_id, profile_data)

        log_action(logger, "info", "profile_router", "PROFILE_UPDATED",
                   f"user_id={user_id} | fields_updated={list(profile_data.keys())}")

        return {"success": True, "message": "Profile updated", "profile": updated}
    except Exception as e:
        log_action(logger, "error", "profile_router", "PROFILE_UPDATE_FAILED",
                   f"user_id={user_id} | error={str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{user_id}")
async def get_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    """Retrieve a user's financial profile."""
    log_action(logger, "info", "profile_router", "ENDPOINT_HIT",
               f"GET /profile/{user_id}")

    # Users can only access their own profile
    if current_user.get("sub") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    profile = user_service.get_profile(user_id)
    if not profile:
        log_action(logger, "warning", "profile_router", "PROFILE_NOT_FOUND",
                   f"user_id={user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    log_action(logger, "info", "profile_router", "PROFILE_RETRIEVED",
               f"user_id={user_id} | complete={profile.get('profile_complete', False)}")

    return {"success": True, "profile": profile}
