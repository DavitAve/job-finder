from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from job_finder.crawler import CrawlSettings
from job_finder.adapters.base import BlockedError, FetchError, HttpFetcher
from job_finder.company_import import (
    CompanyImportResult,
    CompanyImportPreview,
    merge_companies,
    preview_company_import,
    read_uploaded_companies,
)
from job_finder.database import DatabaseBusyError, DatabaseStore
from job_finder.auth import (
    SESSION_COOKIE,
    AuthService,
    AuthenticationError,
    AuthUser,
    LoginRequest,
    RegisterRequest,
)
from job_finder.excel import write_companies
from job_finder.models import Company, CompanyCrawlResult, CompanyStatus, CrawlReport, CrawlStats, Job
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
    CANCELLED = "cancelled"


class CrawlScope(StrEnum):
    FULL = "full"
    NEW = "new"
    STALE = "stale"
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
    unsupported: int = 0
    blocked: int = 0
    failed: int = 0
    unverified: int = 0
    skipped: int = 0
    last_company: str | None = None
    error: str | None = None
    message: str | None = None
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
    adapter: str = "auto"
    last_adapter: str | None = None
    enabled: bool = True
    crawl_status: CompanyStatus | None = None
    jobs_found: int = 0
    last_crawled_at: datetime | None = None
    refresh_due: bool = True


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website_url: str | None = None
    careers_url: str | None = None
    enabled: bool | None = None
    type: str | None = None
    locations: str | None = None
    remote_compatibility: str | None = None
    frontend_compatibility: str | None = None
    adapter: Literal["auto", "html", "browser"] | None = None


class CompanyDiagnostics(BaseModel):
    company_id: str
    company: str
    configured_adapter: str
    latest_result: CompanyCrawlResult | None = None
    request_url: str
    response_url: str | None = None
    response_status: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    raw_preview: str | None = None
    raw_truncated: bool = False
    fetch_error: str | None = None


class CompanyHistoryItem(BaseModel):
    run_id: str
    checked_at: datetime
    status: CompanyStatus
    careers_url: str | None = None
    adapter: str | None = None
    jobs_found: int = 0
    error: str | None = None
    duration_ms: int = 0


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


