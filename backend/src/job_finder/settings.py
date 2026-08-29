from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseModel):
    companies_path: Path = BACKEND_ROOT / "data" / "companies.json"
    output_directory: Path = BACKEND_ROOT / "output"
    resumes_directory: Path = BACKEND_ROOT / "data" / "resumes"
    database_url: str | None = None
    auth_enabled: bool = False
    session_days: int = Field(default=30, ge=1, le=365)
    secure_cookies: bool = False
    concurrency: int = Field(default=8, ge=1, le=50)
    browser_pool_wait_seconds: float = Field(default=30.0, gt=0, le=120)
    refresh_after_hours: float = Field(default=24.0, ge=1, le=720)
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (self.output_directory / "job_finder.db").resolve()
        return f"sqlite:///{database_path.as_posix()}"

    @classmethod
    def from_env(cls) -> "AppSettings":
        origins = os.getenv("JOB_FINDER_ALLOWED_ORIGINS")
        return cls(
            companies_path=Path(
                os.getenv("JOB_FINDER_COMPANIES_FILE", BACKEND_ROOT / "data" / "companies.json")
            ).resolve(),
            output_directory=Path(
                os.getenv("JOB_FINDER_OUTPUT_DIR", BACKEND_ROOT / "output")
            ).resolve(),
            resumes_directory=Path(
                os.getenv("JOB_FINDER_RESUMES_DIR", BACKEND_ROOT / "data" / "resumes")
            ).resolve(),
            database_url=os.getenv("DATABASE_URL") or None,
            auth_enabled=os.getenv("JOB_FINDER_AUTH_ENABLED", "1").casefold()
            not in {"0", "false", "no"},
            session_days=int(os.getenv("JOB_FINDER_SESSION_DAYS", "30")),
            secure_cookies=os.getenv("JOB_FINDER_SECURE_COOKIES", "0").casefold()
            in {"1", "true", "yes"},
            concurrency=int(os.getenv("JOB_FINDER_CONCURRENCY", "8")),
            browser_pool_wait_seconds=float(
                os.getenv("JOB_FINDER_BROWSER_POOL_WAIT_SECONDS", "30")
            ),
            refresh_after_hours=float(os.getenv("JOB_FINDER_REFRESH_AFTER_HOURS", "24")),
            allowed_origins=(
                [origin.strip() for origin in origins.split(",") if origin.strip()]
                if origins
                else ["http://localhost:5173", "http://127.0.0.1:5173"]
            ),
        )
