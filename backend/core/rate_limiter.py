"""Conservative GitHub GraphQL rate and concurrency limiter."""
import asyncio
import time
from dataclasses import dataclass


@dataclass
class RateState:
    remaining: int = 5000
    reset_at: float = 0.0
    limit: int = 5000
    invalid: bool = False


class RateLimiter:
    """Serialize token selection and reserve primary/secondary capacity.

    The limiter deliberately keeps GraphQL concurrency low and spaces requests
    so multiple workers cannot all observe the same stale primary-limit value.
    """

    def __init__(self, floor: int = 500, tokens: list[str] | None = None,
                 max_concurrent: int = 4, points_per_minute: int = 1600):
        self.tokens = [t.strip().strip('"').strip("'") for t in (tokens or []) if t.strip()]
        self.floor = max(0, floor)
        self.max_concurrent = max(1, max_concurrent)
        self.points_per_minute = max(1, points_per_minute)
        self.states = [RateState() for _ in self.tokens]
        self._index = 0
        self._lock = asyncio.Lock()
        self._concurrency = asyncio.Semaphore(self.max_concurrent)
        self._minute_lock = asyncio.Lock()
        self._window_started = time.monotonic()
        self._window_points = 0

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    async def _reserve_secondary_budget(self, estimated_points: int = 10) -> None:
        while True:
            async with self._minute_lock:
                now = time.monotonic()
                elapsed = now - self._window_started
                if elapsed >= 60:
                    self._window_started = now
                    self._window_points = 0
                if self._window_points + estimated_points <= self.points_per_minute:
                    self._window_points += estimated_points
                    return
                wait = max(0.05, 60 - elapsed)
            await asyncio.sleep(min(wait, 5.0))

    async def acquire(self) -> str:
        if not self.tokens:
            raise RuntimeError("No GitHub tokens configured. Set GITHUB_TOKENS in backend/.env.")
        await self._concurrency.acquire()
        try:
            while True:
                async with self._lock:
                    now = time.time()
                    for offset in range(len(self.tokens)):
                        idx = (self._index + offset) % len(self.tokens)
                        state = self.states[idx]
                        if not state.invalid and (state.remaining > self.floor or state.reset_at <= now):
                            self._index = idx
                            break
                    else:
                        usable = [s.reset_at for s in self.states if not s.invalid]
                        if not usable:
                            raise RuntimeError("All configured GitHub tokens are invalid or unauthorized.")
                        wait = max(1.0, min(usable) - now + 1.0)
                        idx = None
                if idx is not None:
                    await self._reserve_secondary_budget(10)
                    return self.tokens[idx]
                await asyncio.sleep(min(wait, 60.0))
        except Exception:
            self._concurrency.release()
            raise

    async def release(self) -> None:
        self._concurrency.release()

    async def wait_if_needed(self) -> str:
        return await self.acquire()

    def update_from_headers(self, headers, token: str | None = None) -> None:
        if not self.tokens:
            return
        try:
            idx = self.tokens.index(token) if token is not None else self._index
        except ValueError:
            idx = self._index
        state = self.states[idx]
        if headers.get("x-ratelimit-remaining") is not None:
            state.remaining = int(headers["x-ratelimit-remaining"])
        if headers.get("x-ratelimit-reset") is not None:
            state.reset_at = float(headers["x-ratelimit-reset"])
        if headers.get("x-ratelimit-limit") is not None:
            state.limit = int(headers["x-ratelimit-limit"])

    def retry_delay(self, headers, attempt: int) -> float:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return max(1.0, min(float(retry_after), 120.0))
            except ValueError:
                pass
        reset = headers.get("x-ratelimit-reset")
        if reset:
            try:
                return max(1.0, min(float(reset) - time.time() + 1, 120.0))
            except ValueError:
                pass
        return min(2 ** attempt, 30.0)

    async def mark_invalid(self, token: str) -> bool:
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
