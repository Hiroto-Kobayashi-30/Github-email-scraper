"""In-memory deduplication backed by the permanent db.csv history."""
import csv
from pathlib import Path
from threading import Lock


class DedupStore:
    """Loads historical emails once and provides thread-safe O(1) membership checks."""

    def __init__(self, db_csv_path: Path):
        self.db_csv_path = db_csv_path
        self._seen: set[str] = set()
        self._lock = Lock()
        self.reload()

    def reload(self) -> None:
        seen: set[str] = set()
        if self.db_csv_path.exists():
            with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = (row.get("email") or "").strip().lower()
                    if email:
                        seen.add(email)
        with self._lock:
            self._seen = seen

    def contains(self, email: str) -> bool:
        with self._lock:
            return email.strip().lower() in self._seen

    def add(self, email: str) -> None:
        with self._lock:
            self._seen.add(email.strip().lower())

    def size(self) -> int:
        with self._lock:
            return len(self._seen)
