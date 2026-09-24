"""Discover GitHub users by location and account-creation year.

The UI's ``start_year``/``end_year`` are ACCOUNT CREATION years. They are
not GraphQL contribution ``from``/``to`` dates, so users may select any
multi-year search range.
"""
import asyncio
from typing import AsyncIterator

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"
USER_SEARCH_QUERY = """
query($q: String!, $cursor: String, $pageSize: Int!) {
  search(query: $q, type: USER, first: $pageSize, after: $cursor) {
    userCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on User {
        id
        login
        name
        email
        createdAt
        location
        repositories(ownerAffiliations: OWNER) {
          totalCount
        }
      }
    }
  }
  rateLimit { remaining resetAt limit cost }
}
"""


class Discovery:
    def __init__(self, rate_limiter):
        self.rate_limiter = rate_limiter

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=45.0,
                write=15.0,
                pool=10.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=5.0,
            ),
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _post(self, query: str, variables: dict) -> dict:
        last_error = None

        for attempt in range(5):
            token = await self.rate_limiter.wait_if_needed(
                estimated_points=10
            )

            try:
                response = await self.client.post(
                    GRAPHQL_URL,
                    json={
                        "query": query,
                        "variables": variables,
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )

                self.rate_limiter.update_from_headers(
                    response.headers,
                    token,
                )

                self.rate_limiter.note_response(
                    token,
                    response.status_code,
                    response.headers,
                )

                if response.status_code == 401:
                    await self.rate_limiter.release(token)

                    switched = await self.rate_limiter.mark_invalid(token)

                    last_error = (
                        "GitHub token rejected with HTTP 401 Unauthorized"
                    )

                    if switched:
                        continue

                    raise RuntimeError(last_error)

                if response.status_code in (403, 429):
                    await self.rate_limiter.release(token)

                    delay = self.rate_limiter.retry_delay(
                        response.headers,
                        attempt,
                    )

                    last_error = (
                        f"GitHub throttled request with HTTP "
                        f"{response.status_code}"
                    )

                    await asyncio.sleep(delay)
                    continue

                if response.status_code in (500, 502, 503, 504):
                    await self.rate_limiter.release(token)

                    last_error = f"HTTP {response.status_code}"

                    await asyncio.sleep(
                        min(2 ** attempt, 16)
                    )

                    continue

                response.raise_for_status()

                payload = response.json()

                self.rate_limiter.record_graphql_result(
                    token,
                    payload,
                )

                self.rate_limiter.clear_cooldown(token)

                await self.rate_limiter.release(token)

                errors = payload.get("errors") or []

                if errors:
                    message = errors[0].get(
                        "message",
                        "GraphQL error",
                    )

                    lower = message.lower()

                    if (
                        "rate limit" in lower
                        or "secondary rate" in lower
                        or "abuse" in lower
                    ):
                        last_error = message

                        await asyncio.sleep(
                            min(2 ** attempt, 16)
                        )

                        continue

                    raise RuntimeError(
                        f"GraphQL error: {errors}"
                    )

                return payload["data"]

            except httpx.TimeoutException as exc:
                # A slow GitHub response is a transport failure, not a fatal
                # scraper failure. Release the slot and retry with backoff.
                await self.rate_limiter.release(token)

                last_error = (
                    f"GitHub request timed out: {exc}"
                )

                await asyncio.sleep(
                    min(2 ** attempt, 16)
                )

            except httpx.RequestError as exc:
                # Includes RemoteProtocolError / ReadError messages such as
                # "Server disconnected without sending a response."
                # Treat these as transient and retry.
                await self.rate_limiter.release(token)

                last_error = (
                    f"GitHub transport error: {exc}"
                )

                await asyncio.sleep(
                    min(2 ** attempt, 16)
                )

        raise RuntimeError(
            "GitHub discovery failed after 5 attempts. "
            f"Last error: {last_error}"
        )

    async def stream_users(
        self,
        location: str,
        start_year: int,
        end_year: int,
    ) -> AsyncIterator[dict]:
        """Yield users matching location and account-creation year.

        The exact location phrase is searched first.

        For multi-word locations, a tokenized fallback is also searched so
        GitHub's search parser does not prematurely exhaust the candidate
        pool.
        """

        seen: set[str] = set()

        location_clean = " ".join(
            location.split()
        ).strip()

        queries = [
            f'location:"{location_clean}" type:user'
        ]

        if " " in location_clean:
            tokens = [
                token
                for token in location_clean.replace(
                    ",",
                    " ",
                ).split()
                if token
            ]

            if tokens:
                fallback = " ".join(
                    f"location:{token}"
                    for token in tokens
                )

                if fallback not in queries:
                    queries.append(
                        fallback + " type:user"
                    )

        for year in range(
            start_year,
            end_year + 1,
        ):
            for base_query in queries:
                q = (
                    f'{base_query} '
                    f'created:{year}-01-01..{year}-12-31'
                )

                cursor = None
                last_cursor = object()

                while True:
                    data = await self._post(
                        USER_SEARCH_QUERY,
                        {
                            "q": q,
                            "cursor": cursor,
                            "pageSize": 100,
                        },
                    )

                    search = data["search"]

                    for node in search["nodes"]:
                        if not node:
                            continue

                        key = str(
                            node.get("id")
                            or node.get("login")
                            or ""
                        )

                        if not key or key in seen:
                            continue

                        seen.add(key)
                        yield node

                    page = search["pageInfo"]

                    if not page["hasNextPage"]:
                        break

                    next_cursor = page["endCursor"]

                    # Guard against a broken/repeated cursor.
                    if (
                        next_cursor == last_cursor
                        or next_cursor == cursor
                        or not next_cursor
                    ):
                        break

                    last_cursor = next_cursor
                    cursor = next_cursor

                    await asyncio.sleep(0.25)