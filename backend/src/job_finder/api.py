from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from job_finder.crawler import CrawlSettings
from job_finder.company_import import (
    CompanyImportBusyError,
    CompanyImportResult,
    CompanyImportPreview,
    import_companies_xlsx,
    preview_companies_xlsx,
)
from job_finder.company_store import CompanyStoreBusyError, mutate_companies
from job_finder.excel import load_companies
from job_finder.models import Company, CompanyCrawlResult, CompanyStatus, CrawlReport, CrawlStats, Job
from job_finder.output import list_history, read_latest, read_run
from job_finder.partial import merge_partial_report
from job_finder.service import CrawlBusyError, CrawlService, PreparedCrawl
from job_finder.settings import AppSettings
from job_finder.resumes import (
    ResumeBusyError,
    ResumeError,
    ResumeList,
    ResumeMatches,
    ResumeStore,
    score_job,
)


class CrawlState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlScope(StrEnum):
    FULL = "full"
    NEW = "new"
    SELECTED = "selected"


class CrawlRequest(BaseModel):
    scope: CrawlScope = CrawlScope.FULL
    company_ids: list[str] = Field(default_factory=list, max_length=2_000)


class CrawlStatus(BaseModel):
    state: CrawlState = CrawlState.IDLE
    run_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processed: int = 0
    total: int = 0
    jobs_found: int = 0
    success: int = 0
    no_jobs: int = 0
    blocked: int = 0
    failed: int = 0
    skipped: int = 0
    last_company: str | None = None
    error: str | None = None
    scope: CrawlScope = CrawlScope.FULL


