"""Find the earliest observable commit year for a GitHub user.

Strategy
--------
1. Resolve the GitHub user's GraphQL ID.
2. Enumerate repositories owned by that user.
3. Skip archived repositories and repositories without a default branch.
4. For each repository, search the user's commit history by DATE RANGE.
5. Use a binary search over years instead of walking every commit page.
6. Return the earliest year in which GitHub exposes a matching commit.

Why this is faster
------------------
The old implementation paginated through the entire commit history:

    first: 100
    after: cursor
    ...

A large repository could therefore require hundreds of requests.

The new implementation asks GitHub whether at least one matching commit
exists before a given year. Because "there is a matching commit by year X"
is monotonic, we can binary-search the earliest year.

GitHub's GraphQL Commit.history supports:
    - author
    - since
    - until
    - first

So we can ask for only one matching commit in a date range.
"""

import asyncio
from datetime import datetime, timezone

import httpx


GRAPHQL_URL = "https://api.github.com/graphql"

# GitHub documents the supported GitTimestamp range as 1970-01-01
# through 2099-12-13. We use 1970 as the safe lower boundary.
MIN_COMMIT_YEAR = 1970


# ---------------------------------------------------------------------------
# Resolve GitHub user ID
# ---------------------------------------------------------------------------

USER_ID_QUERY = """
query($login: String!) {
  user(login: $login) {
    id
  }

  rateLimit {
    remaining
    resetAt
    limit
  }
}
"""


# ---------------------------------------------------------------------------
# Enumerate repositories owned by the user
# ---------------------------------------------------------------------------

