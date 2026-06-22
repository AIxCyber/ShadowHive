import zoneinfo
from datetime import UTC, datetime

_TZ_HEADER = "X-Timezone"


def get_user_tz(request) -> zoneinfo.ZoneInfo | None:
    tz_name = request.headers.get(_TZ_HEADER)
    if tz_name:
        try:
            return zoneinfo.ZoneInfo(tz_name)
        except (KeyError, TypeError):
            pass
    return None


def format_dt(dt: datetime | None, tz: zoneinfo.ZoneInfo | None = None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if tz:
        dt = dt.astimezone(tz)
    return dt.isoformat()
