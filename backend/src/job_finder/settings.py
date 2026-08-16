from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseModel):
    companies_path: Path = BACKEND_ROOT / "data" / "companies.json"
    output_directory: Path = BACKEND_ROOT / "output"
    resumes_directory: Path = BACKEND_ROOT / "data" / "resumes"
    concurrency: int = Field(default=8, ge=1, le=50)
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

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
            concurrency=int(os.getenv("JOB_FINDER_CONCURRENCY", "8")),
            allowed_origins=(
                [origin.strip() for origin in origins.split(",") if origin.strip()]
                if origins
                else ["http://localhost:5173", "http://127.0.0.1:5173"]
            ),
        )
