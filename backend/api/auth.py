import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import (
    _hash_password,
    _verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    is_account_locked,
    is_auth_enabled,
    record_failed_login,
    reset_login_attempts,
    validate_password,
)
from backend.database import get_session
from backend.models.user import ResetToken, User
from backend.services.rate_limiter import rate_limiter
from backend.utils.config import Config
from backend.utils.timezone import format_dt, get_user_tz

logger = logging.getLogger("shadowhive")


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Seed default admin ──────────────────────────────────────────────────────

DEFAULT_ADMIN_EMAIL = "admin@shadowhive.local"
DEFAULT_ADMIN_PASSWORD = "admin123"


async def ensure_admin_exists():
    if not is_auth_enabled():
        return
    async for db in get_session():
        result = await db.execute(select(User).where(User.email == DEFAULT_ADMIN_EMAIL))
        if result.scalar_one_or_none():
            return
        # migrate old email format
        old = await db.execute(select(User).where(User.email == "shadowhive").limit(1))
        old_user = old.scalar_one_or_none()
        if old_user:
            old_user.email = DEFAULT_ADMIN_EMAIL
            await db.commit()
            logger.info("Migrated admin email: shadowhive -> admin@shadowhive.local")
            return
        admin = User(
            id=uuid.uuid4(),
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=_hash_password(DEFAULT_ADMIN_PASSWORD),
            display_name="Administrator",
            role="admin",
            must_change_password=True,
            is_active=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(admin)
        await db.commit()
        logger.info("Default admin created: admin@shadowhive.local / admin123")


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/register")
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    await rate_limiter.check(request)

    if not is_auth_enabled():
        raise HTTPException(status_code=400, detail="Auth is disabled")

    pw_errors = validate_password(body.password)
    if pw_errors:
        raise HTTPException(status_code=422, detail="; ".join(pw_errors))

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        password_hash=_hash_password(body.password),
        display_name=body.display_name,
        role="user",
        must_change_password=True,
        is_active=True,
        created_at=_naive_utcnow(),
    )
    db.add(user)
    await db.commit()
    return {"message": "User created", "user_id": str(user.id)}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    await rate_limiter.check(request)

    if not is_auth_enabled():
        raise HTTPException(status_code=400, detail="Auth is disabled")

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    if is_account_locked(user):
        remaining = (user.locked_until - _naive_utcnow()).seconds // 60
        raise HTTPException(
            status_code=429,
            detail=f"Account locked. Try again in {remaining} minutes",
        )

    if not _verify_password(body.password, user.password_hash):
        record_failed_login(user, db)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    reset_login_attempts(user, db)
    await db.commit()

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_dict(user, request),
    )


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_session)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(access_token=access, refresh_token=refresh, user=_user_dict(user, request))


@router.get("/me")
async def me(request: Request, user: User = Depends(get_current_user)):
    return _user_dict(user, request)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    await rate_limiter.check(request)

    pw_errors = validate_password(body.new_password)
    if pw_errors:
        raise HTTPException(status_code=422, detail="; ".join(pw_errors))

    if not _verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = _hash_password(body.new_password)
    user.must_change_password = False
    user.last_password_change = _naive_utcnow()
    db.add(user)
    await db.commit()
    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}

    token = secrets.token_urlsafe(48)
    expires = _naive_utcnow() + timedelta(hours=1)
    rt = ResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires_at=expires,
        used=False,
    )
    db.add(rt)
    await db.commit()

    reset_link = f"{_get_base_url()}/reset-password?token={token}"
    logger.info(f"Password reset link for {user.email}: {reset_link}")

    _try_send_email(user.email, "Password Reset", f"Reset your password here: {reset_link}")

    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(ResetToken).where(
            ResetToken.token == body.token,
            ResetToken.used == False,  # noqa: E712
            ResetToken.expires_at > _naive_utcnow(),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.password_hash = _hash_password(body.new_password)
    user.must_change_password = False
    user.last_password_change = _naive_utcnow()
    rt.used = True
    db.add(user)
    db.add(rt)
    await db.commit()
    return {"message": "Password reset successfully"}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _user_dict(user: User, request: Request | None = None) -> dict:
    tz = get_user_tz(request) if request else None
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "must_change_password": user.must_change_password,
        "is_active": user.is_active,
        "created_at": format_dt(user.created_at, tz),
        "last_login": format_dt(user.last_login, tz),
    }


def _get_base_url() -> str:
    return Config.get("server.base_url", "http://localhost:3000")


def _try_send_email(to: str, subject: str, body: str) -> None:
    smtp = Config.get("auth.smtp", {})
    if not smtp.get("host"):
        logger.info(f"[EMAIL] To: {to} | Subject: {subject} | Body: {body}")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["To"] = to
        msg["From"] = smtp.get("from", "noreply@shadowhive.local")

        with smtplib.SMTP(smtp["host"], smtp.get("port", 587)) as server:
            if smtp.get("tls", True):
                server.starttls()
            if smtp.get("username"):
                server.login(smtp["username"], smtp.get("password", ""))
            server.send_message(msg)
        logger.info(f"Password reset email sent to {to}")
    except Exception as e:
        logger.warning(f"Failed to send email to {to}: {e}")
