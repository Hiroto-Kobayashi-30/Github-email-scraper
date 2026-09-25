"""Orchestrates discovery -> profile email -> Gmail -> deduplication -> history."""
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from time import monotonic
from typing import Callable

from core.config import settings
from core.dedup import DedupStore
from core.gmail_filter import (
    is_gmail,
    is_quality_gmail,
    normalize_email,
)
from core.rate_limiter import RateLimiter
from db.history import HistoryDB, EXPORT_BATCH_SIZE
from scraper.discovery import Discovery
from scraper.filter_engine import passes_initial_filter


@dataclass
class RunProgress:
    run_id: str = ""
    status: str = "idle"
    location: str = ""
    min_repos: int = 0
    max_repos: int = 0
    target: int = 0
    extracted: int = 0
    skipped: int = 0
    skipped_no_email: int = 0
    skipped_not_gmail: int = 0
    skipped_duplicate: int = 0
    skipped_repo_range: int = 0

    profile_email_fallbacks: int = 0
    profile_email_found: int = 0
    profile_email_missing: int = 0

    errors: int = 0
    scanned_users: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    profile_seconds: float = 0.0
    gmail_filter_seconds: float = 0.0
    dedup_seconds: float = 0.0
    current_username: str | None = None
    current_stage: str = "idle"
    run_csv: str | None = None
    run_exports: list[str] = field(default_factory=list)
    last_error: str | None = None
    recent: list[dict] = field(default_factory=list)

    def public(self) -> dict:
        data = asdict(self)

        data["progress_percent"] = (
            round(
                (self.extracted / self.target) * 100,
                1,
            )
            if self.target
            else 0
        )

        return data


