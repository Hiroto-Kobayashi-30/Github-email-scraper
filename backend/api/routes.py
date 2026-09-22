"""HTTP API for starting and inspecting scraper runs."""
import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from core.config import settings
from scraper.task_runner import TaskRunner

router = APIRouter(prefix="/api")


class StartRunRequest(BaseModel):
    location: str = Field(min_length=1, max_length=120)
    min_repos: int = Field(default=0, ge=0, le=100000)
    max_repos: int = Field(default=100000, ge=0, le=100000)
    target_count: int = Field(default=100, ge=1, le=100000)
    start_year: int = Field(default=2008, ge=2008, le=2100)
    end_year: int = Field(default=2026, ge=2008, le=2100)
    strict_quality_gmail: bool = True
    max_scanned_users: int = Field(default=200, ge=1, le=100000)

    @field_validator("location")
    @classmethod
    def clean_location(cls, value: str) -> str:
        value = " ".join(value.split()).strip()
        if not value:
            raise ValueError("location is required")
        return value

    @field_validator("max_repos")
    @classmethod
    def valid_range(cls, value: int, info):
        min_repos = info.data.get("min_repos", 0)
        if value < min_repos:
            raise ValueError("max_repos must be >= min_repos")
        return value

    @field_validator("end_year")
    @classmethod
    def valid_years(cls, value: int, info):
        start = info.data.get("start_year", 2008)
        if value < start:
            raise ValueError("end_year must be >= start_year")
        return value


class RunManager:
    def __init__(self):
        self.runner: TaskRunner | None = None
        self.task: asyncio.Task | None = None
        self.latest: dict = {"status": "idle"}

    def _progress(self, progress):
        self.latest = progress.public()

    async def start(self, request: StartRunRequest):
        if self.task and not self.task.done():
            raise HTTPException(status_code=409, detail="A scrape is already running")
        self.runner = TaskRunner(on_progress=self._progress)
        self.task = asyncio.create_task(self.runner.run(**request.model_dump()))
        return {"accepted": True}

    async def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            return True
        return False


manager = RunManager()


@router.get("/health")
async def health():
    return {"ok": True, "github_tokens_configured": bool(settings.token_list)}


@router.get("/stats")
async def stats():
    from db.history import HistoryDB
    db = HistoryDB(settings.db_csv_path, settings.exports_dir_path)
    return {"historical_records": db.total_count(), "run": manager.latest}


@router.post("/runs")
async def start_run(request: StartRunRequest):
    if not settings.token_list:
        raise HTTPException(status_code=503, detail="No GitHub token configured on the server")
    return await manager.start(request)


@router.get("/runs/current")
async def current_run():
    return manager.latest


@router.post("/runs/cancel")
async def cancel_run():
    cancelled = await manager.cancel()
    return {"cancelled": cancelled}


@router.get("/history")
async def history(limit: int = 100, offset: int = 0, q: str = ""):
    from db.history import HistoryDB
    db = HistoryDB(settings.db_csv_path, settings.exports_dir_path)
    if q:
        records = db.search_records(q, limit)
    else:
        records = db.recent_records(limit, offset)
    return {"total": db.total_count(), "records": records}


@router.get("/exports")
async def list_exports():
    from db.history import HistoryDB
    db = HistoryDB(settings.db_csv_path, settings.exports_dir_path)
    return {"exports": db.list_exports()}


@router.get("/exports/download")
async def download_export(path: str):
    requested = Path(path).resolve()
    export_root = settings.exports_dir_path.resolve()
    if export_root not in requested.parents or not requested.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(requested, media_type="text/csv", filename=requested.name)


@router.get("/runs/file")
async def run_file(path: str):
    requested = Path(path).resolve()
    export_root = settings.exports_dir_path.resolve()
    if export_root not in requested.parents or not requested.is_file():
        raise HTTPException(status_code=404, detail="Run file not found")
    return FileResponse(requested, media_type="text/csv", filename=requested.name)
