"""The server never opens a browser window on the laptop.

Background work (cache warmer, downloads, lyrics and metadata lookups) runs unattended, so a
library that tries to open a page (an OAuth login, a QR or image preview, a "help" link) must not
pop up a tab on the host's screen. install() swaps webbrowser.open* and os.startfile (for URLs)
for a stub that refuses and logs who asked, with a stack trace, so a culprit shows in the log.
Opening the control panel at start is the start script's job (start-karaoke.ps1), not ours.
"""
import logging
import os
import traceback
import webbrowser

log = logging.getLogger(__name__)
_URL_PREFIXES = ("http:", "https:", "file:", "www.")
_installed = False


def _refuse(what: str, target) -> None:
    stack = "".join(traceback.format_stack(limit=12)[:-2])
    log.warning("Blocked %s(%r): the karaoke server never opens browser windows. Called from:\n%s",
                what, target, stack)


def _blocked_open(url, new=0, autoraise=True) -> bool:
    _refuse("webbrowser.open", url)
    return False


def _blocked_open_new(url) -> bool:
    _refuse("webbrowser.open_new", url)
    return False


def _blocked_open_new_tab(url) -> bool:
    _refuse("webbrowser.open_new_tab", url)
    return False


def _guard_startfile(real):
    def startfile(path, *args, **kwargs):
        if str(path).strip().lower().startswith(_URL_PREFIXES):
            _refuse("os.startfile", path)
            return None
        return real(path, *args, **kwargs)
    return startfile


def install() -> None:
    """Idempotent; call once at startup, before any background work begins."""
    global _installed
    if _installed:
        return
    webbrowser.open, webbrowser.open_new, webbrowser.open_new_tab = (
        _blocked_open, _blocked_open_new, _blocked_open_new_tab)
    if hasattr(os, "startfile"):   # Windows only
        os.startfile = _guard_startfile(os.startfile)
    _installed = True
