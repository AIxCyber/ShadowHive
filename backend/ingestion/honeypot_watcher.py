import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger("shadowhive.honeypot")


class HoneypotFileWatcher:
    """Generic watcher for JSON-line log files from any honeypot source."""

    def __init__(self, log_path: str, source: str = "unknown"):
        self.log_path = Path(log_path)
        self.source = source
        self._last_position = 0

    async def fetch_events(self, since: str | None = None, limit: int = 100) -> list[dict]:
        if not self.log_path.exists():
            return []
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._read_new_lines)
            events = []
            for line in data:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if since:
                events = [e for e in events if e.get("timestamp", "") > since]
            return events[:limit]
        except Exception as e:
            logger.error(f"Failed to read {self.source} log: {e}")
            return []

    def _read_new_lines(self) -> list[str]:
        with open(self.log_path) as f:
            f.seek(self._last_position)
            lines = f.readlines()
            self._last_position = f.tell()
        return lines

    @staticmethod
    def parse_timestamp(ts: str) -> str:
        return ts.replace("Z", "+00:00") if ts else ""
