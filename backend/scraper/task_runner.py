"""Orchestrates discovery -> profile email -> Gmail -> first commit -> history."""
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Callable

from core.config import settings
from core.dedup import DedupStore
from core.gmail_filter import is_gmail, is_quality_gmail, normalize_email
from core.rate_limiter import RateLimiter
from db.history import HistoryDB
from scraper.discovery import Discovery
from scraper.filter_engine import account_created_year, passes_initial_filter, passes_year_rule
from scraper.profile_extractor import ProfileExtractor
from scraper.repo_extractor import RepoExtractor


@dataclass
class RunProgress:
    run_id: str = ""
    status: str = "idle"
    location: str = ""
    min_repos: int = 0
    max_repos: int = 0
    max_scanned_users: int = 200
    target: int = 0
    extracted: int = 0
    skipped: int = 0
    skipped_no_email: int = 0
    skipped_not_gmail: int = 0
    skipped_year_mismatch: int = 0
    skipped_duplicate: int = 0
    skipped_repo_range: int = 0
    errors: int = 0
    scanned_users: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    profile_seconds: float = 0.0
    gmail_filter_seconds: float = 0.0
    first_commit_seconds: float = 0.0
    dedup_seconds: float = 0.0
    current_username: str | None = None
    current_stage: str = "idle"
    run_csv: str | None = None
    last_error: str | None = None
    recent: list[dict] = field(default_factory=list)

    def public(self) -> dict:
        data = asdict(self)
        data["progress_percent"] = round((self.extracted / self.target) * 100, 1) if self.target else 0
        return data


