import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import (
    _hash_password,
    get_current_user,
    is_auth_enabled,
)
from backend.database import get_session
from backend.models.user import User
from backend.utils.timezone import format_dt, get_user_tz

logger = logging.getLogger("shadowhive")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── Schemas ─────────────────────────────────────────────────────────────────


class CreateUserRequest(BaseModel):
    email: str
    password: str
    display_name: str
    role: str = "user"


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


# ── Dependencies ────────────────────────────────────────────────────────────


async def require_admin(user: User = Depends(get_current_user)):
    if not is_auth_enabled():
        return user
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [_user_dict(u, request) for u in users]


@router.post("/users")
async def create_user(
    body: CreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        password_hash=_hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        must_change_password=True,
        is_active=True,
        created_at=_naive_utcnow(),
    )
    db.add(user)
    await db.commit()
    logger.info(f"Admin {admin.email} created user {body.email} with role {body.role}")
    return _user_dict(user, request)


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_dict(user, request)


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id) and body.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    user.updated_at = _naive_utcnow()
    db.add(user)
    await db.commit()
    logger.info(f"Admin {admin.email} updated user {user.email}")
    return _user_dict(user, request)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    await db.delete(user)
    await db.commit()
    logger.info(f"Admin {admin.email} deleted user {user.email}")
    return {"deleted": True, "user_id": user_id}


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    import secrets

    temp_password = secrets.token_urlsafe(12)
    user.password_hash = _hash_password(temp_password)
    user.must_change_password = True
    user.updated_at = _naive_utcnow()
    db.add(user)
    await db.commit()
    logger.info(f"Admin {admin.email} reset password for user {user.email}")
    return {"message": "Password reset", "temporary_password": temp_password}


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
