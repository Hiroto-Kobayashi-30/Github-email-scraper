import json
import time
from core.rejection_cache import RejectionCache


def test_rejection_cache_remembers_negative_decision(tmp_path):
    path = tmp_path / "rejection_cache.json"
    cache = RejectionCache(path, ttl_days=30)
    assert not cache.contains("123", "alice")
    cache.remember_no_public_email("123", "alice")
    assert cache.contains("123", "alice")

    payload = json.loads(path.read_text())
    assert payload["entries"]["id:123"]["reason"] == "no_public_profile_email"


def test_rejection_cache_expires(tmp_path):
    path = tmp_path / "rejection_cache.json"
    cache = RejectionCache(path, ttl_days=1)
    cache.remember_no_public_email("123", "alice")

    payload = json.loads(path.read_text())
    payload["entries"]["id:123"]["checked_at"] = time.time() - 2 * 86400
    path.write_text(json.dumps(payload))

    refreshed = RejectionCache(path, ttl_days=1)
    assert not refreshed.contains("123", "alice")
