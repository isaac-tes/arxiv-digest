"""Request guards for the digest service in local mode.

Local mode has no user accounts (one shared user), so the server protects
itself instead:

- **Access token** (`DIGEST_ACCESS_TOKEN`): when set, every request except
  `/health` must send `Authorization: Bearer <token>`. Needed to reach the
  server from other devices.
- **Localhost only** when no token is set: the client must be on this machine
  *and* the `Host` header must name it, so a web page can't reach the server
  through DNS rebinding.

Remote mode authenticates every user with JWTs instead (`auth.py`).
"""

from __future__ import annotations

import hmac
import ipaddress
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from .settings import get_settings

_OPEN_PATHS = {"/health"}
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _is_loopback(host: str | None) -> bool:
    try:
        return host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _hostname(host_header: str) -> str:
    # "localhost:8000" → "localhost", "[::1]:8000" → "::1"
    return (urlsplit(f"//{host_header}").hostname or "").lower()


async def access_guard(request: Request, call_next):
    settings = get_settings()
    if settings.is_remote or request.url.path in _OPEN_PATHS:
        return await call_next(request)

    token = settings.access_token
    if token:
        sent = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(sent.encode(), expected.encode()):
            return JSONResponse({"detail": "Missing or wrong access token."}, status_code=401)
        return await call_next(request)

    client = request.client.host if request.client else None
    if _is_loopback(client) and _hostname(request.headers.get("host", "")) in _LOCAL_HOSTNAMES:
        return await call_next(request)
    return JSONResponse(
        {"detail": "This server only answers this machine. Set DIGEST_ACCESS_TOKEN to allow other devices."},
        status_code=403,
    )


def is_arxiv_url(url: str) -> bool:
    """Whether `url` is an http(s) URL on arxiv.org (feeds may only point there)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme in {"http", "https"} and (host == "arxiv.org" or host.endswith(".arxiv.org"))
