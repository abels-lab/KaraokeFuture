"""The guest link: this laptop's Tailscale Funnel address, when one points at our port.

Tailscale Funnel gives the laptop a public https://<machine>.<tailnet>.ts.net address that
forwards to a local port. Guests can then open the remote page from their phone's mobile data,
no shared Wi-Fi needed, and over HTTPS (so their party password isn't sent in plain text).
The start script (start-karaoke.ps1) switches Funnel on; this module only reads its status, so
a server started any other way still finds the link. Results are cached: the TV asks often.
"""
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)
_EXE_GUESSES = [r"C:\Program Files\Tailscale\tailscale.exe", "/usr/bin/tailscale", "/usr/local/bin/tailscale",
                "/Applications/Tailscale.app/Contents/MacOS/Tailscale"]
CACHE_SECONDS = 30
_cache: tuple[float, int, str | None] = (0.0, 0, None)   # (checked at, port, url)


def executable() -> str | None:
    return shutil.which("tailscale") or next((p for p in _EXE_GUESSES if Path(p).is_file()), None)


def _status() -> dict:
    exe = executable()
    if not exe:
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # no console window flashing on Windows
    out = subprocess.run([exe, "funnel", "status", "--json"], capture_output=True, text=True,
                         timeout=5, creationflags=flags)
    return json.loads(out.stdout or "{}") if out.returncode == 0 else {}


def _find(status: dict, port: int) -> str | None:
    """https://host[:port] of a Funnel whose handler proxies to our local port."""
    for host_port, web in (status.get("Web") or {}).items():
        if not (status.get("AllowFunnel") or {}).get(host_port):
            continue   # served inside the tailnet only: phones outside can't open it
        targets = [h.get("Proxy", "") for h in (web.get("Handlers") or {}).values()]
        if any(t.rstrip("/").endswith(f":{port}") for t in targets):
            host, _, public_port = host_port.rpartition(":")
            return f"https://{host}" + ("" if public_port == "443" else f":{public_port}")
    return None


def funnel_url(port: int) -> str | None:
    """The public guest address, or None (Tailscale missing, logged out or no Funnel to us)."""
    global _cache
    checked, cached_port, url = _cache
    if cached_port == port and time.monotonic() - checked < CACHE_SECONDS:
        return url
    try:
        url = _find(_status(), port)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.debug("Tailscale status unavailable: %s", exc)
        url = None
    _cache = (time.monotonic(), port, url)
    return url
