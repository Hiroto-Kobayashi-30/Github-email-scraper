"""Per-token GitHub GraphQL rate-limit and authentication management."""
import asyncio
import time
from dataclasses import dataclass


@dataclass
class RateState:
    remaining: int = 5000
    reset_at: float = 0.0
    limit: int = 5000
    invalid: bool = False

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0


class RateLimiter:
    """Select a usable token and rotate away from exhausted/invalid tokens."""

    def __init__(self, floor: int = 500, tokens: list[str] | None = None):
        cleaned = [t.strip().strip('"').strip("'") for t in (tokens or []) if t.strip()]
        self.tokens = cleaned
        self.floor = max(0, floor)
        self.states = [RateState() for _ in self.tokens]
        self._index = 0
        self._lock = asyncio.Lock()

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    def current_token(self) -> str:
        if not self.tokens:
            return ""
        return self.tokens[self._index]

    def snapshot(self) -> dict:
        if not self.tokens:
            return {"token_index": -1, "token_count": 0, "remaining": 0, "limit": 0, "reset_at": 0}
        state = self.states[self._index]
        return {
            "token_index": self._index,
            "token_count": len(self.tokens),
            "remaining": state.remaining,
            "limit": state.limit,
            "reset_at": state.reset_at,
            "invalid": state.invalid,
        }

    async def acquire(self) -> str:
        if not self.tokens:
            raise RuntimeError(
                "No GitHub tokens configured. Set GITHUB_TOKENS in backend/.env."
            )
        while True:
            async with self._lock:
                now = time.time()
                available = [
                    i for i, state in enumerate(self.states)
                    if not state.invalid and (state.remaining > self.floor or state.reset_at <= now)
                ]
                if available:
                    for offset in range(len(self.tokens)):
                        idx = (self._index + offset) % len(self.tokens)
                        if idx in available:
                            self._index = idx
                            return self.tokens[idx]

                usable = [s.reset_at for s in self.states if not s.invalid]
                if not usable:
                    raise RuntimeError(
                        "All configured GitHub tokens are invalid or unauthorized. "
                        "Create valid classic tokens and give them the public_repo scope."
                    )
                reset_at = min(usable)
                wait = max(1.0, reset_at - now + 1.0)
            await asyncio.sleep(min(wait, 60.0))

    def update_from_headers(self, headers, token: str | None = None) -> None:
        if not self.tokens:
            return
        if token is None:
            idx = self._index
        else:
            try:
                idx = self.tokens.index(token)
            except ValueError:
                idx = self._index
        state = self.states[idx]
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        limit = headers.get("x-ratelimit-limit")
        if remaining is not None:
            state.remaining = int(remaining)
        if reset is not None:
            state.reset_at = float(reset)
        if limit is not None:
            state.limit = int(limit)

    async def mark_invalid(self, token: str) -> bool:
        """Mark a token unauthorized and rotate to another token if available."""
        async with self._lock:
            try:
                idx = self.tokens.index(token)
            except ValueError:
                return False
            self.states[idx].invalid = True
            for offset in range(1, len(self.tokens) + 1):
                candidate = (idx + offset) % len(self.tokens)
                if not self.states[candidate].invalid:
                    self._index = candidate
                    return True
            return False

    async def wait_if_needed(self) -> str:
        return await self.acquire()

    async def rotate_if_low(self) -> None:
        if not self.tokens:
            return
        async with self._lock:
            for offset in range(1, len(self.tokens) + 1):
                idx = (self._index + offset) % len(self.tokens)
                if not self.states[idx].invalid and self.states[idx].remaining > self.floor:
                    self._index = idx
                    return
