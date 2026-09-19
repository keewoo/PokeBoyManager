import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

PSEUDO_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class UpdatePseudoRequest(BaseModel):
    pseudo: str = Field(min_length=3, max_length=32)

    @field_validator("pseudo")
    @classmethod
    def _validate_pseudo(cls, value: str) -> str:
        if not PSEUDO_PATTERN.match(value):
            raise ValueError("Le pseudo n'accepte que lettres, chiffres, tirets et underscores.")
        return value


class ProfileResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    pending_email: str | None
    pseudo: str | None
    has_avatar: bool


class ChangeEmailRequest(BaseModel):
    email: EmailStr


class ConfirmEmailChangeRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    password: str


class MessageResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    id: str
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    current: bool
