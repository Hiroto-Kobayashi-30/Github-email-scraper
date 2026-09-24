from scraper.filter_engine import account_created_year, passes_initial_filter


def test_initial_filter_accepts_valid_user():
    user = {
        "login": "alice",
        "createdAt": "2020-05-01T00:00:00Z",
        "repositories": {"totalCount": 10},
    }
    assert passes_initial_filter(user, 5, 20) == (True, "ok")


def test_initial_filter_rejects_repository_range():
    user = {
        "login": "alice",
        "createdAt": "2020-05-01T00:00:00Z",
        "repositories": {"totalCount": 30},
    }
    assert passes_initial_filter(user, 5, 20) == (False, "repo_count_out_of_range")


def test_account_created_year():
    assert account_created_year({"createdAt": "2024-02-03T12:00:00Z"}) == 2024
