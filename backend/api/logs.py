import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from backend.auth import get_optional_user, require_role
from backend.models.user import User

logger = logging.getLogger("shadowhive")

router = APIRouter(prefix="/api/logs", tags=["logs"])

_log_handler = None


def set_log_handler(handler):
    global _log_handler
    _log_handler = handler


@router.get("")
async def get_logs(
    level: str | None = Query(None, description="Filter by level (ERROR, WARNING, INFO, DEBUG)"),
    logger_name: str | None = Query(None, alias="logger", description="Filter by logger name"),
    search: str | None = Query(None, description="Search in message and traceback"),
    task_id: str | None = Query(None, description="Filter by task ID"),
    since: str | None = Query(None, description="ISO datetime (inclusive)"),
    until: str | None = Query(None, description="ISO datetime (inclusive)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    _user: User | None = Depends(get_optional_user),
):
    if not _log_handler:
        return {"items": [], "total": 0}
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00")) if until else None
    if since_dt:
        since_dt = since_dt.replace(tzinfo=None)
    if until_dt:
        until_dt = until_dt.replace(tzinfo=None)
    items, total = await _log_handler.get_recent(
        level=level,
        logger_name=logger_name,
        search=search,
        task_id=task_id,
        since=since_dt,
        until=until_dt,
        limit=limit,
        offset=offset,
        order=order,
    )
    return {"items": items, "total": total}


@router.get("/stats")
async def get_log_stats(
    _user: User | None = Depends(get_optional_user),
):
    if not _log_handler:
        return {"total": 0, "by_level": {}, "by_logger": {}}
    return await _log_handler.get_recent_stats()


@router.delete("")
async def clear_logs(
    older_than: int = Query(7, ge=1, description="Delete logs older than N days"),
    _user: User = Depends(require_role("admin")),
):
    if not _log_handler:
        return {"deleted": 0}
    await _log_handler.cleanup_old_logs(older_than_days=older_than)
    return {"deleted": True}