class RunSummary(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    stats: CrawlStats


class JobChanges(BaseModel):
    new_jobs: list[Job]
    closed_jobs: list[Job]


class CompanySummary(BaseModel):
    id: str
    name: str
    website_url: str
    careers_url: str | None = None
    configured_careers_url: str | None = None
    resolved_careers_url: str | None = None
    careers_url_discovered: bool = False
    discovery_pending: bool = False
    type: str | None = None
    locations: str | None = None
    remote_compatibility: str | None = None
    frontend_compatibility: str | None = None
    enabled: bool = True
    crawl_status: CompanyStatus | None = None
    jobs_found: int = 0


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website_url: str | None = None
    careers_url: str | None = None
    enabled: bool | None = None
    type: str | None = None
    locations: str | None = None
    remote_compatibility: str | None = None
    frontend_compatibility: str | None = None


class CompanyBulkRequest(BaseModel):
    company_ids: list[str] = Field(min_length=1, max_length=2_000)
    action: Literal["enable", "disable", "delete"]


class CompanyMutationResult(BaseModel):
    changed: int
    total: int
    backup_file: str


class CareersDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    url: str = Field(min_length=1, max_length=2_000)


CrawlAlreadyRunning = CrawlBusyError


class CrawlManager:
    def __init__(self, app_settings: AppSettings) -> None:
        self.app_settings = app_settings
        self.status = CrawlStatus()
        self._task: asyncio.Task[None] | None = None
        self._state_lock = asyncio.Lock()
        self.service = CrawlService(
            app_settings.companies_path, app_settings.output_directory
        )

    async def start(self, request: CrawlRequest | None = None) -> CrawlStatus:
        request = request or CrawlRequest()
        async with self._state_lock:
            if self._task is not None and not self._task.done():
                raise CrawlAlreadyRunning("A crawl is already running")
            try:
                prepared = self.service.prepare()
            except CrawlBusyError as exc:
                raise CrawlAlreadyRunning(str(exc)) from exc
            try:
                all_companies = list(prepared.companies)
                previous = read_latest(self.app_settings.output_directory)
                if request.scope == CrawlScope.NEW:
                    processed = {
                        result.company_id for result in (previous.companies if previous else [])
                    }
                    selected = [company for company in all_companies if company.id not in processed]
                elif request.scope == CrawlScope.SELECTED:
                    requested_ids = set(request.company_ids)
                    known_ids = {company.id for company in all_companies}
                    unknown = sorted(requested_ids - known_ids)
                    if unknown:
                        raise ValueError(f"Unknown company IDs: {', '.join(unknown[:10])}")
                    selected = [company for company in all_companies if company.id in requested_ids]
                else:
                    selected = all_companies
                if not selected:
                    raise ValueError("No companies match the requested crawl scope")
                prepared.companies = selected
            except BaseException:
                self.service.release(prepared)
                raise
            self.status = CrawlStatus(
                state=CrawlState.RUNNING,
                run_id=prepared.run_id,
                started_at=prepared.started_at,
                total=len(selected),
                scope=request.scope,
            )
            try:
                self._task = asyncio.create_task(
                    self._run(prepared, previous, all_companies, request.scope),
                    name=f"crawl-{prepared.run_id}",
                )
            except BaseException:
                self.service.release(prepared)
                raise
            return self.status.model_copy(deep=True)

    async def _run(
        self,
        prepared: PreparedCrawl,
        previous: CrawlReport | None,
        all_companies: list[Company],
        scope: CrawlScope,
    ) -> None:
        def on_progress(result: CompanyCrawlResult, processed: int, total: int) -> None:
            self.status.processed = processed
            self.status.total = total
            self.status.last_company = result.company
            self.status.jobs_found += result.matching_jobs
            if result.status == CompanyStatus.SUCCESS:
                self.status.success += 1
            elif result.status == CompanyStatus.NO_JOBS:
                self.status.no_jobs += 1
            elif result.status == CompanyStatus.BLOCKED:
                self.status.blocked += 1
            elif result.status == CompanyStatus.FAILED:
                self.status.failed += 1
            elif result.status == CompanyStatus.SKIPPED:
                self.status.skipped += 1

        try:
            report = await self.service.execute(
                prepared,
                CrawlSettings(concurrency=self.app_settings.concurrency),
                progress_callback=on_progress,
                report_transform=(
                    None
                    if scope == CrawlScope.FULL
                    else lambda partial: merge_partial_report(
                        previous,
                        partial,
                        all_companies,
                        {company.id for company in prepared.companies},
                        scope.value,
                    )
                ),
            )
            self.status.state = CrawlState.COMPLETED
            self.status.finished_at = report.finished_at
            self.status.jobs_found = report.stats.jobs_found
            self.status.success = report.stats.success
            self.status.no_jobs = report.stats.no_jobs
            self.status.blocked = report.stats.blocked
            self.status.failed = report.stats.failed
            self.status.skipped = report.stats.skipped
        except asyncio.CancelledError:
            self.status.state = CrawlState.FAILED
            self.status.finished_at = datetime.now(timezone.utc)
            self.status.error = "Crawl cancelled"
            raise
        except Exception as exc:
            self.status.state = CrawlState.FAILED
            self.status.finished_at = datetime.now(timezone.utc)
            self.status.error = f"{type(exc).__name__}: {exc}"

    def snapshot(self) -> CrawlStatus:
        return self.status.model_copy(deep=True)


def _summary(report: CrawlReport) -> RunSummary:
    return RunSummary(
        run_id=report.run_id,
        started_at=report.started_at,
        finished_at=report.finished_at,
        stats=report.stats,
    )


def create_app(
    app_settings: AppSettings | None = None,
    manager: CrawlManager | None = None,
) -> FastAPI:
    settings = app_settings or AppSettings.from_env()
    crawl_manager = manager or CrawlManager(settings)
    app = FastAPI(title="Frontend Job Finder API", version="2.0.0")
    app.state.settings = settings
    app.state.crawl_manager = crawl_manager
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    resume_store = ResumeStore(settings.resumes_directory)

    @app.get("/api/resumes", response_model=ResumeList)
    def list_resumes() -> ResumeList:
        try:
            return resume_store.list()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read resumes: {exc}") from exc

    @app.post("/api/resumes", response_model=ResumeList, status_code=status.HTTP_201_CREATED)
    def upload_resume(
        filename: str = Query(..., min_length=1, max_length=255),
        language: Literal["en", "ru"] = Query(...),
        content: bytes = Body(..., media_type="application/pdf"),
    ) -> ResumeList:
        try:
            return resume_store.add(content, filename, language)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/resumes/{resume_id}/activate", response_model=ResumeList)
    def activate_resume(resume_id: str) -> ResumeList:
        try:
            return resume_store.activate(resume_id)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/resumes/{resume_id}", response_model=ResumeList)
    def delete_resume(resume_id: str) -> ResumeList:
        try:
            return resume_store.delete(resume_id)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/resume-matches", response_model=ResumeMatches)
    def resume_matches(run_id: str | None = Query(default=None)) -> ResumeMatches:
        try:
            resume = resume_store.active()
            report = (
                read_run(settings.output_directory, run_id)
                if run_id
                else read_latest(settings.output_directory)
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot calculate resume matches: {exc}") from exc
        if resume is None or report is None:
            return ResumeMatches(active_resume_id=resume.id if resume else None, matches=[])
        return ResumeMatches(
            active_resume_id=resume.id,
            matches=[score_job(job, resume) for job in report.jobs],
        )

    @app.get("/api/companies", response_model=list[CompanySummary])
    async def companies() -> list[CompanySummary]:
        try:
            configured = (
                load_companies(settings.companies_path)
                if settings.companies_path.exists()
                else []
            )
            latest = read_latest(settings.output_directory)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read companies: {exc}") from exc
        latest_by_id = {
            result.company_id: result for result in (latest.companies if latest else [])
        }
        return [
            CompanySummary(
                id=company.id,
                name=company.name,
                website_url=str(company.website_url),
                careers_url=(
                    result.resolved_careers_url
                    if result
                    and result.resolved_careers_url
                    and result.resolved_careers_url
                    not in set(company.metadata.get("Rejected Careers URLs", "").splitlines())
                    else str(company.careers_url) if company.careers_url else None
                ),
                configured_careers_url=str(company.careers_url) if company.careers_url else None,
                resolved_careers_url=result.resolved_careers_url if result else None,
                careers_url_discovered=bool(result and result.careers_url_discovered),
                discovery_pending=bool(
                    result
                    and result.careers_url_discovered
                    and result.resolved_careers_url
                    and result.resolved_careers_url != (str(company.careers_url) if company.careers_url else None)
                    and result.resolved_careers_url
                    not in set(company.metadata.get("Rejected Careers URLs", "").splitlines())
                ),
                type=company.metadata.get("Тип"),
                locations=company.metadata.get("Страна / основные локации"),
                remote_compatibility=company.metadata.get("Remote из Армении"),
                frontend_compatibility=company.metadata.get("Frontend compatibility"),
                enabled=company.enabled,
                crawl_status=result.status if result else None,
                jobs_found=result.matching_jobs if result else 0,
            )
            for company in configured
            for result in [latest_by_id.get(company.id)]
        ]

    def mutate_company_list(mutation) -> tuple[list, Path]:
        try:
            return mutate_companies(
                settings.companies_path, settings.output_directory, mutation
            )
        except CompanyStoreBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/companies/{company_id}", response_model=CompanyMutationResult)
    def update_company(company_id: str, request: CompanyUpdateRequest) -> CompanyMutationResult:
        changed = 0

        def mutation(companies):
            nonlocal changed
            updated = []
            for company in companies:
                if company.id != company_id:
                    updated.append(company)
                    continue
                values = company.model_dump(mode="python")
                metadata = dict(company.metadata)
                for field, key in (
                    ("type", "Тип"),
                    ("locations", "Страна / основные локации"),
                    ("remote_compatibility", "Remote из Армении"),
                    ("frontend_compatibility", "Frontend compatibility"),
                ):
                    if field in request.model_fields_set:
                        value = getattr(request, field)
                        if value:
                            metadata[key] = value
                        else:
                            metadata.pop(key, None)
                for field in ("name", "website_url", "enabled"):
                    if field in request.model_fields_set:
                        values[field] = getattr(request, field)
                if "careers_url" in request.model_fields_set:
                    values["careers_url"] = request.careers_url or None
                values["metadata"] = metadata
                updated.append(Company.model_validate(values))
                changed = 1
            if not changed:
                raise ValueError("Company not found")
            return updated

        updated, backup = mutate_company_list(mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/bulk", response_model=CompanyMutationResult)
    def bulk_companies(request: CompanyBulkRequest) -> CompanyMutationResult:
        selected = set(request.company_ids)
        changed = 0

        def mutation(companies):
            nonlocal changed
            if request.action == "delete":
                changed = sum(company.id in selected for company in companies)
                return [company for company in companies if company.id not in selected]
            enabled = request.action == "enable"
            updated = []
            for company in companies:
                if company.id in selected and company.enabled != enabled:
                    updated.append(company.model_copy(update={"enabled": enabled}))
                    changed += 1
                else:
                    updated.append(company)
            return updated

        updated, backup = mutate_company_list(mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/{company_id}/careers-decision", response_model=CompanyMutationResult)
    def decide_careers(company_id: str, request: CareersDecisionRequest) -> CompanyMutationResult:
        changed = 0

        def mutation(companies):
            nonlocal changed
            updated = []
            for company in companies:
                if company.id != company_id:
                    updated.append(company)
                    continue
                values = company.model_dump(mode="python")
                metadata = dict(company.metadata)
                rejected = set(metadata.get("Rejected Careers URLs", "").splitlines())
                if request.decision == "approve":
                    values["careers_url"] = request.url
                    rejected.discard(request.url)
                else:
                    rejected.add(request.url)
                if rejected:
                    metadata["Rejected Careers URLs"] = "\n".join(sorted(rejected))
                else:
                    metadata.pop("Rejected Careers URLs", None)
                values["metadata"] = metadata
                updated.append(Company.model_validate(values))
                changed = 1
            if not changed:
                raise ValueError("Company not found")
            return updated

        updated, backup = mutate_company_list(mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/import/preview", response_model=CompanyImportPreview)
    def preview_import(
        filename: str = Query(..., min_length=1, max_length=255),
        reset_existing: bool = Query(False),
        deduplicate: bool = Query(True),
        content: bytes = Body(..., media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ) -> CompanyImportPreview:
        if Path(filename).suffix.casefold() != ".xlsx":
            raise HTTPException(status_code=422, detail="Only .xlsx files are supported")
        try:
            return preview_companies_xlsx(
                content,
                companies_path=settings.companies_path,
                reset_existing=reset_existing,
                deduplicate=deduplicate,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Cannot preview XLSX: {exc}") from exc

    @app.post("/api/companies/import", response_model=CompanyImportResult)
    def import_companies(
        filename: str = Query(..., min_length=1, max_length=255),
        reset_existing: bool = Query(False),
        deduplicate: bool = Query(True),
        content: bytes = Body(..., media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ) -> CompanyImportResult:
        if Path(filename).suffix.casefold() != ".xlsx":
            raise HTTPException(status_code=422, detail="Only .xlsx files are supported")
        try:
            return import_companies_xlsx(
                content,
                companies_path=settings.companies_path,
                output_directory=settings.output_directory,
                reset_existing=reset_existing,
                deduplicate=deduplicate,
            )
        except CompanyImportBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Cannot import XLSX: {exc}") from exc

    @app.post(
        "/api/crawls",
        response_model=CrawlStatus,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_crawl(request: CrawlRequest | None = None) -> CrawlStatus:
        try:
            return await crawl_manager.start(request)
        except CrawlAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Cannot start crawl: {exc}") from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot start crawl: {exc}") from exc

    @app.get("/api/crawls/status", response_model=CrawlStatus)
    async def crawl_status() -> CrawlStatus:
        return crawl_manager.snapshot()

    @app.get("/api/runs/latest", response_model=CrawlReport)
    async def latest_run() -> CrawlReport:
        try:
            report = read_latest(settings.output_directory)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read latest run: {exc}") from exc
        if report is None:
            raise HTTPException(status_code=404, detail="No completed crawl exists")
        return report

    @app.get("/api/jobs/changes", response_model=JobChanges)
    async def job_changes() -> JobChanges:
        try:
            latest = read_latest(settings.output_directory)
            history = list_history(settings.output_directory, 1)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read job changes: {exc}") from exc
        if latest is None:
            return JobChanges(new_jobs=[], closed_jobs=[])
        previous = history[0] if history else None
        previous_by_id = {job.job_id: job for job in (previous.jobs if previous else [])}
        latest_ids = {job.job_id for job in latest.jobs}
        return JobChanges(
            new_jobs=[job for job in latest.jobs if job.job_id not in previous_by_id],
            closed_jobs=[job for job in previous_by_id.values() if job.job_id not in latest_ids],
        )

    @app.get("/api/runs/history", response_model=list[RunSummary])
    async def run_history(limit: int = Query(default=3, ge=1, le=3)) -> list[RunSummary]:
        try:
            return [_summary(report) for report in list_history(settings.output_directory, limit)]
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read crawl history: {exc}") from exc

    @app.get("/api/runs/{run_id}", response_model=CrawlReport)
    async def run_details(run_id: str) -> CrawlReport:
        try:
            report = read_run(settings.output_directory, run_id)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read crawl run: {exc}") from exc
        if report is None:
            raise HTTPException(status_code=404, detail="Crawl run not found")
        return report

    return app


app = create_app()
