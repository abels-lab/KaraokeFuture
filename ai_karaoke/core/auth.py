"""Who is asking: the host (admin), a logged-in guest, or an anonymous viewer.

Role model (enforced here and in the routers, never only by hiding buttons):
- The laptop running the karaoke is the host without a PIN: physical access = host. A
  request counts as the laptop when it comes from 127.0.0.1 / ::1 or this machine's own
  LAN address (a phone can't send from those) and wasn't forwarded by Tailscale Funnel.
- Any other device becomes host by entering the host PIN (routers/auth.py). Until a PIN
  has been set on the laptop, only the laptop is host.
- Guests log in on /remote with a name and password (core/party_db.py) and may manage only
  their own queue entries (`owner` = their guest id) and control their own song while it
  plays. Everyone may look: queue, library, settings, lyrics.
Works for HTTP requests and WebSockets alike (both are an HTTPConnection with cookies).
"""
from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from config import get_local_ip
from core import party_db

COOKIE = "karaoke_session"
HOST_ONLY = "Only the host can do that — enter the host PIN on this device"


@dataclass
class Who:
    laptop: bool = False
    admin: bool = False
    guest_id: int | None = None
    name: str | None = None
    token: str | None = None   # the session cookie, when it belongs to a live session

    def public(self) -> dict:
        guest = {"id": self.guest_id, "name": self.name} if self.guest_id is not None else None
        return {"admin": self.admin, "laptop": self.laptop, "guest": guest,
                "pin_set": party_db.pin_hash() is not None}


def _via_proxy(conn: HTTPConnection) -> bool:
    """Tailscale Funnel / Serve forwards internet visitors from 127.0.0.1. Uvicorn already swaps in
    the real address from X-Forwarded-For, but a forwarded or *.ts.net request is never the laptop."""
    headers = conn.headers
    host = headers.get("host", "").split(":")[0].lower()
    return host.endswith(".ts.net") or any(h in headers for h in ("x-forwarded-for", "forwarded", "tailscale-funnel-request"))


def is_this_laptop(conn: HTTPConnection) -> bool:
    """"testclient" is Starlette's TestClient default, treated like a local request."""
    host = conn.client.host if conn.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient", get_local_ip()) and not _via_proxy(conn)


def identify(conn: HTTPConnection) -> Who:
    laptop = is_this_laptop(conn)
    token = conn.cookies.get(COOKIE)
    live = party_db.session(token)
    if not live:
        return Who(laptop=laptop, admin=laptop)
    return Who(laptop=laptop, admin=laptop or live["admin"], guest_id=live["guest_id"],
               name=live["name"], token=token)


def require_admin(request: Request) -> Who:
    """FastAPI dependency for host-only endpoints."""
    who = identify(request)
    if not who.admin:
        raise HTTPException(403, HOST_ONLY)
    return who


def owns(who: Who, entry: dict | None) -> bool:
    return bool(entry and who.guest_id is not None and entry.get("owner") == who.guest_id)


def may_manage(who: Who, entry: dict | None) -> bool:
    """Remove / reorder / change settings of a queue entry: the host, or whoever queued it."""
    return who.admin or owns(who, entry)
