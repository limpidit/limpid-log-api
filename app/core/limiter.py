"""
Simple in-memory rate limiter middleware.
Uses a sliding window counter per (key, route).
Not distributed — resets on restart — sufficient for this use case.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# {key: [(timestamp, ...)]}
_windows: dict[str, list[datetime]] = defaultdict(list)

RULES: list[tuple[str, int, int]] = [
    # (path_prefix, max_requests, window_seconds)
    ("/api/auth/login",  5,  60),
    ("/api/log",        60,  60),
    ("/api/logs/batch", 30,  60),
]


def _check(key: str, max_req: int, window_sec: int) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_sec)
    hits = _windows[key]
    # Drop old entries
    _windows[key] = [t for t in hits if t > cutoff]
    if len(_windows[key]) >= max_req:
        return False
    _windows[key].append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        for prefix, max_req, window_sec in RULES:
            if path == prefix or path.startswith(prefix + "/"):
                if prefix in ("/api/log", "/api/logs/batch"):
                    ident = request.headers.get("X-API-Key") or request.client.host
                else:
                    ident = request.client.host if request.client else "unknown"

                key = f"{prefix}:{ident}"
                if not _check(key, max_req, window_sec):
                    return Response(
                        content='{"detail":"Trop de requêtes, réessayez dans une minute."}',
                        status_code=429,
                        media_type="application/json",
                    )
                break

        return await call_next(request)
