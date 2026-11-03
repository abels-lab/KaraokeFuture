"""set_style: the DJ Co-Pilot restyles every screen through settings, never files. Each value is
checked like a change on the Settings page (custom CSS by core/css_guard.py), all-or-nothing, and
"reset" brings back the theme's own look. Guests may use it when the host switched on
agent_guest_style, at most once a minute each."""
import time
from typing import Any

from core import auth, settings
from core.hub import hub

# set_style argument -> setting key
FIELDS = {"theme": "theme", "accent": "accent", "accent_hex": "style_accent_hex", "font": "style_font",
          "title_effect": "style_title_effect", "background": "style_background", "glow": "style_glow",
          "corners": "style_corners", "pulse": "style_pulse", "title_text": "title_text",
          "custom_css": "custom_css"}
STYLE_KEYS = [key for key in settings.BY_KEY if settings.BY_KEY[key]["group"] == "style"]
GUEST_EVERY = 60.0   # seconds between two restyles by the same guest
_last_by_guest: dict[int, float] = {}


def guest_wait(who: auth.Who) -> float:
    """Seconds this guest still has to wait before restyling again (0 = may now)."""
    if who.admin or who.guest_id is None:
        return 0.0
    return max(0.0, GUEST_EVERY - (time.monotonic() - _last_by_guest.get(who.guest_id, -GUEST_EVERY)))


async def set_style(who: auth.Who, args: dict) -> dict[str, Any]:
    if (wait := guest_wait(who)) > 0:
        return {"error": f"One restyle a minute per guest: try again in {wait:.0f} s"}
    changes = {key: args[arg] for arg, key in FIELDS.items() if arg in args and args[arg] is not None}
    reset = bool(args.get("reset"))
    if not changes and not reset:
        return {"error": "Nothing to change: pass at least one style option"}
    try:
        if reset:
            settings.reset(STYLE_KEYS)
        if changes:
            settings.update(changes)
    except ValueError as exc:
        return {"error": str(exc)}
    if who.guest_id is not None and not who.admin:
        _last_by_guest[who.guest_id] = time.monotonic()
    await hub.broadcast({"type": "settings"})
    return {"status": "ok", "reset": reset, "changed": {k: settings.get(k) for k in changes}}
