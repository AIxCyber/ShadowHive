from datetime import UTC, datetime

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

ANALYSIS_PROMPT = """You are a threat intelligence analyst. Analyze this attacker's activities.

Attacker IP: {source_ip}
Session events ({event_count}):
{events}

Session duration: {duration_minutes} minutes

Return a JSON object with:
- attacker_objectives: array of 1-3 likely objectives (e.g., "credential theft", "lateral movement")
- confidence: integer 1-100
- threat_level: "low", "medium", "high", or "critical"
- summary: 2-3 sentence threat summary
- recommended_actions: array of 2-4 recommended deception responses
- observed_techniques: array of technique names observed

ONLY return valid JSON, no other text."""


async def analyze_session(
    source_ip: str,
    events: list[dict],
    duration_minutes: float | None = None,
) -> dict:
    if duration_minutes is None and events:
        timestamps = [e.get("detected_at") or e.get("timestamp") or e.get("created_at") for e in events if e]
        if timestamps:
            try:
                start = datetime.fromisoformat(str(timestamps[0]).replace("Z", "+00:00"))
                end = datetime.fromisoformat(str(timestamps[-1]).replace("Z", "+00:00"))
                duration_minutes = (end - start).total_seconds() / 60
            except (ValueError, TypeError):
                duration_minutes = 0
        else:
            duration_minutes = 0

    events_summary = "\n".join(
        [f"  - [{e.get('event_type', 'unknown')}] {e.get('command', '')[:100]}" for e in events[:20]]
    )

    provider = get_provider_for_module("threat_analysis", Config.all())
    prompt = ANALYSIS_PROMPT.format(
        source_ip=source_ip,
        event_count=len(events),
        events=events_summary,
        duration_minutes=round(duration_minutes or 0, 1),
    )
    response = await provider.generate(
        prompt=prompt,
        system="You are a threat intelligence analyst specializing in deception technology and attacker profiling.",
        temperature=0.4,
    )
    try:
        data = extract_json(response.content)
    except Exception:
        return {
            "attacker_objectives": ["unknown"],
            "confidence": 0,
            "threat_level": "unknown",
            "summary": "Analysis failed to parse",
            "recommended_actions": [],
            "observed_techniques": [],
        }
    data["source_ip"] = source_ip
    data["total_events"] = len(events)
    data["analyzed_at"] = datetime.now(UTC).isoformat()
    return data
