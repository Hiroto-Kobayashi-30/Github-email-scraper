import asyncio
from scraper.discovery import Discovery


def test_discovery_has_no_public_profile_rest_fallback():
    assert not hasattr(Discovery, "public_profile_email")


def test_discovery_close_only_closes_graphql_client():
    class Dummy:
        def __init__(self):
            self.closed = False
        async def aclose(self):
            self.closed = True

    discovery = Discovery.__new__(Discovery)
    discovery.client = Dummy()
    asyncio.run(discovery.aclose())
    assert discovery.client.closed is True
