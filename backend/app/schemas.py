import uuid
from datetime import date, datetime
from typing import Optional, Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.validators import US_STATES


class PatientBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    date_of_birth: date
    sex: str
    phone_number: str = Field(..., min_length=10, max_length=10)
    email: Optional[EmailStr] = None

    address_line_1: str = Field(..., min_length=1, max_length=255)
    address_line_2: Optional[str] = None
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str = Field(..., min_length=5, max_length=10)

    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"

    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("sex")
    @classmethod
    def check_sex(cls, v):
        if v not in {"Male", "Female", "Other", "Decline to Answer"}:
            raise ValueError("sex must be one of: Male, Female, Other, Decline to Answer")
        return v

    @field_validator("state")
    @classmethod
    def check_state(cls, v):
        v = v.upper()
        if v not in US_STATES:
            raise ValueError("state must be a valid 2-letter US state abbreviation")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v):
        if v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return v


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional - partial updates allowed per spec."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class PatientOut(PatientBase):
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Envelope(BaseModel):
    data: Optional[Any] = None
    error: Optional[str] = None
