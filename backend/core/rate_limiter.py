"""Conservative GitHub GraphQL rate/concurrency limiter with live token telemetry."""
import asyncio
import time
from dataclasses import dataclass


@dataclass
class RateState:
    remaining: int = 0
    limit: int = 5000
    reset_at: float = 0.0
    invalid: bool = False
    initialized: bool = False
    in_flight: int = 0
    cooldown_until: float = 0.0
    last_cost: int = 0
    last_status: int | None = None
    last_error: str | None = None


class RateLimiter:
    """Limit concurrency and keep each configured token's rate state."""

    def __init__(
        self,
        floor: int = 500,
        tokens: list[str] | None = None,
        max_concurrent: int = 4,
        points_per_minute: int = 1600,
    ):
        self.tokens = [
            t.strip().strip('"').strip("'")
            for t in (tokens or [])
            if t.strip()
        ]

        self.floor = max(0, floor)
        self.max_concurrent = max(
            1,
            max_concurrent,
        )
        self.points_per_minute = max(
            1,
            points_per_minute,
        )

        self.states = [
            RateState()
            for _ in self.tokens
        ]

        self._index = 0
        self._lock = asyncio.Lock()

        self._concurrency = asyncio.Semaphore(
            self.max_concurrent
        )

        self._minute_lock = asyncio.Lock()
        self._window_started = time.monotonic()
        self._window_points = 0

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    def _idx(self, token: str) -> int:
        try:
            return self.tokens.index(token)
        except ValueError:
            return 0

    async def _reserve_secondary_budget(
        self,
        estimated_points: int = 10,
    ) -> None:
        estimated_points = max(
            0,
            estimated_points,
        )

        # A zero-point REST request does not need secondary GraphQL
        # point pacing.
        if estimated_points == 0:
            return

        while True:
            async with self._minute_lock:
                now = time.monotonic()

                elapsed = (
                    now - self._window_started
                )

                if elapsed >= 60:
                    self._window_started = now
                    self._window_points = 0

                if (
                    self._window_points
                    + estimated_points
                    <= self.points_per_minute
                ):
                    self._window_points += (
                        estimated_points
                    )
                    return

                wait = max(
                    0.05,
                    60 - elapsed,
                )

            await asyncio.sleep(
                min(wait, 5.0)
            )

    async def acquire(
        self,
        estimated_points: int = 10,
    ) -> str:
        if not self.tokens:
            raise RuntimeError(
                "No GitHub tokens configured. "
                "Set GITHUB_TOKENS in backend/.env."
            )

        await self._concurrency.acquire()

        try:
            while True:
                async with self._lock:
                    now = time.time()
                    chosen = None

                    for offset in range(
                        len(self.tokens)
                    ):
                        idx = (
                            self._index + offset
                        ) % len(self.tokens)

                        state = self.states[idx]

                        # Account for requests already in flight against
                        # the primary-limit floor.
                        projected = (
                            state.remaining
                            - (
                                state.in_flight
                                * 10
                            )
                            if state.initialized
                            else 5000
                        )

                        if (
                            not state.invalid
                            and now
                            >= state.cooldown_until
                            and (
                                not state.initialized
                                or projected
                                > self.floor
                                or state.reset_at
                                <= now
                            )
                        ):
                            chosen = idx

                            state.in_flight += 1

                            self._index = (
                                idx + 1
                            ) % len(self.tokens)

                            break

                    if chosen is None:
                        usable = [
                            s.cooldown_until
                            for s in self.states
                            if (
                                not s.invalid
                                and s.cooldown_until
                                > now
                            )
                        ]

                        resets = [
                            s.reset_at
                            for s in self.states
                            if (
                                not s.invalid
                                and s.reset_at > now
                                and s.initialized
                            )
                        ]

                        waits = usable + resets

                        if not waits:
                            if all(
                                s.invalid
                                for s in self.states
                            ):
                                raise RuntimeError(
                                    "All configured GitHub "
                                    "tokens are invalid "
                                    "or unauthorized."
                                )

                            wait = 1.0

                        else:
                            wait = max(
                                0.25,
                                min(waits) - now,
                            )

                if chosen is not None:
                    await self._reserve_secondary_budget(
                        estimated_points
                    )

                    return self.tokens[
                        chosen
                    ]

                await asyncio.sleep(
                    min(wait, 5.0)
                )

        except Exception:
            self._concurrency.release()
            raise

    async def release(
        self,
        token: str | None = None,
    ) -> None:
        async with self._lock:
            if (
                token is not None
                and token in self.tokens
            ):
                idx = self.tokens.index(
                    token
                )

                self.states[idx].in_flight = max(
                    0,
                    self.states[idx].in_flight - 1,
                )

        self._concurrency.release()

    async def wait_if_needed(
        self,
        estimated_points: int = 10,
    ) -> str:
        return await self.acquire(
            estimated_points=estimated_points
        )

    def update_from_headers(
        self,
        headers,
        token: str | None = None,
    ) -> None:
        if not self.tokens:
            return

        idx = (
            self._idx(token)
            if token is not None
            else self._index
        )

        state = self.states[idx]

        if (
            headers.get(
                "x-ratelimit-remaining"
            )
            is not None
        ):
            state.remaining = int(
                headers[
                    "x-ratelimit-remaining"
                ]
            )

            state.initialized = True

        if (
            headers.get(
                "x-ratelimit-reset"
            )
            is not None
        ):
            state.reset_at = float(
                headers[
                    "x-ratelimit-reset"
                ]
            )

        if (
            headers.get(
                "x-ratelimit-limit"
            )
            is not None
        ):
            state.limit = int(
                headers[
                    "x-ratelimit-limit"
                ]
            )

        state.last_status = None

    def record_graphql_result(
        self,
        token: str,
        payload: dict,
    ) -> None:
        """Capture authoritative GraphQL rateLimit telemetry."""
        if token not in self.tokens:
            return

        idx = self.tokens.index(
            token
        )

        rl = (
            payload.get("data", {}).get(
                "rateLimit"
            )
            if isinstance(payload, dict)
            else None
        )

        if not isinstance(rl, dict):
            return

        state = self.states[idx]

        if rl.get("remaining") is not None:
            state.remaining = int(
                rl["remaining"]
            )
            state.initialized = True

        if rl.get("limit") is not None:
            state.limit = int(
                rl["limit"]
            )

        if rl.get("resetAt"):
            try:
                from datetime import datetime

                state.reset_at = (
                    datetime.fromisoformat(
                        str(
                            rl["resetAt"]
                        ).replace(
                            "Z",
                            "+00:00",
                        )
                    ).timestamp()
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        if rl.get("cost") is not None:
            state.last_cost = int(
                rl["cost"]
            )

    def note_response(
        self,
        token: str,
        status: int,
        headers=None,
        message: str | None = None,
    ) -> None:
        if token not in self.tokens:
            return

        idx = self.tokens.index(
            token
        )

        state = self.states[idx]

        state.last_status = status
        state.last_error = message

        headers = headers or {}

        delay = self.retry_delay(
            headers,
            0,
        )

        if status in (403, 429):
            state.cooldown_until = max(
                state.cooldown_until,
                time.time() + delay,
            )

    def clear_cooldown(
        self,
        token: str,
    ) -> None:
        if token in self.tokens:
            self.states[
                self.tokens.index(token)
            ].cooldown_until = 0.0

    def retry_delay(
        self,
        headers,
        attempt: int,
    ) -> float:
        retry_after = headers.get(
            "retry-after"
        )

        if retry_after:
            try:
                return max(
                    1.0,
                    min(
                        float(retry_after),
                        120.0,
                    ),
                )
            except ValueError:
                pass

        reset = headers.get(
            "x-ratelimit-reset"
        )

        if reset:
            try:
                return max(
                    1.0,
                    min(
                        float(reset)
                        - time.time()
                        + 1,
                        120.0,
                    ),
                )
            except ValueError:
                pass

        return min(
            2 ** attempt,
            30.0,
        )

    async def mark_invalid(
        self,
        token: str,
    ) -> bool:
        async with self._lock:
            try:
                idx = self.tokens.index(
                    token
                )
            except ValueError:
                return False

            self.states[idx].invalid = True

            # The caller releases the request slot separately.
            # Do not decrement in_flight here because that would
            # count the same request twice.

            for offset in range(
                1,
                len(self.tokens) + 1,
            ):
                candidate = (
                    idx + offset
                ) % len(self.tokens)

                if not self.states[
                    candidate
                ].invalid:
                    self._index = candidate
                    return True

            return False

    def token_status(self) -> list[dict]:
        now = time.time()

        result = []

        for i, (
            token,
            state,
        ) in enumerate(
            zip(
                self.tokens,
                self.states,
            ),
            start=1,
        ):
            cooldown = max(
                0.0,
                state.cooldown_until - now,
            )

            reset = max(
                0.0,
                state.reset_at - now,
            )

            usage = None

            if (
                state.initialized
                and state.limit
            ):
                usage = round(
                    max(
                        0.0,
                        min(
                            100.0,
                            (
                                1
                                - state.remaining
                                / state.limit
                            )
                            * 100,
                        ),
                    ),
                    1,
                )

            result.append(
                {
                    "token_index": i,
                    "label": f"Token {i}",
                    "masked": (
                        f"{token[:4]}…{token[-4:]}"
                        if len(token) >= 8
                        else "••••"
                    ),
                    "usage_percent": usage,
                    "remaining": (
                        state.remaining
                        if state.initialized
                        else None
                    ),
                    "limit": (
                        state.limit
                        if state.initialized
                        else None
                    ),
                    "reset_seconds": round(
                        reset
                    ),
                    "cooldown_seconds": round(
                        cooldown
                    ),
                    "cooldown_active": (
                        cooldown > 0
                    ),
                    "in_flight": state.in_flight,
                    "last_cost": state.last_cost,
                    "last_status": state.last_status,
                    "invalid": state.invalid,
                    "initialized": state.initialized,
                }
            )

        return result