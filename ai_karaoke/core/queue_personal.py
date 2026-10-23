"""What a guest may do to their own queue entries (mixed into core/queue_manager.QueueManager).

Fairness rule for reordering: a guest only shuffles songs among the slots their own songs
already hold. If Ann holds slots 2 and 5, moving her slot-5 song "up" puts it in slot 2 and
her other song in slot 5 — nobody else's position changes, so nobody can cut ahead.
"""
MODES = ("party", "score", "battle")   # battle: two mics head to head (scored like score for now)


class PersonalQueue:
    entries: list[dict]
    current: dict | None

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

    async def set_prefs(self, uid: str, **prefs) -> dict | None:
        """guide (0-100 or None) / mode (MODES or None) for one entry, playing or waiting."""
        entry = next((e for e in self.entries + [self.current] if e and e["uid"] == uid), None)
        if entry is not None:
            entry.update({k: v for k, v in prefs.items() if k in ("guide", "mode")})
            await self.broadcast_state()
        return entry

    async def drop_guests(self) -> int:
        """After a party wipe: guests' waiting songs leave the queue. The song playing now
        finishes, but no longer belongs to anyone (only the host controls it)."""
        before = len(self.entries)
        self.entries[:] = [e for e in self.entries if e.get("owner") is None]
        if self.current and self.current.get("owner") is not None:
            self.current["owner"] = None
        await self.broadcast_state()
        return before - len(self.entries)

    async def broadcast_state(self) -> None:  # provided by QueueManager
        raise NotImplementedError
