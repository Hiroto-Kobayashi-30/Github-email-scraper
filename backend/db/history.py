"""Append-only CSV history and per-run export files split into 20-entry batches."""
import csv
import re
import threading
from datetime import datetime
from pathlib import Path

DB_HEADER = [
    "username", "email", "github_username",
    "account_creation_year", "run_id", "scraped_at", "location",
]

EXPORT_HEADER = [
    "github_username", "gmail_address", "username",
    "location", "account_creation_year",
]

EXPORT_BATCH_SIZE = 20


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
                    "run_id": row.get("run_id", "legacy"),
                    "scraped_at": row.get("scraped_at", ""),
                    "location": row.get("location", ""),
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

    def recent_records(self, limit: int = 25, offset: int = 0) -> list[dict]:
        if not self.db_csv_path.exists():
            return []
        with self._lock:
            with self.db_csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        rows.reverse()
        return rows[offset:offset + limit]

    def search_records(self, query: str, limit: int = 100) -> list[dict]:
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
        exports: list[dict] = []
        if not self.exports_dir.exists():
            return exports
        paths: list[Path] = []
        paths.extend(self.exports_dir.rglob("*.csv"))
        paths.extend(self.exports_dir.rglob("*.CSV"))
        for path in sorted(paths, reverse=True):
            stat = path.stat()
            exports.append({
                "path": str(path),
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return exports

    def _batch_export_path(self, location: str, batch_count: int, index: int = 1) -> Path:
        now = datetime.now()
        location_slug = _safe_slug(location)
        date_part = now.strftime("%m_%d")
        base = f"{date_part}_{location_slug}_{int(batch_count)}.csv"
        folder = self.exports_dir
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / base
        if not path.exists():
            return path
        suffix = 2
        while True:
            candidate = folder / f"{date_part}_{location_slug}_{int(batch_count)}_{suffix}.csv"
            if not candidate.exists():
                return candidate
            suffix += 1

    def create_run_exports(
        self,
        location: str,
        records: list[dict],
        batch_size: int = EXPORT_BATCH_SIZE,
    ) -> list[Path]:
        """Split completed run results into CSV files of ``batch_size`` entries each.

        Called once after scraping is finished. Returns the list of created
        file paths. Each file uses the export header with fields:
        github_username, gmail_address, username, location, account_creation_year.
        """
        paths: list[Path] = []
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            path = self._batch_export_path(location, len(chunk))
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=EXPORT_HEADER)
                writer.writeheader()
                for record in chunk:
                    writer.writerow({
                        "github_username": record.get("github_username", ""),
                        "gmail_address": record.get("email", ""),
                        "username": record.get("username", ""),
                        "location": record.get("location", location),
                        "account_creation_year": record.get("account_creation_year", ""),
                    })
            paths.append(path)
        return paths