class CrawlNotRunning(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RequestContext:
    user: AuthUser
    database: DatabaseStore


def _is_refresh_due(
    result: CompanyCrawlResult | None, cutoff: datetime
) -> bool:
    if result is None or result.last_crawled_at is None:
        return True
    checked_at = result.last_crawled_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return checked_at <= cutoff


class CrawlManager:
    def __init__(self, app_settings: AppSettings, database: DatabaseStore | None = None) -> None:
        self.app_settings = app_settings
        self.database = database or DatabaseStore(app_settings.resolved_database_url)
        if self.database.user_id == "local":
            self.database.bootstrap_legacy(
                app_settings.companies_path, app_settings.output_directory
            )
        else:
            self.database.initialize()
        self.status = CrawlStatus()
        self._task: asyncio.Task[None] | None = None
        self._prepared: PreparedCrawl | None = None
        self._state_lock = asyncio.Lock()
        compatibility_output = (
            app_settings.output_directory
            if self.database.user_id == "local"
            else app_settings.output_directory / "users" / self.database.user_id
        )
        self.service = CrawlService(
            app_settings.companies_path,
            compatibility_output,
            database=self.database,
            lock_path=app_settings.output_directory / "crawl.lock",
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
                previous = self.database.read_latest()
                if request.scope == CrawlScope.NEW:
                    processed = {
                        result.company_id for result in (previous.companies if previous else [])
                    }
                    selected = [company for company in all_companies if company.id not in processed]
                elif request.scope == CrawlScope.STALE:
                    previous_by_id = {
                        result.company_id: result
                        for result in (previous.companies if previous else [])
                    }
                    cutoff = datetime.now(timezone.utc) - timedelta(
                        hours=self.app_settings.refresh_after_hours
                    )
                    selected = [
                        company
                        for company in all_companies
                        if company.enabled
                        and _is_refresh_due(previous_by_id.get(company.id), cutoff)
                    ]
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
                    if request.scope in {CrawlScope.NEW, CrawlScope.STALE}:
                        now = datetime.now(timezone.utc)
                        message = (
                            "No companies are due for refresh. All enabled companies were checked within the refresh interval."
                            if request.scope == CrawlScope.STALE
                            else "No new companies were found. All companies have already been processed."
                        )
                        self.status = CrawlStatus(
                            state=CrawlState.COMPLETED,
                            started_at=now,
                            finished_at=now,
                            total=0,
                            scope=request.scope,
                            message=message,
                        )
                        self.service.release(prepared)
                        return self.status.model_copy(deep=True)
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
                self._prepared = prepared
                self._task = asyncio.create_task(
                    self._run(prepared, previous, all_companies, request.scope),
                    name=f"crawl-{prepared.run_id}",
                )
            except BaseException:
                self._prepared = None
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
            elif result.status == CompanyStatus.UNSUPPORTED:
                self.status.unsupported += 1
            elif result.status == CompanyStatus.BLOCKED:
                self.status.blocked += 1
            elif result.status == CompanyStatus.FAILED:
                self.status.failed += 1
            elif result.status == CompanyStatus.UNVERIFIED:
                self.status.unverified += 1
            elif result.status == CompanyStatus.SKIPPED:
                self.status.skipped += 1

        try:
            report = await self.service.execute(
                prepared,
                CrawlSettings(
                    concurrency=self.app_settings.concurrency,
                    browser_pool_wait_seconds=self.app_settings.browser_pool_wait_seconds,
                ),
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
            self.status.unsupported = report.stats.unsupported
            self.status.blocked = report.stats.blocked
            self.status.failed = report.stats.failed
            self.status.unverified = report.stats.unverified
            self.status.skipped = report.stats.skipped
        except asyncio.CancelledError:
            self.status.state = CrawlState.CANCELLED
            self.status.finished_at = datetime.now(timezone.utc)
            self.status.error = None
            raise
        except Exception as exc:
            self.status.state = CrawlState.FAILED
            self.status.finished_at = datetime.now(timezone.utc)
            self.status.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.service.release(prepared)
            if self._prepared is prepared:
                self._prepared = None

    def snapshot(self) -> CrawlStatus:
        return self.status.model_copy(deep=True)

    async def stop(self) -> CrawlStatus:
        async with self._state_lock:
            task = self._task
            if task is None or task.done() or self.status.state != CrawlState.RUNNING:
                raise CrawlNotRunning("No crawl is currently running")
            prepared = self._prepared
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                if prepared is not None:
                    self.service.release(prepared)
                if self._prepared is prepared:
                    self._prepared = None
            if self.status.state == CrawlState.RUNNING:
                self.status.state = CrawlState.CANCELLED
                self.status.finished_at = datetime.now(timezone.utc)
                self.status.error = None
            return self.snapshot()


def _summary(report: CrawlReport) -> RunSummary:
    return RunSummary(
        run_id=report.run_id,
        started_at=report.started_at,
        finished_at=report.finished_at,
        stats=report.stats,
    )


def _add_missing_company_websites(report: CrawlReport, configured: list[Company]) -> CrawlReport:
    """Enrich legacy snapshots without rewriting their stored JSON."""
    if all(company.website_url for company in report.companies):
        return report
    websites_by_id = {company.id: str(company.website_url) for company in configured}
    websites_by_name = {
        company.name.casefold(): str(company.website_url) for company in configured
    }
    for company in report.companies:
        if company.website_url is None:
            company.website_url = websites_by_id.get(company.company_id) or websites_by_name.get(
                company.company.casefold()
            )
    return report


def _set_session_cookie(response: Response, token: str, settings: AppSettings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def create_app(
    app_settings: AppSettings | None = None,
    manager: CrawlManager | None = None,
) -> FastAPI:
    settings = app_settings or AppSettings.from_env()
    if manager is None:
        crawl_manager = CrawlManager(settings)
        database = crawl_manager.database
    else:
        crawl_manager = manager
        database = DatabaseStore(settings.resolved_database_url)
        database.bootstrap_legacy(settings.companies_path, settings.output_directory)
    app = FastAPI(title="Frontend Job Finder API", version="2.0.0")
    app.state.settings = settings
    app.state.crawl_manager = crawl_manager
    app.state.database = database
    auth_service = AuthService(database, session_days=settings.session_days)
    managers: dict[str, CrawlManager] = {}
    if isinstance(crawl_manager, CrawlManager):
        managers[crawl_manager.database.user_id] = crawl_manager

    def current_context(request: Request) -> RequestContext:
        if not settings.auth_enabled:
            raw = database.find_user_by_id("local")
            return RequestContext(
                user=AuthUser.model_validate(raw),  # type: ignore[arg-type]
                database=database.scoped("local"),
            )
        user = auth_service.resolve(request.cookies.get(SESSION_COOKIE))
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return RequestContext(user=user, database=database.scoped(user.id))

    def manager_for(context: RequestContext):
        if not settings.auth_enabled and manager is not None:
            return crawl_manager
        existing = managers.get(context.user.id)
        if existing is None:
            existing = CrawlManager(settings, context.database)
            managers[context.user.id] = existing
        return existing

    def resume_store_for(context: RequestContext) -> ResumeStore:
        directory = (
            settings.resumes_directory
            if context.user.id == "local"
            else settings.resumes_directory / context.user.id
        )
        return ResumeStore(directory, database=context.database)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/register", response_model=AuthUser, status_code=status.HTTP_201_CREATED)
    def register(request: RegisterRequest, response: Response) -> AuthUser:
        try:
            session = auth_service.register(request)
        except AuthenticationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _set_session_cookie(response, session.token, settings)
        return session.user

    @app.post("/api/auth/login", response_model=AuthUser)
    def login(request: LoginRequest, response: Response) -> AuthUser:
        try:
            session = auth_service.login(request)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        _set_session_cookie(response, session.token, settings)
        return session.user

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request, response: Response) -> None:
        auth_service.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")

    @app.get("/api/auth/me", response_model=AuthUser)
    def me(context: RequestContext = Depends(current_context)) -> AuthUser:
        return context.user

    @app.get("/api/resumes", response_model=ResumeList)
    def list_resumes(context: RequestContext = Depends(current_context)) -> ResumeList:
        try:
            return resume_store_for(context).list()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read resumes: {exc}") from exc

    @app.post("/api/resumes", response_model=ResumeList, status_code=status.HTTP_201_CREATED)
    def upload_resume(
        filename: str = Query(..., min_length=1, max_length=255),
        language: Literal["en", "ru"] = Query(...),
        content: bytes = Body(..., media_type="application/pdf"),
        context: RequestContext = Depends(current_context),
    ) -> ResumeList:
        try:
            return resume_store_for(context).add(content, filename, language)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/resumes/{resume_id}/activate", response_model=ResumeList)
    def activate_resume(
        resume_id: str, context: RequestContext = Depends(current_context)
    ) -> ResumeList:
        try:
            return resume_store_for(context).activate(resume_id)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/resumes/{resume_id}", response_model=ResumeList)
    def delete_resume(
        resume_id: str, context: RequestContext = Depends(current_context)
    ) -> ResumeList:
        try:
            return resume_store_for(context).delete(resume_id)
        except ResumeBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResumeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/resume-matches", response_model=ResumeMatches)
    def resume_matches(
        run_id: str | None = Query(default=None),
        context: RequestContext = Depends(current_context),
    ) -> ResumeMatches:
        try:
            resume = resume_store_for(context).active()
            report = (
                context.database.read_run(run_id)
                if run_id
                else context.database.read_latest()
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
    async def companies(
        context: RequestContext = Depends(current_context),
    ) -> list[CompanySummary]:
        try:
            configured = context.database.list_companies()
            latest = context.database.read_latest()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read companies: {exc}") from exc
        latest_by_id = {
            result.company_id: result for result in (latest.companies if latest else [])
        }
        refresh_cutoff = datetime.now(timezone.utc) - timedelta(
            hours=settings.refresh_after_hours
        )
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
                adapter=company.adapter,
                last_adapter=result.adapter if result else None,
                enabled=company.enabled,
                crawl_status=result.status if result else None,
                jobs_found=result.matching_jobs if result else 0,
                last_crawled_at=result.last_crawled_at if result else None,
                refresh_due=bool(
                    company.enabled
                    and _is_refresh_due(result, refresh_cutoff)
                ),
            )
            for company in configured
            for result in [latest_by_id.get(company.id)]
        ]

    @app.get("/api/companies/{company_id}/diagnostics", response_model=CompanyDiagnostics)
    async def company_diagnostics(
        company_id: str, context: RequestContext = Depends(current_context)
    ) -> CompanyDiagnostics:
        try:
            configured = context.database.list_companies()
            latest = context.database.read_latest()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read company diagnostics: {exc}") from exc
        company = next((item for item in configured if item.id == company_id), None)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        result = next(
            (item for item in (latest.companies if latest else []) if item.company_id == company_id),
            None,
        )
        request_url = str(
            company.careers_url
            or (result.resolved_careers_url if result else None)
            or company.website_url
        )
        diagnostics = CompanyDiagnostics(
            company_id=company.id,
            company=company.name,
            configured_adapter=company.adapter,
            latest_result=result,
            request_url=request_url,
        )
        try:
            async with httpx.AsyncClient() as client:
                page = await HttpFetcher(
                    client,
                    timeout_seconds=10,
                    retries=0,
                    max_response_bytes=2_000_000,
                ).fetch(request_url)
            raw = page.text
            diagnostics.response_url = page.url
            diagnostics.response_status = page.status_code
            diagnostics.response_headers = {
                key: value
                for key in ("content-type", "content-length", "cache-control", "server")
                if (value := page.headers.get(key))
            }
            diagnostics.raw_preview = raw[:50_000]
            diagnostics.raw_truncated = len(raw) > 50_000
        except (BlockedError, FetchError) as exc:
            diagnostics.fetch_error = str(exc)
        return diagnostics

    @app.get("/api/companies/{company_id}/history", response_model=list[CompanyHistoryItem])
    async def company_history(
        company_id: str,
        limit: int = Query(default=5, ge=3, le=5),
        context: RequestContext = Depends(current_context),
    ) -> list[CompanyHistoryItem]:
        try:
            configured = context.database.list_companies()
            latest = context.database.read_latest()
            previous = context.database.list_history(10)
            stored = context.database.read_company_history(company_id, limit=limit)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read company history: {exc}") from exc
        if not any(company.id == company_id for company in configured):
            raise HTTPException(status_code=404, detail="Company not found")
        items: dict[str, CompanyHistoryItem] = {}
        for raw in stored:
            try:
                item = CompanyHistoryItem.model_validate(raw)
            except ValueError:
                continue
            items[item.run_id] = item
        for report in [item for item in [latest, *previous] if item is not None]:
            processed_ids = set(report.processed_company_ids)
            was_processed = (
                company_id in processed_ids
                if processed_ids
                else report.scope == "full"
            )
            if not was_processed or report.run_id in items:
                continue
            result = next(
                (entry for entry in report.companies if entry.company_id == company_id),
                None,
            )
            if result is None or result.status == CompanyStatus.SKIPPED:
                continue
            items[report.run_id] = CompanyHistoryItem(
                run_id=report.run_id,
                checked_at=result.last_crawled_at or report.finished_at,
                status=result.status,
                careers_url=result.resolved_careers_url or result.careers_url,
                adapter=result.adapter,
                jobs_found=result.matching_jobs,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        return sorted(items.values(), key=lambda item: item.checked_at, reverse=True)[:limit]

    def mutate_company_list(
        context: RequestContext, mutation
    ) -> tuple[list, Path]:
        try:
            updated, backup = context.database.mutate_companies(
                mutation,
                lock_path=settings.output_directory / "crawl.lock",
                backup_directory=(
                    settings.output_directory / "import-backups"
                    if context.user.id == "local"
                    else settings.output_directory / "users" / context.user.id / "import-backups"
                ),
            )
            # Compatibility export for CLI tools and easy manual inspection.
            # SQLite remains the source of truth after the first bootstrap.
            export_path = (
                settings.companies_path
                if context.user.id == "local"
                else settings.output_directory / "users" / context.user.id / "companies.json"
            )
            write_companies(export_path, updated)
            return updated, backup
        except DatabaseBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/companies/{company_id}", response_model=CompanyMutationResult)
    def update_company(
        company_id: str,
        request: CompanyUpdateRequest,
        context: RequestContext = Depends(current_context),
    ) -> CompanyMutationResult:
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
                for field in ("name", "website_url", "enabled", "adapter"):
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

        updated, backup = mutate_company_list(context, mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/bulk", response_model=CompanyMutationResult)
    def bulk_companies(
        request: CompanyBulkRequest,
        context: RequestContext = Depends(current_context),
    ) -> CompanyMutationResult:
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

        updated, backup = mutate_company_list(context, mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/{company_id}/careers-decision", response_model=CompanyMutationResult)
    def decide_careers(
        company_id: str,
        request: CareersDecisionRequest,
        context: RequestContext = Depends(current_context),
    ) -> CompanyMutationResult:
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

        updated, backup = mutate_company_list(context, mutation)
        return CompanyMutationResult(changed=changed, total=len(updated), backup_file=str(backup))

    @app.post("/api/companies/import/preview", response_model=CompanyImportPreview)
    def preview_import(
        filename: str = Query(..., min_length=1, max_length=255),
        reset_existing: bool = Query(False),
        deduplicate: bool = Query(True),
        content: bytes = Body(..., media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        context: RequestContext = Depends(current_context),
    ) -> CompanyImportPreview:
        if Path(filename).suffix.casefold() != ".xlsx":
            raise HTTPException(status_code=422, detail="Only .xlsx files are supported")
        try:
            uploaded = read_uploaded_companies(content)
            return preview_company_import(
                context.database.list_companies(),
                uploaded,
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
        context: RequestContext = Depends(current_context),
    ) -> CompanyImportResult:
        if Path(filename).suffix.casefold() != ".xlsx":
            raise HTTPException(status_code=422, detail="Only .xlsx files are supported")
        try:
            uploaded = read_uploaded_companies(content)
            counts: dict[str, int] = {}

            def mutation(existing: list[Company]) -> list[Company]:
                merged, added, skipped = merge_companies(
                    existing,
                    uploaded,
                    reset_existing=reset_existing,
                    deduplicate=deduplicate,
                )
                counts.update(added=added, skipped=skipped)
                return merged

            merged, backup = mutate_company_list(context, mutation)
            return CompanyImportResult(
                uploaded=len(uploaded),
                added=counts["added"],
                duplicates_skipped=counts["skipped"],
                total=len(merged),
                replaced_existing=reset_existing,
                backup_file=str(backup),
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Cannot import XLSX: {exc}") from exc

    @app.post(
        "/api/crawls",
        response_model=CrawlStatus,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_crawl(
        request: CrawlRequest | None = None,
        context: RequestContext = Depends(current_context),
    ) -> CrawlStatus:
        try:
            return await manager_for(context).start(request)
        except CrawlAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Cannot start crawl: {exc}") from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot start crawl: {exc}") from exc

    @app.get("/api/crawls/status", response_model=CrawlStatus)
    async def crawl_status(
        context: RequestContext = Depends(current_context),
    ) -> CrawlStatus:
        return manager_for(context).snapshot()

    @app.post(
        "/api/crawls/stop",
        response_model=CrawlStatus,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def stop_crawl(
        context: RequestContext = Depends(current_context),
    ) -> CrawlStatus:
        try:
            return await manager_for(context).stop()
        except CrawlNotRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/runs/latest", response_model=CrawlReport)
    async def latest_run(
        context: RequestContext = Depends(current_context),
    ) -> CrawlReport:
        try:
            report = context.database.read_latest()
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read latest run: {exc}") from exc
        if report is None:
            raise HTTPException(status_code=404, detail="No completed crawl exists")
        return _add_missing_company_websites(report, context.database.list_companies())

    @app.get("/api/jobs/changes", response_model=JobChanges)
    async def job_changes(
        context: RequestContext = Depends(current_context),
    ) -> JobChanges:
        try:
            latest = context.database.read_latest()
            history = context.database.list_history(1)
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
    async def run_history(
        limit: int = Query(default=3, ge=1, le=3),
        context: RequestContext = Depends(current_context),
    ) -> list[RunSummary]:
        try:
            return [_summary(report) for report in context.database.list_history(limit)]
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read crawl history: {exc}") from exc

    @app.get("/api/runs/{run_id}", response_model=CrawlReport)
    async def run_details(
        run_id: str, context: RequestContext = Depends(current_context)
    ) -> CrawlReport:
        try:
            report = context.database.read_run(run_id)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read crawl run: {exc}") from exc
        if report is None:
            raise HTTPException(status_code=404, detail="Crawl run not found")
        return _add_missing_company_websites(report, context.database.list_companies())

    return app


app = create_app()
