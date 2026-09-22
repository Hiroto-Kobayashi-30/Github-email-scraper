import asyncio

from scraper.contribution_extractor import _safe_year_window, ContributionExtractor


def test_year_window_is_within_one_year():
    start, end = _safe_year_window(2024)
    assert start == "2024-01-01T00:00:00Z"
    assert end == "2024-12-31T23:59:59Z"


def test_first_commit_year_stops_after_first_matching_year():
    class Limiter:
        async def wait_if_needed(self): return "token"
        async def release(self): pass
        def update_from_headers(self, *args): pass
        async def mark_invalid(self, *args): return False
        def retry_delay(self, *args): return 0

    class Fake(ContributionExtractor):
        def __init__(self):
            self.rate_limiter = Limiter()
            self.calls = []
        async def _post(self, variables):
            self.calls.append(variables)
            year = int(variables["from"][:4])
            return {"user": {"contributionsCollection": {"totalCommitContributions": 1 if year == 2018 else 0}}}

    async def run():
        obj = Fake()
        result = await obj.first_commit_year("example", 2017)
        assert result == 2018
        assert len(obj.calls) == 2

    asyncio.run(run())
