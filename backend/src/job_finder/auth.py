from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import BaseModel, Field, field_validator

from job_finder.database import DatabaseStore


SESSION_COOKIE = "job_finder_session"
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthUser(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=100)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _EMAIL.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class AuthSession(BaseModel):
    user: AuthUser
    token: str
    expires_at: datetime


class AuthenticationError(ValueError):
    pass


class AuthService:
    def __init__(self, database: DatabaseStore, *, session_days: int = 30) -> None:
        self.database = database
        self.session_days = session_days
        self.passwords = PasswordHasher()

    def register(self, request: RegisterRequest) -> AuthSession:
        password_hash = self.passwords.hash(request.password)
        try:
            raw = self.database.register_user(
                email=request.email,
                display_name=request.display_name,
                password_hash=password_hash,
            )
        except ValueError as exc:
            raise AuthenticationError(str(exc)) from exc
        return self._new_session(_public_user(raw))

    def login(self, request: LoginRequest) -> AuthSession:
        raw = self.database.find_user_by_email(request.email)
        password_hash = raw.get("password_hash") if raw else None
        if not password_hash:
            raise AuthenticationError("Invalid email or password")
        try:
            self.passwords.verify(password_hash, request.password)
        except (VerifyMismatchError, InvalidHashError):
            raise AuthenticationError("Invalid email or password") from None
        return self._new_session(_public_user(raw))

    def resolve(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        raw = self.database.resolve_auth_session(_token_hash(token), datetime.now(timezone.utc))
        return _public_user(raw) if raw else None

    def logout(self, token: str | None) -> None:
        if token:
            self.database.delete_auth_session(_token_hash(token))

    def _new_session(self, user: AuthUser) -> AuthSession:
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.session_days)
        self.database.create_auth_session(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=expires_at,
        )
        return AuthSession(user=user, token=token, expires_at=expires_at)


def _public_user(raw: dict | None) -> AuthUser:
    if raw is None:
        raise AuthenticationError("User not found")
    return AuthUser.model_validate({
        "id": raw["id"],
        "email": raw["email"],
        "display_name": raw["display_name"],
        "created_at": raw["created_at"],
    })


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
