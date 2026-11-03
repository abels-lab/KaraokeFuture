"""Checks the party's custom CSS (the `custom_css` setting, written by the host or the DJ Co-Pilot)
before every screen injects it into a <style> tag.

CSS can't run code, but it can still reach out: url(), @import and image-set() load from any
address (and attribute selectors plus url() can leak what's on the page), old IE / Firefox
extensions bind scripts, and "<" could close the <style> tag. All of those are refused, as are
backslash escapes and comments, which could hide them. What's left restyles, it can't phone home.
"""
import re

MAX_LEN = 4000
_BANNED = ("url(", "image-set(", "image(", "src(", "@import", "@namespace", "@font-face",
           "expression(", "javascript:", "behavior:", "-moz-binding", "vbscript:")


def check(css: str) -> str:
    """The CSS unchanged, or ValueError saying what isn't allowed."""
    if not isinstance(css, str):
        raise ValueError("Custom CSS: must be text")
    if len(css) > MAX_LEN:
        raise ValueError(f"Custom CSS: at most {MAX_LEN} characters")
    for char, why in (("<", "'<'"), ("\\", "backslash escapes"), ("/*", "comments")):
        if char in css:
            raise ValueError(f"Custom CSS: {why} are not allowed")
    squashed = re.sub(r"\s+", "", css.lower())
    for word in _BANNED:
        if word in squashed:
            raise ValueError(f"Custom CSS: {word.rstrip('(:')} is not allowed (nothing may load from outside)")
    if css.count("{") != css.count("}"):
        raise ValueError("Custom CSS: unbalanced { }")
    return css
