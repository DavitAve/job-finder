from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    website_url: HttpUrl
    careers_url: HttpUrl | None = None
    enabled: bool = True
    adapter: str = "auto"
    adapter_options: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)


class WorkFormat(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobLifecycle(StrEnum):
    NEW = "new"
    ACTIVE = "active"


class RawJob(BaseModel):
    title: str
    url: str
    location: str | None = None
    description: str = ""
    published_at: str | None = None
    remote: bool | None = None
    work_format: WorkFormat | None = None
    source: str
    source_job_id: str | None = None


class Job(BaseModel):
    job_id: str
    company: str
    title: str
    url: str
    location: str | None = None
    remote: bool | None = None
    work_format: WorkFormat = WorkFormat.UNKNOWN
    seniority: str | None = None
    technologies: list[str] = Field(default_factory=list)
    description: str = ""
    published_at: str | None = None
    source: str
    source_job_id: str | None = None
    found_at: datetime
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    lifecycle: JobLifecycle = JobLifecycle.NEW
    match_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_work_format(cls, value: Any) -> Any:
        if isinstance(value, dict) and "work_format" not in value and value.get("remote") is True:
            return {**value, "work_format": WorkFormat.REMOTE}
        return value


class CompanyStatus(StrEnum):
    SUCCESS = "success"
    NO_JOBS = "no_jobs"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class CompanyCrawlResult(BaseModel):
    company_id: str
    company: str
    careers_url: str | None = None
    resolved_careers_url: str | None = None
    careers_url_discovered: bool = False
    status: CompanyStatus
    adapter: str | None = None
    candidates_found: int = 0
    matching_jobs: int = 0
    duration_ms: int = 0
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CrawlError(BaseModel):
    company_id: str
    company: str
    status: CompanyStatus
    message: str


class CrawlStats(BaseModel):
    total_companies: int
    success: int = 0
    no_jobs: int = 0
    blocked: int = 0
    failed: int = 0
    skipped: int = 0
    jobs_found: int = 0
    duplicates_removed: int = 0


class CrawlReport(BaseModel):
    schema_version: str = "2.0"
    scope: str = "full"
    processed_company_ids: list[str] = Field(default_factory=list)
    run_id: str
    started_at: datetime
    finished_at: datetime
    stats: CrawlStats
    companies: list[CompanyCrawlResult]
    errors: list[CrawlError]
    jobs: list[Job]
