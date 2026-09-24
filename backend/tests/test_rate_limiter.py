import asyncio
from core.rate_limiter import RateLimiter


def test_token_status_before_response():
    limiter = RateLimiter(tokens=["ghp_abcdefghijkl", "ghp_123456789abc", "ghp_xyz987654321"])
    rows = limiter.token_status()
    assert len(rows) == 3
    assert rows[0]["usage_percent"] is None
    assert rows[0]["initialized"] is False


def test_token_status_uses_authoritative_headers_and_cooldown():
    limiter = RateLimiter(tokens=["ghp_abcdefghijkl"])
    token = limiter.tokens[0]
    limiter.update_from_headers({
        "x-ratelimit-remaining": "3750",
        "x-ratelimit-limit": "5000",
        "x-ratelimit-reset": str(__import__("time").time() + 120),
    }, token)
    row = limiter.token_status()[0]
    assert row["usage_percent"] == 25.0
    assert row["remaining"] == 3750

    limiter.note_response(token, 429, {"retry-after": "30"})
    row = limiter.token_status()[0]
    assert row["cooldown_active"] is True
    assert 28 <= row["cooldown_seconds"] <= 30


def test_graphql_rate_limit_updates_state():
    limiter = RateLimiter(tokens=["ghp_abcdefghijkl"])
    token = limiter.tokens[0]
    limiter.record_graphql_result(token, {
        "data": {"rateLimit": {
            "remaining": 4000,
            "limit": 5000,
            "cost": 7,
            "resetAt": "2099-01-01T00:00:00Z",
        }}
    })
    row = limiter.token_status()[0]
    assert row["usage_percent"] == 20.0
    assert row["last_cost"] == 7
