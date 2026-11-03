"""Advanced settings: defaults from settings_schema, changes kept in settings.json.

Code reads values when it uses them (settings.get("key")), so most changes need no restart.
Every value is validated against its limits; an invalid or unknown entry in the file is
ignored (logged), so a hand-edited or broken file can never stop the app.
"""
import json
import logging
import math
import os
import threading

from config import SETTINGS_FILE
from core.settings_schema import RETIRED, SPECS

log = logging.getLogger(__name__)
BY_KEY = {spec["key"]: spec for spec in SPECS}
_lock = threading.Lock()
_values: dict = {}   # only the settings that differ from their default


def coerce(spec: dict, value):
    """The value as the setting's type, or ValueError with a message for the Settings page."""
    kind, label = spec["kind"], spec["label"]
    if kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"{label}: must be on or off")
    if kind == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label}: must be a number") from None
        if not math.isfinite(number) or not spec["min"] <= number <= spec["max"]:
            raise ValueError(f"{label}: must be between {spec['min']} and {spec['max']}")
        return int(number) if float(spec["step"]).is_integer() and number.is_integer() else round(number, 4)
    if kind == "text":
        if spec.get("allow_empty", False) and (value == "" or (isinstance(value, str) and not value.strip())):
            return ""
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > spec["max_len"]:
            raise ValueError(f"{label}: must be 1 to {spec['max_len']} characters")
        return " ".join(value.split())
    allowed = [choice[0] for choice in spec["choices"]]
    match = next((a for a in allowed if str(a) == str(value)), None)
    if match is None:
        raise ValueError(f"{label}: not one of the offered choices")
    return match


def _check_together(values: dict) -> None:
    """Rules that involve two settings."""
    if values["game_perfect"] >= values["game_miss"]:
        raise ValueError("Pitch miss point must be larger than the perfect pitch window")
    if values["min_duration_sec"] >= values["max_duration_min"] * 60:
        raise ValueError("Shortest song allowed must be shorter than the longest song allowed")


def _load() -> None:
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except ValueError as exc:
        log.warning("settings.json is unreadable (%s): using defaults", exc)
        return
    for key, value in stored.items() if isinstance(stored, dict) else []:
        if key in RETIRED:   # a setting that was removed: forgotten at the next save
            continue
        try:
            _values[key] = coerce(BY_KEY[key], value)
        except (KeyError, ValueError) as exc:
            log.warning("Ignoring setting %r=%r: %s", key, value, exc)


def _save() -> None:
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_values, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)


def get(key: str, default=None):
    if key in _values:
        return _values[key]
    if key in BY_KEY:
        return BY_KEY[key]["default"]
    return default


def all_values() -> dict:
    return {key: get(key) for key in BY_KEY}


def update(changes: dict) -> None:
    """Validate everything first; nothing is stored unless every change is valid."""
    unknown = [key for key in changes if key not in BY_KEY]
    if unknown:
        raise ValueError(f"Unknown setting: {', '.join(unknown)}")
    clean = {key: coerce(BY_KEY[key], value) for key, value in changes.items()}
    with _lock:
        merged = {**all_values(), **clean}
        _check_together(merged)
        for key, value in clean.items():
            if value == BY_KEY[key]["default"]:
                _values.pop(key, None)   # back at default: store nothing
            else:
                _values[key] = value
        _save()
    log.info("Settings changed: %s", clean)


def reset(keys: list[str] | None = None) -> None:
    """Back to defaults: the given settings, or all of them."""
    with _lock:
        for key in list(_values) if keys is None else keys:
            _values.pop(key, None)
        _save()
    log.info("Settings reset: %s", "all" if keys is None else keys)


def snapshot() -> list[dict]:
    return [{**spec, "value": get(spec["key"]), "changed": spec["key"] in _values} for spec in SPECS]


def client_values() -> dict:
    return {spec["key"]: get(spec["key"]) for spec in SPECS if spec["client"]}


_load()
