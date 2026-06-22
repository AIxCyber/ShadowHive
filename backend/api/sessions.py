from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from backend.auth import get_optional_user, is_auth_enabled
from backend.database import get_session
from backend.models.company import AttackerEvent
from backend.models.user import User
from backend.utils.timezone import format_dt, get_user_tz

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    request: Request,
    min_risk: int | None = Query(None, ge=0, le=5),
    limit: int = Query(50, le=200),
    current_user: User | None = Depends(get_optional_user),
):
    async for db in get_session():
        stmt = (
            select(
                AttackerEvent.session_id,
                AttackerEvent.source_ip,
                AttackerEvent.event_type,
                AttackerEvent.severity,
                AttackerEvent.detected_at,
                AttackerEvent.command,
            )
            .where(AttackerEvent.session_id.isnot(None))
            .order_by(AttackerEvent.detected_at.desc())
        )
        if current_user and is_auth_enabled() and current_user.role != "admin":
            stmt = stmt.where(AttackerEvent.user_id == current_user.id)
        result = await db.execute(stmt)
        rows = result.all()

    tz = get_user_tz(request)
    seen = {}
    for row in rows:
        sid = row.session_id
        if sid not in seen:
            risk_map = {"low": 1, "medium": 3, "high": 4, "critical": 5}
            seen[sid] = {
                "session_id": sid,
                "source_ip": row.source_ip,
                "protocol": row.event_type,
                "risk_score": risk_map.get(row.severity, 0),
                "commands_executed": 0,
                "duration_minutes": 0,
                "bytes_sent": 0,
                "bytes_received": 0,
                "last_seen": format_dt(row.detected_at, tz),
                "_first_seen": row.detected_at,
                "_last_seen": row.detected_at,
            }
        seen[sid]["commands_executed"] += 1 if row.command else 0
        if row.detected_at:
            if not seen[sid]["_first_seen"] or row.detected_at < seen[sid]["_first_seen"]:
                seen[sid]["_first_seen"] = row.detected_at
            if not seen[sid]["_last_seen"] or row.detected_at > seen[sid]["_last_seen"]:
                seen[sid]["_last_seen"] = row.detected_at

    sessions = []
    for s in seen.values():
        if s["_first_seen"] and s["_last_seen"]:
            s["duration_minutes"] = round((s["_last_seen"] - s["_first_seen"]).total_seconds() / 60)
        del s["_first_seen"], s["_last_seen"]
        sessions.append(s)
    if min_risk:
        sessions = [s for s in sessions if s["risk_score"] >= min_risk]
    return sessions[:limit]
