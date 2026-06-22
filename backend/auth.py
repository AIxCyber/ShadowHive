import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models.user import User
from backend.utils.config import Config

logger = logging.getLogger("shadowhive")

security = HTTPBearer(auto_error=False)

# ── Password policy ─────────────────────────────────────────────────────────


def validate_password(password: str) -> list[str]:
    errors: list[str] = []
    min_len = Config.get("auth.password_policy.min_length", 8)
    if len(password) < min_len:
        errors.append(f"Password must be at least {min_len} characters long")
    return errors


# ── Auth mode check ─────────────────────────────────────────────────────────


def is_auth_enabled() -> bool:
    return Config.get("auth.enabled", False)


def auth_mode() -> str:
    return Config.get("auth.mode", "none")


# ── Password hashing (PBKDF2-HMAC-SHA256) ──────────────────────────────────

_ITERATIONS = 600_000


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"{salt}${base64.b64encode(dk).decode()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, b64hash = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
        return hmac.compare_digest(base64.b64decode(b64hash), dk)
    except (ValueError, TypeError, AttributeError):
        return False


# ── JWT implementation (no external deps) ──────────────────────────────────

_JWT_SECRET_CACHE: str | None = None
_EPHEMERAL_SECRET = False


def validate_jwt_config() -> list[str]:
    warnings: list[str] = []
    secret = Config.get("auth.jwt.secret", "")
    min_len = Config.get("auth.jwt.min_secret_length", 32)
    if not secret:
        warnings.append(
            "JWT secret not configured — using ephemeral key. "
            "Set auth.jwt.secret in config for persistent sessions."
        )
    elif len(secret) < min_len:
        warnings.append(
            f"JWT secret is too short ({len(secret)} chars, minimum {min_len}). "
            "Generate a strong secret with: openssl rand -base64 32"
        )
    return warnings


def validate_required_config() -> list[str]:
    warnings: list[str] = []
    if not Config.get("database.postgresql.password", ""):
        warnings.append(
            "PostgreSQL password not configured — set POSTGRES_PASSWORD in .env "
            "or database.postgresql.password in config."
        )
    if not Config.get("database.neo4j.password", ""):
        warnings.append(
            "Neo4j password not configured — set NEO4J_PASSWORD in .env "
            "or database.neo4j.password in config."
        )
    smtp_host = Config.get("auth.smtp.host", "")
    smtp_user = Config.get("auth.smtp.username", "")
    smtp_pass = Config.get("auth.smtp.password", "")
    if smtp_host and not (smtp_user and smtp_pass):
        warnings.append(
            "SMTP host is configured but username/password are missing. "
            "Password reset emails will fail. Set SMTP_USERNAME and SMTP_PASSWORD."
        )
    return warnings


def _jwt_secret() -> str:
    global _JWT_SECRET_CACHE, _EPHEMERAL_SECRET
    if _JWT_SECRET_CACHE is not None:
        return _JWT_SECRET_CACHE
    secret = Config.get("auth.jwt.secret", "")
    if not secret:
        secret = secrets.token_hex(32)
        _EPHEMERAL_SECRET = True
        logger.warning(
            "JWT secret not configured — using ephemeral key. "
            "Set auth.jwt.secret in config for persistent sessions."
        )
    _JWT_SECRET_CACHE = secret
    return secret


def _jwt_algorithm() -> str:
    return Config.get("auth.jwt.algorithm", "HS256")


def _access_token_expire() -> int:
    return Config.get("auth.jwt.access_token_expire_minutes", 60)


def _refresh_token_expire() -> int:
    return Config.get("auth.jwt.refresh_token_expire_days", 30)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _base64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _jwt_header() -> str:
    return _base64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())


def create_token(payload: dict, expires_delta: timedelta) -> str:
    header = _jwt_header()
    payload = {**payload, "exp": int(time.time()) + int(expires_delta.total_seconds())}
    payload_b64 = _base64url_encode(json.dumps(payload, default=str).encode())
    signature = hmac.new(
        _jwt_secret().encode(),
        f"{header}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = _base64url_encode(signature)
    return f"{header}.{payload_b64}.{sig_b64}"


def create_access_token(user_id: str, role: str) -> str:
    return create_token(
        {"sub": user_id, "role": role, "type": "access"},
        timedelta(minutes=_access_token_expire()),
    )


def create_refresh_token(user_id: str) -> str:
    return create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=_refresh_token_expire()),
    )


def decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    header_b64, payload_b64, sig_b64 = parts

    expected_sig = hmac.new(
        _jwt_secret().encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    actual_sig = _base64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature")

    payload = json.loads(_base64url_decode(payload_b64))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    return payload


# ── Dependencies ────────────────────────────────────────────────────────────


async def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    if not is_auth_enabled():
        return None
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except (ValueError, Exception):
        return None


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not is_auth_enabled():
        return {"sub": "", "role": "admin"}

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


def require_role(required: str):
    async def role_checker(payload: dict = Depends(require_auth)) -> dict:
        role = payload.get("role", "")
        role_level = {"admin": 3, "user": 2, "viewer": 1}
        if role_level.get(role, 0) < role_level.get(required, 0):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return payload

    return role_checker


async def require_api_key(authorization: str | None = Header(None, alias="Authorization")):
    if not is_auth_enabled() or auth_mode() != "api_key":
        return True
    expected = Config.get("auth.api_key", "")
    if not expected:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


async def get_current_user(
    payload: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> User:
    user_id = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


async def get_optional_user(
    payload: dict = Depends(optional_auth),
    db: AsyncSession = Depends(get_session),
) -> User | None:
    if not payload or not payload.get("sub"):
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    return result.scalar_one_or_none()


# ── Account lockout ─────────────────────────────────────────────────────────


def _lockout_max_attempts() -> int:
    return Config.get("auth.lockout.max_attempts", 5)


def _lockout_minutes() -> int:
    return Config.get("auth.lockout.lockout_minutes", 15)


def is_account_locked(user: User) -> bool:
    if not user.locked_until:
        return False
    return datetime.now(UTC).replace(tzinfo=None) < user.locked_until


def _naive_utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def record_failed_login(user: User, db_session) -> None:
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= _lockout_max_attempts():
        user.locked_until = _naive_utcnow() + timedelta(minutes=_lockout_minutes())
        logger.warning(f"Account locked: {user.email} until {user.locked_until}")
    db_session.add(user)


def reset_login_attempts(user: User, db_session) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = _naive_utcnow()
    db_session.add(user)
