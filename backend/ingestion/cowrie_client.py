import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger("shadowhive.cowrie")


class CowrieClient:
    def __init__(self, log_path: str = "/app/cowrie_logs/cowrie.json"):
        self.log_path = Path(log_path)
        self._last_position = 0

    async def fetch_events(self, since: str | None = None, limit: int = 100) -> list[dict]:
        if not self.log_path.exists():
            return []

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._read_new_lines)
            events = []
            for line in data:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if since:
                events = [e for e in events if e.get("timestamp", "") > since]
            return events[:limit]
        except Exception as e:
            logger.error(f"Failed to read Cowrie log: {e}")
            return []

    def _read_new_lines(self) -> list[str]:
        with open(self.log_path) as f:
            f.seek(self._last_position)
            lines = f.readlines()
            self._last_position = f.tell()
        return lines

    @staticmethod
    def parse_event(raw: dict) -> dict:
        return {
            "source_ip": raw.get("src_ip", "unknown"),
            "event_type": raw.get("eventid", "unknown"),
            "command": raw.get("message", raw.get("input", "")),
            "session_id": raw.get("session", ""),
            "timestamp": raw.get("timestamp", ""),
            "raw_data": raw,
        }
