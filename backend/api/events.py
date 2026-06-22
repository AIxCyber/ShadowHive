import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_optional_user, is_auth_enabled
from backend.database import get_session
from backend.models.company import AttackerEvent
from backend.models.user import User
from backend.neo4j_client import _driver as neo4j_driver
from backend.services.graph_builder import record_event

logger = logging.getLogger("shadowhive.events")

router = APIRouter(prefix="/api", tags=["events"])


class IngestEvent(BaseModel):
    source_ip: str = Field(default="unknown", max_length=45)
    event_type: str = Field(default="unknown", max_length=100)
    command: str | None = None
    session_id: str | None = None
    mitre_technique_id: str | None = None
    mitre_tactic: str | None = None
    confidence_score: str | None = None
    severity: str = Field(default="medium", max_length=20)
    detected_at: str | None = None
    company_id: str | None = None


class IngestBatch(BaseModel):
    events: list[IngestEvent]


@router.post("/events", status_code=201)
async def ingest_events(
    batch: IngestBatch,
    current_user: User | None = Depends(get_optional_user),
):
    if not batch.events:
        raise HTTPException(400, "No events provided")

    user_id = None
    if current_user and is_auth_enabled():
        user_id = current_user.id

    async for db in get_session():
        ids = []
        for ev in batch.events:
            detected_at = datetime.now(UTC).replace(tzinfo=None)
            if ev.detected_at:
                try:
                    dt = datetime.fromisoformat(ev.detected_at.replace("Z", "+00:00"))
                    detected_at = dt.replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            company_id = uuid.UUID(ev.company_id) if ev.company_id else uuid.uuid4()

            event = AttackerEvent(
                id=uuid.uuid4(),
                user_id=user_id,
                company_id=company_id,
                source_ip=ev.source_ip,
                event_type=ev.event_type,
                command=ev.command or None,
                session_id=ev.session_id or None,
                mitre_technique_id=ev.mitre_technique_id or None,
                mitre_tactic=ev.mitre_tactic or None,
                confidence_score=ev.confidence_score or None,
                severity=ev.severity,
                detected_at=detected_at,
            )
            db.add(event)
            ids.append(str(event.id))

        await db.commit()

        if neo4j_driver:
            try:
                async with neo4j_driver.session() as neo4j_session:
                    for ev in batch.events:
                        dt_val = ev.detected_at or detected_at.isoformat()
                        await record_event(
                            neo4j_session,
                            event_id=str(ids[len(ids) - len(batch.events) + batch.events.index(ev)]),
                            eventid=ev.event_type,
                            source_ip=ev.source_ip,
                            timestamp=dt_val,
                            session_id=ev.session_id or f"session-{ev.source_ip}",
                            command=ev.command,
                            message=ev.command or ev.event_type,
                            mitre_technique_id=ev.mitre_technique_id,
                            mitre_technique_name=ev.mitre_technique_id,
                            mitre_tactic=ev.mitre_tactic,
                            mitre_tactic_name=ev.mitre_tactic,
                        )
            except Exception as e:
                logger.warning(f"Failed to sync event to Neo4j graph: {e}")

        return {"ingested": len(ids), "ids": ids}
