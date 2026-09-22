"""Find the earliest observable commit year without repository enumeration.

GitHub limits a ContributionsCollection time window to at most one year.
The scraper therefore makes one one-year query per candidate year. The
business rule only needs to know whether the first commit is within four
calendar years of account creation, so at most four contribution queries
are needed per candidate.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"

COMMIT_YEAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
    }
  }
  rateLimit { remaining resetAt limit cost }
}
"""


def _safe_year_window(year: int) -> tuple[str, str]:
    """Return a strictly-less-than-one-year UTC window for one calendar year."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_exclusive = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    # End one second before the next calendar year. This avoids an accidental
    # >1-year span while still covering the complete requested calendar year.
    end = end_exclusive - timedelta(seconds=1)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


class ContributionExtractor:
    def __init__(self, rate_limiter):
        self.rate_limiter = rate_limiter
        self.client = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _post(self, variables: dict) -> dict:
        last_error = None
        for attempt in range(5):
            token = await self.rate_limiter.wait_if_needed()
            try:
                response = await self.client.post(
                    GRAPHQL_URL,
                    json={"query": COMMIT_YEAR_QUERY, "variables": variables},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
                self.rate_limiter.update_from_headers(response.headers, token)
                self.rate_limiter.note_response(token, response.status_code, response.headers)

                if response.status_code == 401:
                    await self.rate_limiter.release(token)
                    switched = await self.rate_limiter.mark_invalid(token)
                    last_error = "GitHub token rejected with HTTP 401 Unauthorized"
                    if switched:
                        continue
                    raise RuntimeError(last_error)

                if response.status_code in (403, 429):
                    await self.rate_limiter.release(token)
                    last_error = f"GitHub throttled request with HTTP {response.status_code}"
                    await asyncio.sleep(self.rate_limiter.retry_delay(response.headers, attempt))
                    continue

                if response.status_code in (500, 502, 503, 504):
                    await self.rate_limiter.release(token)
                    last_error = f"HTTP {response.status_code}"
                    await asyncio.sleep(min(2 ** attempt, 16))
                    continue

                response.raise_for_status()
                payload = response.json()
                self.rate_limiter.record_graphql_result(token, payload)
                self.rate_limiter.clear_cooldown(token)
                await self.rate_limiter.release(token)
                errors = payload.get("errors") or []
                if errors:
                    message = errors[0].get("message", "GraphQL error")
                    lower = message.lower()
                    if "rate limit" in lower or "secondary rate" in lower or "abuse" in lower or "timeout" in lower:
                        last_error = message
                        await asyncio.sleep(min(2 ** attempt, 16))
                        continue
                    raise RuntimeError(f"GraphQL error: {errors}")
                return payload["data"]
            except httpx.TimeoutException as exc:
                await self.rate_limiter.release(token)
                last_error = f"Timeout: {exc}"
                await asyncio.sleep(min(2 ** attempt, 16))

        raise RuntimeError(f"Contribution query failed after 5 attempts. Last error: {last_error}")

    async def first_commit_year(self, login: str, account_created_year: int) -> int | None:
        """Return the first year with a visible GitHub commit contribution.

        Only years account_created_year through account_created_year + 3 are
        needed for the project's ``difference < 4`` acceptance rule.
        """
        for year in range(account_created_year, account_created_year + 4):
            from_ts, to_ts = _safe_year_window(year)
            data = await self._post({"login": login, "from": from_ts, "to": to_ts})
            collection = (data.get("user") or {}).get("contributionsCollection")
            if not collection:
                return None
            if int(collection.get("totalCommitContributions") or 0) > 0:
                return year
        return None
