import asyncio
import logging
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.log import LogEntry

RECENT_BUFFER_SIZE = 1000
FLUSH_INTERVAL = 2.0
FLUSH_BATCH_SIZE = 100
TTL_DAYS = 7
TTL_CLEANUP_INTERVAL = 3600

logger = logging.getLogger("shadowhive")


class AsyncDBLogHandler(logging.Handler):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        super().__init__()
        self._session_maker = session_maker
        self._buffer: deque[logging.LogRecord] = deque()
        self._recent: deque[dict] = deque(maxlen=RECENT_BUFFER_SIZE)
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= FLUSH_BATCH_SIZE:
            asyncio.create_task(self._flush())

    async def start(self):
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._flush_task:
            self._flush_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._buffer:
            await self._flush()

    async def _flush_loop(self):
        while True:
            try:
                await asyncio.sleep(FLUSH_INTERVAL)
                if self._buffer:
                    await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Log flush error")

    async def _flush(self):
        if not self._buffer:
            return
        async with self._lock:
            batch = []
            while self._buffer:
                record = self._buffer.popleft()
                traceback_text = None
                if record.exc_info and record.exc_info[0]:
                    import traceback

                    traceback_text = "".join(traceback.format_exception(*record.exc_info))
                log_id = str(uuid.uuid4())
                entry = {
                    "id": log_id,
                    "timestamp": datetime.fromtimestamp(record.created),
                    "level": record.levelname,
                    "logger_name": record.name,
                    "module": record.module or record.pathname,
                    "func_name": record.funcName,
                    "line_no": record.lineno,
                    "message": record.getMessage(),
                    "traceback": traceback_text,
                    "task_id": getattr(record, "task_id", None),
                    "request_id": getattr(record, "request_id", None),
                }
                batch.append(entry)
                if len(self._recent) >= RECENT_BUFFER_SIZE:
                    self._recent.popleft()
                self._recent.append(entry)
        if not batch:
            return
        try:
            async with self._session_maker() as session:
                session.add_all(LogEntry(**e) for e in batch)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to write {len(batch)} log entries to DB: {e}")

    async def get_recent(
        self,
        level: str | None = None,
        logger_name: str | None = None,
        search: str | None = None,
        task_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "desc",
    ) -> tuple[list[dict], int]:
        items = list(self._recent)
        if level:
            items = [i for i in items if i["level"] == level.upper()]
        if logger_name:
            items = [i for i in items if i["logger_name"] == logger_name]
        if search:
            search_lower = search.lower()
            items = [
                i
                for i in items
                if search_lower in i["message"].lower() or (i["traceback"] and search_lower in i["traceback"].lower())
            ]
        if task_id:
            items = [i for i in items if i["task_id"] == task_id]
        if since:
            items = [i for i in items if i["timestamp"] >= since]
        if until:
            items = [i for i in items if i["timestamp"] <= until]
        total = len(items)
        if order == "desc":
            items.reverse()
        items = items[offset : offset + limit]
        return items, total

    async def get_recent_stats(self) -> dict:
        items = list(self._recent)
        by_level: dict[str, int] = {}
        by_logger: dict[str, int] = {}
        for i in items:
            by_level[i["level"]] = by_level.get(i["level"], 0) + 1
            by_logger[i["logger_name"]] = by_logger.get(i["logger_name"], 0) + 1
        return {
            "total": len(items),
            "by_level": by_level,
            "by_logger": by_logger,
        }

    async def clear_recent(self):
        self._recent.clear()

    async def cleanup_old_logs(self, older_than_days: int = TTL_DAYS):
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than_days)
        try:
            async with self._session_maker() as session:
                result = await session.execute(sa_delete(LogEntry).where(LogEntry.timestamp < cutoff))
                await session.commit()
                deleted = result.rowcount
                if deleted:
                    logger.info(f"Cleaned up {deleted} log entries older than {older_than_days}d")
        except Exception as e:
            logger.error(f"Log cleanup error: {e}")

    async def _cleanup_loop(self):
        await asyncio.sleep(60)
        while True:
            try:
                await asyncio.sleep(TTL_CLEANUP_INTERVAL)
                await self.cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Log cleanup error")
