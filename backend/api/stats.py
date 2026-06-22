import math
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text

from backend.auth import get_optional_user, is_auth_enabled
from backend.database import get_session
from backend.models.company import AttackerEvent
from backend.models.user import User
from backend.services.task_manager import task_manager

router = APIRouter(prefix="/api", tags=["stats"])


class TimelineRange(StrEnum):
    H24 = "24h"
    D7 = "7d"
    D30 = "30d"
    ALL = "all"


async def _build_timeline(now: datetime, timeline_range: TimelineRange, user_filter, current_user, db):
    if timeline_range == TimelineRange.H24:
        buckets = 24
        delta = timedelta(hours=1)
        fmt = "%H:00"
    elif timeline_range == TimelineRange.D7:
        buckets = 7
        delta = timedelta(days=1)
        fmt = "%b %d"
    elif timeline_range == TimelineRange.D30:
        buckets = 30
        delta = timedelta(days=1)
        fmt = "%b %d"
    else:
        min_max_sql = text(
            "SELECT MIN(detected_at), MAX(detected_at) FROM attacker_events"
            + (" WHERE user_id = :uid" if user_filter else "")
        )
        min_max = (await db.execute(min_max_sql, {"uid": str(current_user.id)} if user_filter else {})).one()
        overall_start = min_max[0]
        if isinstance(overall_start, str):
            try:
                overall_start = datetime.fromisoformat(overall_start)
            except (ValueError, TypeError):
                overall_start = now
        overall_start = overall_start or now
        overall_end = min_max[1]
        if isinstance(overall_end, str):
            try:
                overall_end = datetime.fromisoformat(overall_end)
            except (ValueError, TypeError):
                overall_end = now
        overall_end = (overall_end or now) + timedelta(hours=1)
        span_days = max(math.ceil((overall_end - overall_start).total_seconds() / 86400), 1)
        if span_days <= 30:
            delta = timedelta(days=1)
            fmt = "%b %d"
        elif span_days <= 180:
            delta = timedelta(days=7)
            fmt = "%b %d"
        else:
            delta = timedelta(days=30)
            fmt = "%b %Y"
        buckets = max(int(span_days / (delta.days or 1)), 1)

    if timeline_range == TimelineRange.ALL:
        timeline = []
        for i in range(buckets):
            bucket_start = overall_start + delta * i
            bucket_end = overall_start + delta * (i + 1)
            sql = """
                SELECT
                    COUNT(*) AS threats,
                    COUNT(*) FILTER (WHERE severity = 'critical') AS critical
                FROM attacker_events
                WHERE detected_at >= :start AND detected_at < :end
            """
            params = {"start": bucket_start, "end": bucket_end}
            if user_filter:
                sql += " AND user_id = :uid"
                params["uid"] = str(current_user.id)
            result = await db.execute(text(sql), params)
            row = result.one()
            timeline.append(
                {
                    "hour": bucket_start.strftime(fmt),
                    "threats": row[0] or 0,
                    "critical": row[1] or 0,
                }
            )
        return timeline

    timeline = []
    for i in range(buckets - 1, -1, -1):
        bucket_start = now - delta * (i + 1)
        bucket_end = now - delta * i
        sql = """
            SELECT
                COUNT(*) AS threats,
                COUNT(*) FILTER (WHERE severity = 'critical') AS critical
            FROM attacker_events
            WHERE detected_at >= :start AND detected_at < :end
        """
        params = {"start": bucket_start, "end": bucket_end}
        if user_filter:
            sql += " AND user_id = :uid"
            params["uid"] = str(current_user.id)
        result = await db.execute(text(sql), params)
        row = result.one()
        timeline.append(
            {
                "hour": bucket_start.strftime(fmt),
                "threats": row[0] or 0,
                "critical": row[1] or 0,
            }
        )

    return timeline


