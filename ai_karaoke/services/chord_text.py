"""Turn a guitar chord sheet into plain lyrics: drop chord tags and chord-only lines, fret diagrams,
tab staves and chart info (tuning, capo, ...). Used by services/guitar_tabs.py."""
import re

_CHORD_TAG = re.compile(r"\[ch\][^\[]*?\[/ch\]", re.IGNORECASE)
_TAB_TAG = re.compile(r"\[/?(?:tab|toptab|headline|closetab)\]", re.IGNORECASE)
_FRET_DIAGRAM = re.compile(r"^[A-H][b#]?[a-z0-9]*\s+[\dxX\s-]{5,}$")
_TAB_STAFF = re.compile(r"^[eBGDAE]\s*\|")
_CHART_META = re.compile(r"^(tuning|capo|strumming|bpm|key|tempo|tone)\s*[:=]", re.IGNORECASE)
_CHORD_TOKEN = re.compile(r"^[A-H][b#]?(?:m|maj|min|dim|aug|sus|add)?[0-9]*(?:/[A-H][b#]?)?$", re.IGNORECASE)


def is_chord_or_noise(line: str) -> bool:
    """True if line contains guitar fret diagrams, tuning info, tab staves, or only chord names."""
    trimmed = line.strip()
    if not trimmed:
        return True
    if _FRET_DIAGRAM.match(trimmed) or _TAB_STAFF.match(trimmed) or _CHART_META.match(trimmed):
        return True
    # Tab staff or divider lines: mostly ASCII dashes/pipes/slashes
    if len(trimmed) >= 5 and sum(ch in "-|~/\\x*=_" for ch in trimmed) / len(trimmed) > 0.4:
        return True
    # Lines where every word is a chord symbol (e.g. "Em D C G" or "Am7/G Dsus4 Cmaj7")
    tokens = [t.strip(".,;:()[]{}|/\\-") for t in trimmed.split() if t.strip(".,;:()[]{}|/\\-")]
    if tokens and all(_CHORD_TOKEN.match(t) for t in tokens):
        return True
    return False


def clean_chord_sheet(raw: str) -> str:
    """Strip [ch]...[/ch] tags, tab wrappers, chord fret diagrams, and ASCII tab staves."""
    text = _CHORD_TAG.sub("", raw or "")
    text = _TAB_TAG.sub("", text)
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        if not is_chord_or_noise(trimmed):
            lines.append(trimmed)
    return "\n".join(lines)
