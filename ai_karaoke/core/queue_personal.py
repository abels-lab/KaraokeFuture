"""What a guest may do to their own queue entries (mixed into core/queue_manager.QueueManager).

Fairness rule for reordering: a guest only shuffles songs among the slots their own songs
already hold. If Ann holds slots 2 and 5, moving her slot-5 song "up" puts it in slot 2 and
her other song in slot 5 — nobody else's position changes, so nobody can cut ahead.

Battle / Duet: another guest may join a battle song as its `partner` (the second mic) while it
waits, or during the pre-song intro card the control panel reports (`set_intro`). A partner
only sings: moving, removing and tuning the entry stay with its owner and the host.
"""
import time

MODES = ("party", "score", "battle")   # battle: two mics scored side by side, one winner


class PersonalQueue:
    entries: list[dict]
    current: dict | None
    intro: tuple[str, float] = ("", 0.0)   # (uid, monotonic end) of the intro card on screen

    async def move_own(self, uid: str, owner: int, direction: str) -> bool:
        """direction: up | down (swap with your neighbouring song) | top (your first slot).
        False when the entry isn't this owner's waiting entry."""
        mine = [e for e in self.entries if e.get("owner") == owner]
        entry = next((e for e in mine if e["uid"] == uid), None)
        if entry is None:
            return False
        slots = [self.entries.index(e) for e in mine]   # the positions this guest holds
        index = mine.index(entry)
        target = {"up": index - 1, "down": index + 1, "top": 0}[direction]
        if 0 <= target < len(mine) and target != index:
            mine.insert(target, mine.pop(index))
            for slot, e in zip(slots, mine):
                self.entries[slot] = e
            await self.broadcast_state()
        return True

    def _entry(self, uid: str) -> dict | None:   # waiting or playing now
        return next((e for e in self.entries + [self.current] if e and e["uid"] == uid), None)

    async def set_prefs(self, uid: str, **prefs) -> dict | None:
        """guide (0-100 or None) / mode (MODES or None) for one entry, playing or waiting."""
        entry = self._entry(uid)
        if entry is not None:
            entry.update({k: v for k, v in prefs.items() if k in ("guide", "mode")})
            if entry.get("mode") != "battle":
                entry["partner"] = None   # a second singer only exists in battle mode
            await self.broadcast_state()
        return entry

    # ── Battle / Duet ────────────────────────────────────────────────────────
    def set_intro(self, uid: str, seconds_left: float) -> None:
        """From the control panel, 4x a second while the countdown runs. A second of slack,
        so a lost last message (TV closed mid-intro) can't keep a song joinable for ever."""
        self.intro = (uid, time.monotonic() + seconds_left + 1.0) if seconds_left > 0 else ("", 0.0)

    def in_intro(self, uid: str) -> bool:
        return self.intro[0] == uid and time.monotonic() < self.intro[1]

    async def set_partner(self, uid: str, partner: dict | None) -> dict | None:
        """partner = {id, name} of the guest singing mic 2, or None to free the slot."""
        entry = self._entry(uid)
        if entry is not None:
            entry["partner"] = partner
            await self.broadcast_state()
        return entry

    async def drop_guests(self) -> int:
        """After a party wipe: guests' waiting songs leave the queue. The song playing now
        finishes, but no longer belongs to anyone (only the host controls it). Battle partners
        were guests too, so every remaining entry loses its partner."""
        before = len(self.entries)
        self.entries[:] = [e for e in self.entries if e.get("owner") is None]
        if self.current and self.current.get("owner") is not None:
            self.current["owner"] = None
        for entry in self.entries + ([self.current] if self.current else []):
            entry["partner"] = None
        await self.broadcast_state()
        return before - len(self.entries)

    async def broadcast_state(self) -> None:  # provided by QueueManager
        raise NotImplementedError
