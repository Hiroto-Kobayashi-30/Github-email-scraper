"""Persistent cache for candidates that have no public profile email.

The cache is intentionally negative-only: it remembers that GitHub exposed no
public profile email for a candidate, but it never stores discovered email
addresses. Entries expire so a user who later publishes an email can be
considered again.
"""
import json
import os
import threading
import time
from pathlib import Path


class RejectionCache:
    def __init__(self, path: Path, ttl_days: int = 30):
        self.path = path
        self.ttl_seconds = max(1, ttl_days) * 86400
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._load()

    @staticmethod
    def _key(user_id: str | None, login: str | None) -> str:
        if user_id:
            return f"id:{user_id}"
        return f"login:{(login or '').strip().lower()}"

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
            if isinstance(entries, dict):
                self._entries = entries
        except (OSError, ValueError, TypeError):
            # A corrupt cache must never stop a scrape. It will be rebuilt.
            self._entries = {}

    def _prune_locked(self, now: float) -> bool:
        changed = False
        for key, entry in list(self._entries.items()):
            try:
                checked_at = float(entry.get("checked_at", 0))
            except (TypeError, ValueError):
                checked_at = 0
            if now - checked_at >= self.ttl_seconds:
                del self._entries[key]
                changed = True
        return changed

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": 1, "entries": self._entries}
        with temp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, self.path)

    def contains(self, user_id: str | None, login: str | None) -> bool:
        key = self._key(user_id, login)
        if key == "login:":
            return False
        now = time.time()
        with self._lock:
            changed = self._prune_locked(now)
            entry = self._entries.get(key)
            hit = bool(entry)
            if changed:
                self._save_locked()
            return hit

    def remember_no_public_email(self, user_id: str | None, login: str | None) -> None:
        key = self._key(user_id, login)
        if key == "login:":
            return
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            self._entries[key] = {
                "login": (login or "").strip(),
                "reason": "no_public_profile_email",
                "checked_at": now,
            }
            self._save_locked()

    def size(self) -> int:
        now = time.time()
        with self._lock:
            changed = self._prune_locked(now)
            if changed:
                self._save_locked()
            return len(self._entries)
