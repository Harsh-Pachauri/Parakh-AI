"""Schemas for institution and admin management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InstitutionCreate(BaseModel):
    """Schema for creating a new institution."""

    name: str = Field(..., min_length=2, max_length=255, description="Full name of the institution")
    code: str = Field(
        ..., min_length=2, max_length=50, description="Short code/acronym for the institution"
    )


class InstitutionResponse(BaseModel):
    """Schema for returning institution details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InstitutionAdminCreate(BaseModel):
    """Schema for appointing an administrator to an institution."""

    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=1, max_length=255)


class InstitutionAdminResponse(BaseModel):
    """Schema returned after appointing an institution administrator."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    institution_id: uuid.UUID
    created_at: datetime


class TeacherCreate(BaseModel):
    """Schema for an institution admin to register a teacher."""

    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=1, max_length=255)


class TeacherResponse(BaseModel):
    """Schema returned when viewing or creating a teacher within an institution."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    institution_id: uuid.UUID
    created_at: datetime
