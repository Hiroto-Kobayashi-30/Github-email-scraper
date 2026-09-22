"""Email extraction and Gmail-only validation."""
import re

GMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@gmail\.com$", re.IGNORECASE)
GENERIC_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Kept as an optional quality filter. The user's primary rule is simply @gmail.com.
BLOCKED_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "admin", "administrator", "postmaster", "webmaster", "hostmaster",
    "support", "help", "info", "contact", "sales", "billing",
    "abuse", "security", "privacy", "legal", "jobs", "careers",
    "marketing", "press", "media", "feedback", "hello", "mail",
    "notifications", "notification", "alerts", "alert", "bot", "automated",
}


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def is_gmail(email: str | None) -> bool:
    return bool(GMAIL_REGEX.fullmatch(normalize_email(email)))


def is_blocked_local_part(email: str | None) -> bool:
    email = normalize_email(email)
    if "@" not in email:
        return True
    local = email.split("@", 1)[0]
    normalized = re.sub(r"[.\-_+]", "", local)
    return any(blocked.replace("-", "") in normalized for blocked in BLOCKED_LOCAL_PARTS)


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