USER_REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(
      first: 100
      after: $cursor
      ownerAffiliations: OWNER
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      nodes {
        nameWithOwner
        isArchived

        defaultBranchRef {
          name
        }
      }

      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }

  rateLimit {
    remaining
    resetAt
    limit
  }
}
"""


# ---------------------------------------------------------------------------
# Check whether a matching commit exists in a date range.
#
# We intentionally request only ONE commit.
#
# `author: {id: $authorId}` keeps the query restricted to the target
# GitHub user's attributed commits.
#
# `since` and `until` restrict the history by date.
# ---------------------------------------------------------------------------

REPO_COMMIT_EXISTS_QUERY = """
query(
  $owner: String!
  $name: String!
  $branch: String!
  $authorId: ID!
  $since: GitTimestamp
  $until: GitTimestamp
) {
  repository(
    owner: $owner
    name: $name
  ) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(
            first: 1
            author: {id: $authorId}
            since: $since
            until: $until
          ) {
            nodes {
              authoredDate
            }
          }
        }
      }
    }
  }

  rateLimit {
    remaining
    resetAt
    limit
  }
}
"""


class RepoExtractor:
    """Find the earliest observable commit year for a GitHub user."""

    def __init__(self, rate_limiter, repo_limit: int = 100, max_concurrent_repos: int = 5):
        self.rate_limiter = rate_limiter
        self.repo_limit = max(1, repo_limit)
        self.repo_sem = asyncio.Semaphore(max(1, max_concurrent_repos))

        self.client = httpx.AsyncClient(
            timeout=60.0,
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    # ------------------------------------------------------------------
    # GitHub GraphQL request
    # ------------------------------------------------------------------

    async def _post(
        self,
        query: str,
        variables: dict,
    ) -> dict:
        """Execute a GitHub GraphQL request with retries."""

        last_err: str | None = None

        for attempt in range(4):
            token = await self.rate_limiter.wait_if_needed()

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

                # ------------------------------------------------------
                # Invalid token
                # ------------------------------------------------------

                if response.status_code == 401:
                    switched = await self.rate_limiter.mark_invalid(
                        token
                    )

                    last_err = (
                        "GitHub token rejected with HTTP 401 Unauthorized"
                    )

                    if switched:
                        continue

                    raise RuntimeError(
                        "GitHub authentication failed: all configured "
                        "tokens returned HTTP 401 Unauthorized."
                    )

                # ------------------------------------------------------
                # Temporary HTTP errors
                # ------------------------------------------------------

                if response.status_code in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    last_err = (
                        f"HTTP {response.status_code}"
                    )

                    await asyncio.sleep(
                        min(2**attempt, 8)
                    )

                    continue

                response.raise_for_status()

                payload = response.json()

                # ------------------------------------------------------
                # GraphQL errors
                # ------------------------------------------------------

                errors = payload.get("errors")

                if errors:
                    message = errors[0].get(
                        "message",
                        "GraphQL error",
                    )

                    lower_message = message.lower()

                    if (
                        "timeout" in lower_message
                        or "something went wrong" in lower_message
                    ):
                        last_err = message

                        await asyncio.sleep(
                            min(2**attempt, 8)
                        )

                        continue

                    raise RuntimeError(
                        str(errors)
                    )

                data = payload.get("data")

                if data is None:
                    raise RuntimeError(
                        "GitHub GraphQL returned no data."
                    )

                return data

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
            ) as exc:
                last_err = str(exc)

                await asyncio.sleep(
                    min(2**attempt, 8)
                )

        raise RuntimeError(
            f"GitHub GraphQL failed: {last_err}"
        )

    # ------------------------------------------------------------------
    # Resolve user ID
    # ------------------------------------------------------------------

    async def _resolve_user_id(
        self,
        login: str,
    ) -> str | None:
        """Resolve a GitHub login to its GraphQL user ID."""

        data = await self._post(
            USER_ID_QUERY,
            {
                "login": login,
            },
        )

        user = data.get("user") or {}

        return user.get("id")

    # ------------------------------------------------------------------
    # Repository discovery
    # ------------------------------------------------------------------

    async def _iter_owned_repositories(
        self,
        login: str,
    ):
        """Yield repositories owned by the user."""

        cursor: str | None = None
        yielded = 0

        while True:
            data = await self._post(
                USER_REPOS_QUERY,
                {
                    "login": login,
                    "cursor": cursor,
                },
            )

            user = data.get("user") or {}

            repositories = (
                user.get("repositories")
                or {}
            )

            nodes = (
                repositories.get("nodes")
                or []
            )

            for repo in nodes:
                if yielded >= self.repo_limit:
                    return

                yielded += 1

                yield repo

            page_info = (
                repositories.get("pageInfo")
                or {}
            )

            if not page_info.get("hasNextPage"):
                return

            next_cursor = page_info.get("endCursor")

            if not next_cursor:
                return

            if next_cursor == cursor:
                return

            cursor = next_cursor

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _year_start(year: int) -> str:
        """Return the UTC start of a year."""

        return f"{year:04d}-01-01T00:00:00Z"

    @staticmethod
    def _year_end(year: int) -> str:
        """Return the UTC end of a year."""

        return f"{year:04d}-12-31T23:59:59Z"

    # ------------------------------------------------------------------
    # Check whether a user has a matching commit in a date range.
    # ------------------------------------------------------------------

    async def _has_commit_in_range(
        self,
        name_with_owner: str,
        branch_name: str,
        author_id: str,
        since_year: int,
        until_year: int,
    ) -> bool:
        """Return True if GitHub exposes at least one matching commit."""

        if "/" not in name_with_owner:
            return False

        owner, repository_name = (
            name_with_owner.split("/", 1)
        )

        qualified_branch = (
            f"refs/heads/{branch_name}"
        )

        data = await self._post(
            REPO_COMMIT_EXISTS_QUERY,
            {
                "owner": owner,
                "name": repository_name,
                "branch": qualified_branch,
                "authorId": author_id,
                "since": self._year_start(since_year),
                "until": self._year_end(until_year),
            },
        )

        repository = (
            data.get("repository")
            or {}
        )

        ref = (
            repository.get("ref")
            or {}
        )

        target = (
            ref.get("target")
            or {}
        )

        history = (
            target.get("history")
            or {}
        )

        nodes = (
            history.get("nodes")
            or []
        )

        return bool(nodes)

    # ------------------------------------------------------------------
    # Find oldest commit year in one repository.
    # ------------------------------------------------------------------

    async def _oldest_commit_year_for_repo(
        self,
        name_with_owner: str,
        branch_name: str,
        author_id: str,
        search_start_year: int = MIN_COMMIT_YEAR,
    ) -> int | None:
        """Find the earliest observable commit year in one repository.

        This uses binary search over years instead of paginating through
        every commit.

        The predicate is:

            "Does this user have at least one commit on this branch
             on or before year N?"

        That predicate is monotonic:

            False, False, False, True, True, True ...

        Therefore binary search can locate the first year containing
        a matching commit.
        """

        if "/" not in name_with_owner:
            return None

        current_year = datetime.now(
            timezone.utc
        ).year

        search_start_year = max(
            MIN_COMMIT_YEAR,
            min(search_start_year, current_year),
        )

        # First determine whether this repository contains ANY
        # matching commit in the relevant time range.
        has_any = await self._has_commit_in_range(
            name_with_owner=name_with_owner,
            branch_name=branch_name,
            author_id=author_id,
            since_year=search_start_year,
            until_year=current_year,
        )

        if not has_any:
            return None

        low = search_start_year
        high = current_year

        while low < high:
            mid = (low + high) // 2

            has_commit_by_mid = await self._has_commit_in_range(
                name_with_owner=name_with_owner,
                branch_name=branch_name,
                author_id=author_id,
                since_year=search_start_year,
                until_year=mid,
            )

            if has_commit_by_mid:
                high = mid
            else:
                low = mid + 1

        return low

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def first_commit_year(
        self,
        login: str,
        user_id: str | None = None,
        account_created_year: int | None = None,
    ) -> int | None:
        """Return the earliest observable commit year for a GitHub user.

        Repositories are processed in parallel batches (controlled by
        ``max_concurrent_repos``) instead of one at a time. Within each
        batch, every repo's binary search runs concurrently, and the
        earliest year across the batch is kept.
        """

        user_id = (
            user_id
            or await self._resolve_user_id(login)
        )

        if not user_id:
            return None

        earliest_year: int | None = None

        current_year = datetime.now(
            timezone.utc
        ).year

        # If the caller knows when the GitHub account was created,
        # don't search before that year.
        search_start_year = (
            max(MIN_COMMIT_YEAR, account_created_year)
            if account_created_year is not None
            else MIN_COMMIT_YEAR
        )

        # Collect repos into batches so we can process each batch
        # concurrently while preserving the overall oldest-first order
        # (repos are already ordered by CREATED_AT ASC).
        batch: list[dict] = []
        batch_size = max(1, self.repo_sem._value)

        async def _process_repo(repo: dict) -> int | None:
            """Process a single repo's binary search under the concurrency semaphore."""

            if repo.get("isArchived"):
                return None

            default_branch = (
                repo.get("defaultBranchRef")
                or {}
            )

            branch_name = default_branch.get("name")

            if not branch_name:
                return None

            name_with_owner = repo.get("nameWithOwner")

            if not name_with_owner:
                return None

            async with self.repo_sem:
                return await self._oldest_commit_year_for_repo(
                    name_with_owner=name_with_owner,
                    branch_name=branch_name,
                    author_id=user_id,
                    search_start_year=search_start_year,
                )

        async for repo in self._iter_owned_repositories(login):
            batch.append(repo)

            if len(batch) >= batch_size:
                results = await asyncio.gather(
                    *[_process_repo(r) for r in batch],
                    return_exceptions=True,
                )

                for repo_year in results:
                    if isinstance(repo_year, Exception):
                        continue

                    if repo_year is None:
                        continue

                    if (
                        earliest_year is None
                        or repo_year < earliest_year
                    ):
                        earliest_year = repo_year

                # We cannot possibly find an earlier year than the
                # account creation year.
                if (
                    account_created_year is not None
                    and earliest_year is not None
                    and earliest_year <= account_created_year
                ):
                    return earliest_year

                batch.clear()

        # Process any remaining repos in the final partial batch.
        if batch:
            results = await asyncio.gather(
                *[_process_repo(r) for r in batch],
                return_exceptions=True,
            )

            for repo_year in results:
                if isinstance(repo_year, Exception):
                    continue

                if repo_year is None:
                    continue

                if (
                    earliest_year is None
                    or repo_year < earliest_year
                ):
                    earliest_year = repo_year

        return earliest_year

    # ------------------------------------------------------------------
    # Date parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _year(
        iso: str | None,
    ) -> int | None:
        """Extract year from an ISO-8601 timestamp."""

        if not iso:
            return None

        try:
            return datetime.fromisoformat(
                iso.replace(
                    "Z",
                    "+00:00",
                )
            ).year
        except ValueError:
            return None