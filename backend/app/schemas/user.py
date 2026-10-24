"""User request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Schema for registering a new user."""

    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.STUDENT


class UserLogin(BaseModel):
    """Schema for user login credentials."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Public user profile schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    full_name: str
    institution_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """JWT bearer token response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
