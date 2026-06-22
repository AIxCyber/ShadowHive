import logging

logger = logging.getLogger("shadowhive.graph")


# ── Node merge queries ───────────────────────────────────────────────────

MERGE_IP = """
MERGE (ip:AttackerIP {address: $ip})
ON CREATE SET ip.first_seen = $timestamp, ip.last_seen = $timestamp
ON MATCH SET ip.last_seen = $timestamp
RETURN id(ip) AS node_id
"""

MERGE_SESSION = """
MERGE (s:Session {session_id: $session_id})
ON CREATE SET s.first_event = $timestamp, s.last_event = $timestamp
ON MATCH SET s.last_event = $timestamp
RETURN id(s) AS node_id
"""

MERGE_EVENT = """
CREATE (e:Event {
    event_id: $event_id,
    eventid: $eventid,
    source_ip: $source_ip,
    timestamp: $timestamp,
    command: $command,
    message: $message
})
RETURN id(e) AS node_id
"""

MERGE_TECHNIQUE = """
MERGE (t:Technique {technique_id: $technique_id})
ON CREATE SET t.name = $technique_name
RETURN id(t) AS node_id
"""

MERGE_TACTIC = """
MERGE (t:Tactic {tactic: $tactic})
ON CREATE SET t.name = $tactic_name
RETURN id(t) AS node_id
"""

# ── Relationship merge queries ──────────────────────────────────────────

RELATE_IP_SESSION = """
MATCH (ip:AttackerIP {address: $ip})
MATCH (s:Session {session_id: $session_id})
MERGE (ip)-[:INITIATED]->(s)
"""

RELATE_SESSION_EVENT = """
MATCH (s:Session {session_id: $session_id})
MATCH (e:Event {event_id: $event_id})
MERGE (s)-[:CONTAINS]->(e)
"""

RELATE_EVENT_TECHNIQUE = """
MATCH (e:Event {event_id: $event_id})
MATCH (t:Technique {technique_id: $technique_id})
MERGE (e)-[:MAPS_TO]->(t)
"""

RELATE_TECHNIQUE_TACTIC = """
MATCH (t:Technique {technique_id: $technique_id})
MATCH (tc:Tactic {tactic: $tactic})
MERGE (t)-[:PART_OF]->(tc)
"""


async def record_event(neo4j_session, event_id: str, eventid: str, source_ip: str,
                        timestamp: str, session_id: str, command: str | None,
                        message: str | None, mitre_technique_id: str | None,
                        mitre_technique_name: str | None, mitre_tactic: str | None,
                        mitre_tactic_name: str | None) -> None:
    try:
        await neo4j_session.run(MERGE_IP, ip=source_ip, timestamp=timestamp)
        await neo4j_session.run(MERGE_SESSION, session_id=session_id, timestamp=timestamp)
        await neo4j_session.run(MERGE_EVENT,
            event_id=event_id, eventid=eventid, source_ip=source_ip,
            timestamp=timestamp, command=command, message=message,
        )
        await neo4j_session.run(RELATE_IP_SESSION, ip=source_ip, session_id=session_id)
        await neo4j_session.run(RELATE_SESSION_EVENT, session_id=session_id, event_id=event_id)

        if mitre_technique_id:
            await neo4j_session.run(MERGE_TECHNIQUE,
                technique_id=mitre_technique_id, technique_name=mitre_technique_name or mitre_technique_id,
            )
            await neo4j_session.run(RELATE_EVENT_TECHNIQUE,
                event_id=event_id, technique_id=mitre_technique_id,
            )

        if mitre_tactic:
            await neo4j_session.run(MERGE_TACTIC,
                tactic=mitre_tactic, tactic_name=mitre_tactic_name or mitre_tactic,
            )
            if mitre_technique_id:
                await neo4j_session.run(RELATE_TECHNIQUE_TACTIC,
                    technique_id=mitre_technique_id, tactic=mitre_tactic,
                )
    except Exception as e:
        logger.warning(f"Failed to record event in Neo4j: {e}")


ATTACK_PATH_QUERY = """
MATCH path = (ip:AttackerIP)-[:INITIATED]->(s:Session)-[:CONTAINS]->(e:Event)
OPTIONAL MATCH (e)-[:MAPS_TO]->(t:Technique)-[:PART_OF]->(tc:Tactic)
RETURN ip {.address, .first_seen, .last_seen} AS ip,
       s {.session_id, .first_event, .last_event} AS session,
       COLLECT(DISTINCT {
           event_id: e.event_id,
           eventid: e.eventid,
           timestamp: e.timestamp,
           command: e.command,
           technique_id: t.technique_id,
           technique_name: t.name,
           tactic: tc.tactic,
           tactic_name: tc.name
       }) AS events
ORDER BY s.last_event DESC
LIMIT $limit
"""

TECHNIQUE_SUMMARY = """
MATCH (e:Event)-[:MAPS_TO]->(t:Technique)-[:PART_OF]->(tc:Tactic)
RETURN tc.tactic AS tactic,
       tc.name AS tactic_name,
       COLLECT(DISTINCT t.technique_id) AS techniques,
       COUNT(e) AS event_count
ORDER BY event_count DESC
"""

IP_SUMMARY = """
MATCH (ip:AttackerIP)-[:INITIATED]->(s:Session)
RETURN ip.address AS ip,
       COUNT(s) AS session_count,
       ip.first_seen AS first_seen,
       ip.last_seen AS last_seen
ORDER BY session_count DESC
LIMIT $limit
"""


async def get_attack_paths(neo4j_session, limit: int = 50) -> list[dict]:
    try:
        result = await neo4j_session.run(ATTACK_PATH_QUERY, limit=limit)
        records = await result.fetch(limit)
        return [dict(r) for r in records]
    except Exception as e:
        logger.warning(f"Failed to query attack paths: {e}")
        return []


async def get_technique_summary(neo4j_session) -> list[dict]:
    try:
        result = await neo4j_session.run(TECHNIQUE_SUMMARY)
        records = await result.fetch(100)
        return [dict(r) for r in records]
    except Exception as e:
        logger.warning(f"Failed to query technique summary: {e}")
        return []


async def get_ip_summary(neo4j_session, limit: int = 20) -> list[dict]:
    try:
        result = await neo4j_session.run(IP_SUMMARY, limit=limit)
        records = await result.fetch(limit)
        return [dict(r) for r in records]
    except Exception as e:
        logger.warning(f"Failed to query IP summary: {e}")
        return []
