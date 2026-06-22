import time
from collections import defaultdict

from fastapi import HTTPException
from starlette.requests import Request

from backend.utils.config import Config


class InMemoryRateLimiter:
    def __init__(self):
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def _key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def check(self, request: Request) -> None:
        cfg = Config.get("auth.rate_limiting", {})
        if not cfg.get("enabled", True):
            return
        max_attempts = cfg.get("max_attempts", 10)
        window_seconds = cfg.get("window_seconds", 60)

        key = self._key(request)
        now = time.time()
        window_start = now - window_seconds

        self._attempts[key] = [t for t in self._attempts[key] if t > window_start]
        self._attempts[key].append(now)

        if len(self._attempts[key]) > max_attempts:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {window_seconds} seconds.",
            )


rate_limiter = InMemoryRateLimiter()