class TaskRunner:
    def __init__(self, on_progress: Callable[[RunProgress], None] | None = None):
        self.history = HistoryDB(settings.db_csv_path, settings.exports_dir_path)
        self.dedup = DedupStore(settings.db_csv_path)
        self.rate_limiter = RateLimiter(settings.graphql_point_floor, settings.token_list)
        self.discovery = Discovery(self.rate_limiter)
        self.profile = ProfileExtractor(settings.max_concurrent_profiles, settings.profile_request_delay_ms)
        self.repo = RepoExtractor(self.rate_limiter, settings.repo_scan_limit, settings.max_concurrent_repos)
        self.on_progress = on_progress
        self.progress = RunProgress()
        self._started_mono = 0.0

    def _emit(self) -> None:
        self.progress.elapsed_seconds = round(monotonic() - self._started_mono, 2) if self._started_mono else 0
        if self.on_progress:
            self.on_progress(self.progress)

    async def close(self) -> None:
        await self.repo.aclose()
        await self.profile.close()

    async def run(
        self,
        target_count: int,
        location: str,
        min_repos: int,
        max_repos: int,
        start_year: int,
        end_year: int,
        strict_quality_gmail: bool = True,
        max_scanned_users: int = 200
    ) -> RunProgress:
        # Fail before creating a misleading empty run when credentials are absent/malformed.
        settings.validate_github_tokens()
        self._started_mono = monotonic()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self.progress = RunProgress(
            run_id=run_id,
            status="running",
            location=location,
            min_repos=min_repos,
            max_repos=max_repos,
            target=target_count,
            max_scanned_users=max_scanned_users,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        run_path = self.history.run_export_path(location, target_count, run_id)
        self.progress.run_csv = str(run_path)
        self._emit()

        try:
            async for user in self.discovery.stream_users(location, start_year, end_year):
                if (
                    self.progress.extracted >= target_count
                    or self.progress.scanned_users >= max_scanned_users
                ):
                    break
                self.progress.scanned_users += 1
                login = user.get("login")
                self.progress.current_username = login
                self.progress.current_stage = "repository_filter"
                self._emit()
                if not login:
                    self.progress.skipped += 1
                    continue

                ok, reason = passes_initial_filter(user, min_repos, max_repos)
                if not ok:
                    self.progress.skipped += 1
                    if reason == "repo_count_out_of_range":
                        self.progress.skipped_repo_range += 1
                    self._emit()
                    continue

                await self._process_user(login, user, run_path, strict_quality_gmail)
        except asyncio.CancelledError:
            self.progress.status = "cancelled"
            raise
        except Exception as exc:
            self.progress.status = "failed"
            self.progress.errors += 1
            self.progress.last_error = str(exc)
        else:
            if self.progress.extracted >= target_count:
                self.progress.status = "completed"
            elif self.progress.scanned_users >= max_scanned_users:
                self.progress.status = "scan_limit_reached"
            else:
                self.progress.status = "exhausted"
        finally:
            self.progress.finished_at = datetime.now(timezone.utc).isoformat()
            self.progress.current_stage = "finished"
            self._emit()
        return self.progress
    async def _process_user(
        self,
        login: str,
        user_node: dict,
        run_path: Path,
        strict_quality_gmail: bool,
    ) -> None:

        # --------------------------------------------------------------
        # Profile email
        # --------------------------------------------------------------

        self.progress.current_stage = "profile_email"
        self._emit()

        started = monotonic()

        profile_email, profile_status = await self.profile.extract(login)

        self.progress.profile_seconds += monotonic() - started

        if not profile_email:
            self.progress.skipped += 1

            if profile_status == "no_profile_email":
                self.progress.skipped_no_email += 1
            else:
                self.progress.errors += 1
                self.progress.last_error = (
                    f"{login}: {profile_status}"
                )

            self._emit()
            return

        email = normalize_email(profile_email)

        # --------------------------------------------------------------
        # Gmail filter
        # --------------------------------------------------------------

        self.progress.current_stage = "gmail_filter"
        self._emit()

        started = monotonic()

        if not is_gmail(email):
            self.progress.skipped += 1
            self.progress.skipped_not_gmail += 1
            self.progress.gmail_filter_seconds += monotonic() - started
            self._emit()
            return

        if strict_quality_gmail and not is_quality_gmail(email):
            self.progress.skipped += 1
            self.progress.skipped_not_gmail += 1
            self.progress.gmail_filter_seconds += monotonic() - started
            self._emit()
            return

        self.progress.gmail_filter_seconds += monotonic() - started

        # --------------------------------------------------------------
        # Account creation year
        # --------------------------------------------------------------

        created_at = user_node.get("createdAt")
        created_year = None

        if created_at:
            try:
                created_year = int(created_at[:4])
            except (TypeError, ValueError):
                created_year = None

        # --------------------------------------------------------------
        # First commit year
        # --------------------------------------------------------------

        self.progress.current_stage = "first_commit_year"
        self._emit()

        started = monotonic()

        try:
            first_year = await self.repo.first_commit_year(
                login,
                user_id=user_node.get("id"),
                account_created_year=created_year,
            )
        except Exception as exc:
            self.progress.first_commit_seconds += (
                monotonic() - started
            )
            self.progress.errors += 1
            self.progress.last_error = f"{login}: {exc}"
            self._emit()
            return

        self.progress.first_commit_seconds += (
            monotonic() - started
        )

        if first_year is None or created_year is None:
            self.progress.skipped += 1
            self.progress.skipped_year_mismatch += 1
            self._emit()
            return

        # --------------------------------------------------------------
        # Year rule
        # --------------------------------------------------------------

        passes, difference = passes_year_rule(
            created_year,
            first_year,
        )

        if not passes:
            self.progress.skipped += 1
            self.progress.skipped_year_mismatch += 1
            self._emit()
            return

        # --------------------------------------------------------------
        # Deduplication
        # --------------------------------------------------------------

        self.progress.current_stage = "deduplication"
        self._emit()

        started = monotonic()

        if self.dedup.contains(email):
            self.progress.dedup_seconds += monotonic() - started
            self.progress.skipped += 1
            self.progress.skipped_duplicate += 1
            self._emit()
            return

        self.progress.dedup_seconds += monotonic() - started

        # --------------------------------------------------------------
        # Save result
        # --------------------------------------------------------------

        now = datetime.now(timezone.utc).isoformat()

        record = {
            "username": login,
            "email": email,
            "github_username": login,
            "account_creation_year": created_year,
            "first_commit_year": first_year,
            "run_id": self.progress.run_id,
            "scraped_at": now,
        }

        self.history.append_to_db(record)
        self.history.append_to_run(run_path, record)
        self.dedup.add(email)

        self.progress.extracted += 1

        self.progress.recent.insert(
            0,
            {
                "login": login,
                "email": email,
                "account_creation_year": created_year,
                "first_commit_year": first_year,
                "difference": difference,
            },
        )

        self.progress.recent = self.progress.recent[:25]

        self._emit()
