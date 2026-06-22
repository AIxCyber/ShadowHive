from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from backend.auth import get_optional_user, is_auth_enabled
from backend.database import get_session
from backend.models.company import AttackerEvent
from backend.models.user import User
from backend.utils.timezone import format_dt, get_user_tz

router = APIRouter(prefix="/api/threats", tags=["threats"])


@router.get("")
async def list_threats(
    request: Request,
    severity: str | None = Query(None),
    tactic: str | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User | None = Depends(get_optional_user),
):
    async for db in get_session():
        stmt = select(AttackerEvent).order_by(AttackerEvent.detected_at.desc())
        if current_user and is_auth_enabled() and current_user.role != "admin":
            stmt = stmt.where(AttackerEvent.user_id == current_user.id)
        if severity:
            stmt = stmt.where(AttackerEvent.severity == severity)
        if tactic:
            stmt = stmt.where(AttackerEvent.mitre_tactic == tactic)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    tz = get_user_tz(request)
    events = []
    for e in rows:
        events.append(
            {
                "threat_id": str(e.id),
                "severity": e.severity or "medium",
                "tactic": e.mitre_tactic or "Unknown",
                "technique": e.mitre_technique_id or "Unknown",
                "confidence": float(e.confidence_score) if e.confidence_score else 0,
                "source_ip": e.source_ip,
                "detected_at": format_dt(e.detected_at, tz),
            }
        )
    return events[:limit]
