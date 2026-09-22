"""Find candidate GitHub users via GraphQL search, sliced by creation year."""
import asyncio
import httpx
from typing import AsyncIterator

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
        createdAt
        location
        repositories(ownerAffiliations: OWNER) {
          totalCount
        }
      }
    }
  }
  rateLimit { remaining resetAt limit }
}
"""


class Discovery:
    def __init__(self, rate_limiter):
        self.rate_limiter = rate_limiter

    async def _post(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict,
    ) -> dict:
        last_error = None

        for attempt in range(4):
            token = await self.rate_limiter.wait_if_needed()
            try:
                r = await client.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                    timeout=60.0,
                )
                self.rate_limiter.update_from_headers(r.headers, token)

                if r.status_code == 401:
                    switched = await self.rate_limiter.mark_invalid(token)
                    last_error = "GitHub token rejected with HTTP 401 Unauthorized"
                    if switched:
                        continue
                    raise RuntimeError(
                        "GitHub authentication failed: all configured tokens returned HTTP 401 Unauthorized. "
                        "For classic ghp_ tokens, ensure the token is active and includes the public_repo scope."
                    )

                await self.rate_limiter.rotate_if_low()

                if r.status_code in (500, 502, 503, 504):
                    last_error = f"HTTP {r.status_code} on attempt {attempt + 1}"
                    await asyncio.sleep(2 ** attempt)
                    continue

                r.raise_for_status()
                data = r.json()

                if "errors" in data:
                    msg = data["errors"][0].get("message", "")
                    if "Something went wrong" in msg or "timeout" in msg.lower():
                        last_error = msg
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise RuntimeError(f"GraphQL error: {data['errors']}")

                return data["data"]

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"GraphQL failed after 4 attempts. Last error: {last_error}"
        )

    async def stream_users(
        self,
        location: str,
        start_year: int,
        end_year: int,
    ) -> AsyncIterator[dict]:
        """Yield users matching location, one year slice at a time.

        Slices avoid GitHub's 1000-result search cap.
        """
        async with httpx.AsyncClient() as client:
            for year in range(start_year, end_year + 1):
                q = (
                    f'location:"{location}" type:user '
                    f"created:{year}-01-01..{year}-12-31"
                )
                cursor = None
                while True:
                    variables = {"q": q, "cursor": cursor, "pageSize": 100}
                    data = await self._post(client, USER_SEARCH_QUERY, variables)
                    search = data["search"]
                    for node in search["nodes"]:
                        if node:
                            yield node
                    page = search["pageInfo"]
                    if not page["hasNextPage"]:
                        break
                    cursor = page["endCursor"]
                    await asyncio.sleep(1.0)