class TaskRunner:
    def __init__(
        self,
        on_progress: Callable[[RunProgress], None] | None = None,
    ):
        self.history = HistoryDB(
            settings.db_csv_path,
            settings.exports_dir_path,
        )

        self.dedup = DedupStore(
            settings.db_csv_path
        )

        self.rate_limiter = RateLimiter(
            settings.graphql_point_floor,
            settings.token_list,
            settings.max_concurrent_graphql,
            settings.graphql_points_per_minute,
        )

        self.discovery = Discovery(
            self.rate_limiter
        )

        self.on_progress = on_progress
        self.progress = RunProgress()
        self._started_mono = 0.0

    def _emit(self) -> None:
        self.progress.elapsed_seconds = (
            round(
                monotonic() - self._started_mono,
                2,
            )
            if self._started_mono
            else 0
        )

        if self.on_progress:
            self.on_progress(self.progress)

    async def close(self) -> None:
        await self.discovery.aclose()

    def _finalize_exports(self, location: str, all_records: list[dict]) -> None:
        """Split completed results into 20-entry CSV files after scraping finishes."""
        if not all_records:
            return

        paths = self.history.create_run_exports(
            location,
            all_records,
            batch_size=EXPORT_BATCH_SIZE,
        )

        self.progress.run_exports = [str(p) for p in paths]
        if paths:
            self.progress.run_csv = str(paths[0])

        self._emit()

    async def run(
        self,
        target_count: int,
        location: str,
        min_repos: int,
        max_repos: int,
        start_year: int,
        end_year: int,
        strict_quality_gmail: bool = True,
    ) -> RunProgress:

        settings.validate_github_tokens()

        self.dedup.reload()

        self._started_mono = monotonic()

        run_id = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%dT%H%M%S_%fZ"
        )

        self.progress = RunProgress(
            run_id=run_id,
            status="running",
            location=location,
            min_repos=min_repos,
            max_repos=max_repos,
            target=target_count,
            started_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        all_records: list[dict] = []

        try:
            async for user in self.discovery.stream_users(
                location,
                start_year,
                end_year,
            ):
                if self.progress.extracted >= target_count:
                    break

                self.progress.scanned_users += 1

                login = user.get("login")

                self.progress.current_username = login
                self.progress.current_stage = (
                    "repository_filter"
                )

                self._emit()

                if not login:
                    self.progress.skipped += 1
                    continue

                ok, reason = passes_initial_filter(
                    user,
                    min_repos,
                    max_repos,
                )

                if not ok:
                    self.progress.skipped += 1

                    if reason == "repo_count_out_of_range":
                        self.progress.skipped_repo_range += 1

                    self._emit()
                    continue

                record = await self._process_user(
                    login,
                    user,
                    location,
                    strict_quality_gmail,
                )

                if record is not None:
                    all_records.append(record)

        except asyncio.CancelledError:
            self._finalize_exports(location, all_records)
            self.progress.status = "cancelled"
            raise

        except Exception as exc:
            self._finalize_exports(location, all_records)
            self.progress.status = "failed"
            self.progress.errors += 1
            self.progress.last_error = str(exc)

        else:
            self._finalize_exports(location, all_records)

            if self.progress.extracted >= target_count:
                self.progress.status = "completed"
            else:
                self.progress.status = "exhausted"

        finally:
            await self.close()

            self.progress.finished_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            self.progress.current_stage = "finished"

            self._emit()

        return self.progress

    async def _process_user(
        self,
        login: str,
        user_node: dict,
        location: str,
        strict_quality_gmail: bool,
    ) -> dict | None:

        self.progress.current_stage = "email_filter"
        self._emit()

        started = monotonic()

        profile_email = user_node.get("email")

        if not profile_email:
            self.progress.profile_email_fallbacks += 1
            self._emit()

            try:
                profile_email = (
                    await self.discovery.public_profile_email(
                        login
                    )
                )

            except Exception as exc:
                self.progress.errors += 1
                self.progress.last_error = (
                    f"{login}: public profile email "
                    f"lookup failed: {exc}"
                )

                profile_email = None

            if profile_email:
                self.progress.profile_email_found += 1

            else:
                self.progress.profile_email_missing += 1
                self.progress.skipped += 1
                self.progress.skipped_no_email += 1

                self._emit()
                return None

        email = normalize_email(
            profile_email
        )

        if not is_gmail(email):
            self.progress.skipped += 1
            self.progress.skipped_not_gmail += 1

            self.progress.gmail_filter_seconds += (
                monotonic() - started
            )

            self._emit()
            return None

        if (
            strict_quality_gmail
            and not is_quality_gmail(email)
        ):
            self.progress.skipped += 1
            self.progress.skipped_not_gmail += 1

            self.progress.gmail_filter_seconds += (
                monotonic() - started
            )

            self._emit()
            return None

        self.progress.gmail_filter_seconds += (
            monotonic() - started
        )

        self.progress.current_stage = (
            "deduplication"
        )

        self._emit()

        started = monotonic()

        if self.dedup.contains(email):
            self.progress.dedup_seconds += (
                monotonic() - started
            )

            self.progress.skipped += 1
            self.progress.skipped_duplicate += 1

            self._emit()
            return None

        self.progress.dedup_seconds += (
            monotonic() - started
        )

        created_at = user_node.get(
            "createdAt"
        )

        created_year = None

        if created_at:
            try:
                created_year = int(
                    created_at[:4]
                )
            except (
                TypeError,
                ValueError,
            ):
                created_year = None

        if created_year is None:
            self.progress.skipped += 1
            self._emit()
            return None

        now = datetime.now(
            timezone.utc
        ).isoformat()

        record = {
            "username": login,
            "email": email,
            "github_username": login,
            "account_creation_year": created_year,
            "run_id": self.progress.run_id,
            "scraped_at": now,
            "location": location,
        }

        self.history.append_to_db(
            record
        )

        self.dedup.add(
            email
        )

        self.progress.extracted += 1

        self.progress.recent.insert(
            0,
            {
                "login": login,
                "email": email,
                "account_creation_year": created_year,
            },
        )

        self.progress.recent = (
            self.progress.recent[:25]
        )

        self._emit()

        return record