@router.get("/stats")
async def get_stats(
    timeline_range: TimelineRange = Query(default=TimelineRange.H24, alias="range"),
    current_user: User | None = Depends(get_optional_user),
):
    now = datetime.now(UTC).replace(tzinfo=None)
    twenty_four_hours_ago = now - timedelta(hours=24)
    one_hour_ago = now - timedelta(hours=1)

    user_filter = []
    if current_user and is_auth_enabled() and current_user.role != "admin":
        user_filter = [AttackerEvent.user_id == current_user.id]

    async for db in get_session():
        total_query = select(func.count(AttackerEvent.id))
        if user_filter:
            total_query = total_query.where(*user_filter)
        total_threats_result = await db.execute(total_query)
        threat_events_total = total_threats_result.scalar() or 0

        new_hour_query = select(func.count(AttackerEvent.id)).where(AttackerEvent.detected_at >= one_hour_ago)
        if user_filter:
            new_hour_query = new_hour_query.where(*user_filter)
        new_hour_result = await db.execute(new_hour_query)
        threat_events_new_hour = new_hour_result.scalar() or 0

        unique_ips_query = select(func.count(func.distinct(AttackerEvent.source_ip))).where(
            AttackerEvent.detected_at >= twenty_four_hours_ago
        )
        if user_filter:
            unique_ips_query = unique_ips_query.where(*user_filter)
        unique_ips_result = await db.execute(unique_ips_query)
        unique_ips_24h = unique_ips_result.scalar() or 0

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        commands_query = select(func.count(AttackerEvent.id)).where(
            AttackerEvent.detected_at >= today_start,
            AttackerEvent.command.isnot(None),
        )
        if user_filter:
            commands_query = commands_query.where(*user_filter)
        commands_result = await db.execute(commands_query)
        total_commands_today = commands_result.scalar() or 0

        active_sessions_query = select(func.count(func.distinct(AttackerEvent.session_id))).where(
            AttackerEvent.detected_at >= one_hour_ago
        )
        if user_filter:
            active_sessions_query = active_sessions_query.where(*user_filter)
        active_sessions_result = await db.execute(active_sessions_query)
        active_sessions = active_sessions_result.scalar() or 0

        high_risk_query = select(func.count(func.distinct(AttackerEvent.session_id))).where(
            AttackerEvent.severity.in_(["high", "critical"]),
            AttackerEvent.detected_at >= one_hour_ago,
        )
        if user_filter:
            high_risk_query = high_risk_query.where(*user_filter)
        high_risk_result = await db.execute(high_risk_query)
        high_risk_sessions = high_risk_result.scalar() or 0

        tactics_query = select(AttackerEvent.mitre_tactic).where(
            AttackerEvent.mitre_tactic.isnot(None)
        ).distinct()
        if user_filter:
            tactics_query = tactics_query.where(*user_filter)
        tactics_result = await db.execute(tactics_query)
        raw_tactics = [row[0] for row in tactics_result.fetchall()]

        def _normalize_tactic(t: str) -> str:
            return t.strip().lower().replace(" ", "-").replace("&", "and")

        normalized = list(set(_normalize_tactic(t) for t in raw_tactics))

        MITRE_TACTICS = {
            "reconnaissance", "resource-development", "initial-access",
            "execution", "persistence", "privilege-escalation",
            "defense-evasion", "credential-access", "discovery",
            "lateral-movement", "collection", "command-and-control",
            "exfiltration", "impact",
        }
        mitre_tactics_mapped = len(MITRE_TACTICS & set(normalized))
        mitre_coverage_pct = min(round((mitre_tactics_mapped / len(MITRE_TACTICS)) * 100), 100) if MITRE_TACTICS else 0

        techniques_query = select(func.count(func.distinct(AttackerEvent.mitre_technique_id))).where(
            AttackerEvent.mitre_technique_id.isnot(None)
        )
        if user_filter:
            techniques_query = techniques_query.where(*user_filter)
        techniques_result = await db.execute(techniques_query)
        techniques_identified = techniques_result.scalar() or 0

        avg_conf_query = select(AttackerEvent.confidence_score)
        if user_filter:
            avg_conf_query = avg_conf_query.where(AttackerEvent.user_id == current_user.id)
        avg_conf_result = await db.execute(avg_conf_query)
        raw_scores = [float(r[0]) for r in avg_conf_result if r[0] not in (None, "")]
        avg_confidence = round((sum(raw_scores) / len(raw_scores)) * 100) if raw_scores else 0

        files_query = select(func.count(AttackerEvent.id)).where(
            AttackerEvent.detected_at >= today_start,
            AttackerEvent.event_type == "file_access",
        )
        if user_filter:
            files_query = files_query.where(*user_filter)
        files_result = await db.execute(files_query)
        files_accessed_today = files_result.scalar() or 0

        timeline = await _build_timeline(now, timeline_range, user_filter, current_user, db)

    tasks = await task_manager.list_tasks(limit=1000)
    active_companies = sum(1 for t in tasks if t.status.value == "completed")

    return {
        "active_companies": active_companies,
        "threat_events_total": threat_events_total,
        "threat_events_new_hour": threat_events_new_hour,
        "active_sessions": active_sessions,
        "high_risk_sessions": high_risk_sessions,
        "mitre_coverage_pct": mitre_coverage_pct,
        "mitre_tactics_mapped": mitre_tactics_mapped,
        "techniques_identified": techniques_identified,
        "avg_confidence": avg_confidence,
        "total_commands_today": total_commands_today,
        "files_accessed_today": files_accessed_today,
        "unique_ips_24h": unique_ips_24h,
        "threat_timeline": timeline,
    }
