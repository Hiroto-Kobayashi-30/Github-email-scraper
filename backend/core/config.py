"""Application configuration loaded from environment/.env."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_tokens: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    max_concurrent_profiles: int = 8
    profile_request_delay_ms: int = 250
    repo_scan_limit: int = 100000
    data_dir: str = "../data"
    db_csv: str = "../data/db.csv"
    exports_dir: str = "../data/exports"
    graphql_point_floor: int = 500
    allowed_origins: str = "http://localhost:3000"

    @property
    def token_list(self) -> list[str]:
        """Parse comma-separated GitHub PATs and normalize common copy/paste artifacts."""
        tokens = []
        for raw in self.github_tokens.split(","):
            token = raw.strip().strip('"').strip("'")
            if token:
                tokens.append(token)
        return tokens

    def validate_github_tokens(self) -> None:
        """Validate token presence/format before a scrape starts.

        GitHub classic PATs start with ``ghp_``. Fine-grained PATs start with
        ``github_pat_``. Both are accepted so the project remains compatible
        with either GitHub PAT type.
        """
        tokens = self.token_list
        if not tokens:
            raise RuntimeError(
                "GITHUB_TOKENS is empty. Add one or more GitHub personal access "
                "tokens to backend/.env."
            )
        unsupported = [t[:10] + "..." for t in tokens if not (t.startswith("ghp_") or t.startswith("github_pat_"))]
        if unsupported:
            raise RuntimeError(
                "Unsupported GitHub token format. Expected classic ghp_ tokens "
                "or fine-grained github_pat_ tokens."
            )

    @property
    def db_csv_path(self) -> Path:
        return (Path(__file__).resolve().parent.parent / self.db_csv).resolve()

    @property
    def exports_dir_path(self) -> Path:
        return (Path(__file__).resolve().parent.parent / self.exports_dir).resolve()

    @property
    def data_dir_path(self) -> Path:
        return (Path(__file__).resolve().parent.parent / self.data_dir).resolve()

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]

    def ensure_dirs(self) -> None:
        self.data_dir_path.mkdir(parents=True, exist_ok=True)
        self.exports_dir_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
