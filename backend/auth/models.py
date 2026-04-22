"""
Pydantic models for authentication and user profiles.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SignupRequest(BaseModel):
    """Request model for user registration."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1)
    email: str = Field(...)


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: str
    password: str


class ProfileUpdate(BaseModel):
    """Request model for updating financial profile."""
    annual_income: Optional[float] = None
    monthly_income: Optional[float] = None
    credit_score: Optional[int] = Field(None, ge=300, le=900)
    employment_months: Optional[int] = Field(None, ge=0)
    employer_name: Optional[str] = None
    existing_loans: Optional[int] = Field(None, ge=0)
    existing_emi_amount: Optional[float] = Field(None, ge=0)
    credit_utilization: Optional[float] = Field(None, ge=0, le=100)
    city: Optional[str] = None
    age: Optional[int] = Field(None, ge=18, le=100)
    loan_type_interest: Optional[str] = None  # home_loan, personal_loan, etc.
    requested_amount: Optional[float] = None
    requested_tenure_months: Optional[int] = None


class UserProfile(BaseModel):
    """Complete user profile returned from the system."""
    user_id: str
    username: str
    full_name: str
    email: str
    annual_income: float = 0
    monthly_income: float = 0
    credit_score: int = 0
    employment_months: int = 0
    employer_name: str = ""
    existing_loans: int = 0
    existing_emi_amount: float = 0
    credit_utilization: float = 0
    city: str = ""
    age: int = 0
    loan_type_interest: str = ""
    requested_amount: float = 0
    requested_tenure_months: int = 0
    profile_complete: bool = False
    created_at: str = ""
    updated_at: str = ""


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    full_name: str


class AuthResponse(BaseModel):
    """Generic auth response."""
    success: bool
    message: str
    data: Optional[dict] = None
