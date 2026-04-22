"""
ChromaDB-based user storage service.
Handles user registration, authentication, and profile management.
"""
import uuid
import json
from datetime import datetime, timezone
import hashlib
import bcrypt as _bcrypt
import chromadb
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, log_action

logger = get_logger("auth_service")


def _hash_password(password: str) -> str:
    """Hash password using bcrypt with SHA-256 pre-hash to handle any length."""
    # Pre-hash with SHA-256 to normalize length (bcrypt has 72-byte limit)
    pw_sha = hashlib.sha256(password.encode('utf-8')).hexdigest().encode('utf-8')
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(pw_sha, salt).decode('utf-8')


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    pw_sha = hashlib.sha256(password.encode('utf-8')).hexdigest().encode('utf-8')
    return _bcrypt.checkpw(pw_sha, hashed.encode('utf-8'))


class UserService:
    """ChromaDB-backed user and profile management service."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.CHROMADB_PATH)
        self.users_collection = self.client.get_or_create_collection(
            name="users",
            metadata={"description": "User accounts with credentials"}
        )
        self.profiles_collection = self.client.get_or_create_collection(
            name="profiles",
            metadata={"description": "User financial profiles"}
        )
        log_action(logger, "info", "auth_service", "SERVICE_INITIALIZED",
                   f"chromadb_path={settings.CHROMADB_PATH} | users_count={self.users_collection.count()} | profiles_count={self.profiles_collection.count()}")

    def register_user(self, username: str, password: str, full_name: str, email: str) -> dict:
        """Register a new user. Returns user dict or raises ValueError."""
        # Check if username exists
        existing = self.users_collection.get(where={"username": username})
        if existing and existing["ids"]:
            log_action(logger, "warning", "auth_service", "REGISTRATION_FAILED",
                       f"username={username} | reason=username_already_exists")
            raise ValueError(f"Username '{username}' already exists")

        user_id = str(uuid.uuid4())
        hashed_password = _hash_password(password)
        now = datetime.now(timezone.utc).isoformat()

        user_data = {
            "username": username,
            "full_name": full_name,
            "email": email,
            "hashed_password": hashed_password,
            "created_at": now,
        }

        self.users_collection.add(
            ids=[user_id],
            documents=[json.dumps(user_data)],
            metadatas=[{"username": username, "full_name": full_name, "email": email, "created_at": now}]
        )

        # Create empty profile
        empty_profile = {
            "annual_income": 0, "monthly_income": 0, "credit_score": 0,
            "employment_months": 0, "employer_name": "", "existing_loans": 0,
            "existing_emi_amount": 0, "credit_utilization": 0, "city": "",
            "age": 0, "loan_type_interest": "", "requested_amount": 0,
            "requested_tenure_months": 0, "profile_complete": False,
            "updated_at": now
        }
        self.profiles_collection.add(
            ids=[user_id],
            documents=[json.dumps(empty_profile)],
            metadatas=[{"user_id": user_id, "profile_complete": "false", "updated_at": now}]
        )

        log_action(logger, "info", "auth_service", "USER_REGISTERED",
                   f"user_id={user_id} | username={username} | timestamp={now}")

        return {"user_id": user_id, "username": username, "full_name": full_name, "email": email}

    def authenticate_user(self, username: str, password: str) -> dict:
        """Authenticate a user. Returns user dict or raises ValueError."""
        results = self.users_collection.get(where={"username": username}, include=["documents", "metadatas"])

        if not results["ids"]:
            log_action(logger, "warning", "auth_service", "LOGIN_FAILED",
                       f"username={username} | reason=user_not_found")
            raise ValueError("Invalid username or password")

        user_id = results["ids"][0]
        user_data = json.loads(results["documents"][0])
        metadata = results["metadatas"][0]

        if not _verify_password(password, user_data["hashed_password"]):
            log_action(logger, "warning", "auth_service", "LOGIN_FAILED",
                       f"username={username} | reason=invalid_password")
            raise ValueError("Invalid username or password")

        log_action(logger, "info", "auth_service", "LOGIN_SUCCESS",
                   f"user_id={user_id} | username={username}")

        return {
            "user_id": user_id,
            "username": metadata["username"],
            "full_name": metadata["full_name"],
            "email": metadata["email"]
        }

    def update_profile(self, user_id: str, profile_data: dict) -> dict:
        """Update user's financial profile."""
        try:
            existing = self.profiles_collection.get(ids=[user_id], include=["documents"])
            if existing["ids"]:
                current = json.loads(existing["documents"][0])
            else:
                current = {}
        except Exception:
            current = {}

        # Merge updates
        updated_fields = []
        for key, value in profile_data.items():
            if value is not None and value != "":
                current[key] = value
                updated_fields.append(key)

        now = datetime.now(timezone.utc).isoformat()
        current["updated_at"] = now

        # Check if profile is complete
        required = ["annual_income", "credit_score", "employment_months", "existing_loans"]
        is_complete = all(current.get(f) and current.get(f) != 0 for f in required)
        current["profile_complete"] = is_complete

        # Calculate monthly income if annual provided
        if current.get("annual_income") and (not current.get("monthly_income") or current["monthly_income"] == 0):
            current["monthly_income"] = current["annual_income"] / 12

        try:
            self.profiles_collection.update(
                ids=[user_id],
                documents=[json.dumps(current)],
                metadatas=[{"user_id": user_id, "profile_complete": str(is_complete).lower(), "updated_at": now}]
            )
        except Exception:
            self.profiles_collection.add(
                ids=[user_id],
                documents=[json.dumps(current)],
                metadatas=[{"user_id": user_id, "profile_complete": str(is_complete).lower(), "updated_at": now}]
            )

        log_action(logger, "info", "auth_service", "PROFILE_UPDATED",
                   f"user_id={user_id} | fields_updated={updated_fields} | complete={is_complete}")

        return current

    def get_profile(self, user_id: str) -> dict:
        """Retrieve user's financial profile."""
        try:
            profile_result = self.profiles_collection.get(ids=[user_id], include=["documents"])
            user_result = self.users_collection.get(ids=[user_id], include=["metadatas"])
        except Exception as e:
            log_action(logger, "error", "auth_service", "PROFILE_RETRIEVAL_FAILED",
                       f"user_id={user_id} | error={str(e)}")
            return None

        if not profile_result["ids"]:
            log_action(logger, "warning", "auth_service", "PROFILE_NOT_FOUND",
                       f"user_id={user_id}")
            return None

        profile = json.loads(profile_result["documents"][0])
        user_meta = user_result["metadatas"][0] if user_result["ids"] else {}

        profile["user_id"] = user_id
        profile["username"] = user_meta.get("username", "")
        profile["full_name"] = user_meta.get("full_name", "")
        profile["email"] = user_meta.get("email", "")

        is_complete = profile.get("profile_complete", False)
        log_action(logger, "info", "auth_service", "PROFILE_RETRIEVED",
                   f"user_id={user_id} | complete={is_complete}")

        return profile


# Singleton instance
user_service = UserService()
