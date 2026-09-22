"""Fetch public GitHub profiles and extract profile-visible emails."""
import asyncio
import re

import httpx

from core.gmail_filter import extract_emails_from_text


PROFILE_URL = "https://github.com/{username}"
MAILTO_RE = re.compile(r'mailto:([^"\'<>\s]+)', re.IGNORECASE)


class ProfileExtractor:
    def __init__(
        self,
        concurrency: int,
        delay_ms: int,
        client: httpx.AsyncClient | None = None,
    ):
        self.sem = asyncio.Semaphore(max(1, concurrency))
        self.delay = max(0, delay_ms) / 1000.0
        self.client = client
        self.owns_client = client is None

        self.headers = {
            "User-Agent": "github-email-scraper/1.0",
            "Accept": "text/html,application/xhtml+xml",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=20.0,
                    write=10.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
            )
        return self.client

    async def close(self) -> None:
        if self.client is not None and self.owns_client:
            await self.client.aclose()
            self.client = None

    async def extract(self, username: str) -> tuple[str | None, str]:
        """Return (email, status)."""

        async with self.sem:
            try:
                client = await self._get_client()

                for attempt in range(3):
                    try:
                        response = await client.get(
                            PROFILE_URL.format(username=username),
                            headers=self.headers,
                        )

                        if response.status_code == 404:
                            return None, "profile_not_found"

                        if response.status_code == 429:
                            retry_after = response.headers.get("Retry-After")

                            if retry_after:
                                try:
                                    wait_seconds = min(float(retry_after), 30.0)
                                except ValueError:
                                    wait_seconds = 2 ** attempt
                            else:
                                wait_seconds = 2 ** attempt

                            if attempt < 2:
                                await asyncio.sleep(wait_seconds)
                                continue

                            return None, "profile_rate_limited"

                        if response.status_code in (500, 502, 503, 504):
                            if attempt < 2:
                                await asyncio.sleep(2 ** attempt)
                                continue

                            return None, f"profile_http_{response.status_code}"

                        if response.status_code != 200:
                            return None, f"profile_http_{response.status_code}"

                        html = response.text
                        break

                    except httpx.TimeoutException as exc:
                        if attempt == 2:
                            return None, f"profile_timeout:{type(exc).__name__}"

                        await asyncio.sleep(2 ** attempt)

                    except httpx.RequestError as exc:
                        if attempt == 2:
                            return None, f"profile_request_error:{type(exc).__name__}"

                        await asyncio.sleep(2 ** attempt)

                else:
                    return None, "profile_request_failed"

            finally:
                if self.delay:
                    await asyncio.sleep(self.delay)

        candidates = []

        for match in MAILTO_RE.findall(html):
            candidates.extend(extract_emails_from_text(match))

        candidates.extend(extract_emails_from_text(html))

        candidates = list(dict.fromkeys(candidates))

        if candidates:
            return candidates[0], "email_found"

        return None, "no_profile_email"