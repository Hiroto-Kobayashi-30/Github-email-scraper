"""Orchestrates discovery -> profile email -> Gmail -> deduplication -> history."""
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
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
from db.history import HistoryDB
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

    # Public-profile email fallback telemetry.
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

        # Fail before creating a misleading empty run when credentials
        # are absent or malformed.
        settings.validate_github_tokens()

        # Reload the complete permanent db.csv at the beginning of every run.
        # This guarantees duplicates from previous runs are never missed.
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

        # Results are written in batches of 20.
        # db.csv remains the permanent source of truth and is updated
        # immediately for every accepted result.
        batch_size = 20
        batch_records: list[dict] = []
        batch_number = 0
        run_path: Path | None = None

        def flush_batch() -> None:
            nonlocal batch_records
            nonlocal batch_number
            nonlocal run_path

            if not batch_records:
                return

            batch_number += 1

            # COUNT is the number of records in THIS batch.
            run_path = self.history.create_batch_export(
                location,
                len(batch_records),
            )

            for record in batch_records:
                self.history.append_to_run(
                    run_path,
                    record,
                )

            batch_records = []

            self.progress.run_csv = str(
                run_path
            )

            self._emit()

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
                    strict_quality_gmail,
                )

                if record is not None:
                    batch_records.append(record)

                    if len(batch_records) >= batch_size:
                        flush_batch()

        except asyncio.CancelledError:
            # Preserve every completed result even when cancelled.
            flush_batch()

            self.progress.status = "cancelled"

            raise

        except Exception as exc:
            flush_batch()

            self.progress.status = "failed"
            self.progress.errors += 1
            self.progress.last_error = str(exc)

        else:
            flush_batch()

            if self.progress.extracted >= target_count:
                self.progress.status = "completed"

            else:
                self.progress.status = "exhausted"

        finally:
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
        strict_quality_gmail: bool,
    ) -> dict | None:

        self.progress.current_stage = "email_filter"
        self._emit()

        started = monotonic()

        # First try the email returned by GraphQL.
        profile_email = user_node.get("email")

        # GraphQL can return null even when the user's public profile
        # exposes an email. Use the public REST profile as a fallback.
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

        # Deduplicate before saving the accepted result.
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

        # --------------------------------------------------------------
        # Account creation year
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Save result
        # --------------------------------------------------------------

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
        }

        # Permanent master database.
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