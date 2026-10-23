"""Building blocks of the settings registry (core/settings_schema.py and its parts): one
dict per setting, so the schema files read like a table, plus when a change takes effect."""
NOW, NEXT, PROCESSING = "immediately", "next song", "next processed song"


def _s(key, group, label, default, kind, help_, applies=PROCESSING, client=False, **extra):
    return {"key": key, "group": group, "label": label, "default": default, "kind": kind,
            "help": help_, "applies": applies, "client": client, **extra}


def _n(key, group, label, default, lo, hi, step, unit, help_, applies=PROCESSING, client=False):
    return _s(key, group, label, default, "number", help_, applies, client, min=lo, max=hi, step=step, unit=unit)
