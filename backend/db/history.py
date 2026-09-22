"""Append-only CSV history and unique per-run export files."""
import csv
import re
import threading
from datetime import datetime
from pathlib import Path

DB_HEADER = [
    "username", "email", "github_username",
    "account_creation_year", "first_commit_year", "run_id", "scraped_at",
]
RUN_HEADER = DB_HEADER


def _safe_slug(text: str) -> str:
    text = (text or "unknown").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"\s+", "_", text)
    return text or "unknown"


class HistoryDB:
    def __init__(self, db_csv_path: Path, exports_dir: Path):
        self.db_csv_path = db_csv_path
        self.exports_dir = exports_dir
        self._lock = threading.Lock()
        self._ensure_db()
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_db(self) -> None:
        self.db_csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_csv_path.exists() or self.db_csv_path.stat().st_size == 0:
            with self.db_csv_path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(DB_HEADER)
            return

        # Migrate the original 3-column db.csv without losing its history.
        with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_fields = reader.fieldnames or []
            if existing_fields == DB_HEADER:
                return
            rows = list(reader)

        temp = self.db_csv_path.with_suffix(".migration.tmp")
        with temp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=DB_HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "username": row.get("username", ""),
                    "email": row.get("email", ""),
                    "github_username": row.get("github_username", row.get("username", "")),
                    "account_creation_year": row.get("account_creation_year", ""),
                    "first_commit_year": row.get("first_commit_year", ""),
                    "run_id": row.get("run_id", "legacy"),
                    "scraped_at": row.get("scraped_at", ""),
                })
        temp.replace(self.db_csv_path)

    def append_to_db(self, record: dict) -> None:
        with self._lock:
            with self.db_csv_path.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=DB_HEADER).writerow(record)
                f.flush()

    def total_count(self) -> int:
        if not self.db_csv_path.exists():
            return 0
        with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)

    def recent_records(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Return the most recently appended history records (newest first)."""
        if not self.db_csv_path.exists():
            return []
        with self._lock:
            with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        rows.reverse()
        return rows[offset:offset + limit]

    def search_records(self, query: str, limit: int = 100) -> list[dict]:
        """Case-insensitive substring search across username and email."""
        if not self.db_csv_path.exists():
            return []
        q = query.strip().lower()
        if not q:
            return self.recent_records(limit)
        with self._lock:
            with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        matched = [
            r for r in rows
            if q in (r.get("username") or "").lower()
            or q in (r.get("email") or "").lower()
        ]
        matched.reverse()
        return matched[:limit]

    def list_exports(self) -> list[dict]:
        """List all export CSV files with relative paths and sizes."""
        exports: list[dict] = []
        if not self.exports_dir.exists():
            return exports
        for path in sorted(self.exports_dir.rglob("*.csv"), reverse=True):
            stat = path.stat()
            exports.append({
                "path": str(path),
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return exports

    def run_export_path(self, location: str, target_count: int, run_id: str | None = None) -> Path:
        now = datetime.now()
        run_id = run_id or now.strftime("%Y%m%d_%H%M%S_%f")
        folder = self.exports_dir / now.strftime("%m-%d-%Y") / _safe_slug(location)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now.strftime('%m_%d_%Y_%H%M%S')}_{_safe_slug(location)}_{target_count}_{run_id}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RUN_HEADER).writeheader()
        return path

    def append_to_run(self, run_path: Path, record: dict) -> None:
        with self._lock:
            with run_path.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=RUN_HEADER).writerow(record)
                f.flush()
