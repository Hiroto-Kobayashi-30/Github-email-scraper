"""Pure business rules for candidate filtering."""
from datetime import datetime


def repo_count_in_range(user: dict, min_repos: int, max_repos: int) -> bool:
    count = (user.get("repositories") or {}).get("totalCount")
    return count is not None and min_repos <= count <= max_repos


def account_created_year(user: dict) -> int | None:
    created = user.get("createdAt")
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).year
    except ValueError:
        return None


def passes_initial_filter(user: dict, min_repos: int, max_repos: int) -> tuple[bool, str]:
    if not user.get("login"):
        return False, "no_login"
    if not repo_count_in_range(user, min_repos, max_repos):
        return False, "repo_count_out_of_range"
    if account_created_year(user) is None:
        return False, "no_created_at"
    return True, "ok"

