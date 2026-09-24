"""Email extraction and Gmail-only validation."""
import re

GMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@gmail\.com$", re.IGNORECASE)
GENERIC_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Role-style local parts that are blocked by the quality filter.
# Matching is exact (after stripping dots/plus-addressing), not substring.
BLOCKED_LOCAL_PARTS = {
    "noreply", "noreply", "donotreply", "donotreply",
    "admin", "administrator", "postmaster", "webmaster", "hostmaster",
    "support", "help", "info", "contact", "sales", "billing",
    "abuse", "security", "privacy", "legal", "jobs", "careers",
    "marketing", "press", "media", "feedback", "hello", "mail",
    "notifications", "notification", "alerts", "alert", "bot", "automated",
}


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def canonical_gmail(email: str | None) -> str:
    """Return the canonical Gmail key for deduplication.

    Gmail ignores dots in the local part and strips ``+suffix`` addressing,
    so ``john.doe+work@gmail.com`` and ``johndoe@gmail.com`` are the same
    inbox and should not be collected twice.
    """
    email = normalize_email(email)
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if domain != "gmail.com":
        return email
    local = local.split("+", 1)[0]
    local = local.replace(".", "")
    return f"{local}@gmail.com"


def is_gmail(email: str | None) -> bool:
    return bool(GMAIL_REGEX.fullmatch(normalize_email(email)))


def _normalize_local_part(local: str) -> str:
    """Strip dots and plus-addressing for exact comparison."""
    local = local.split("+", 1)[0]
    local = local.replace(".", "")
    local = local.replace("-", "")
    local = local.replace("_", "")
    return local


def is_blocked_local_part(email: str | None) -> bool:
    email = normalize_email(email)
    if "@" not in email:
        return True
    local = email.split("@", 1)[0]
    normalized = _normalize_local_part(local)
    return normalized in BLOCKED_LOCAL_PARTS


def is_quality_gmail(email: str | None) -> bool:
    """Optional stricter gate retained from the existing project."""
    return is_gmail(email) and not is_blocked_local_part(email)


def extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(normalize_email(e) for e in GENERIC_EMAIL_REGEX.findall(text)))


def extract_gmails_from_text(text: str, quality_filter: bool = True) -> list[str]:
    candidates = [e for e in extract_emails_from_text(text) if is_gmail(e)]
    if quality_filter:
        candidates = [e for e in candidates if not is_blocked_local_part(e)]
    return candidates
