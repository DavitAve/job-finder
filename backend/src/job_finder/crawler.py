from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from job_finder.adapters import AutoAdapter, BlockedError, HttpFetcher
from job_finder.adapters.browser import BrowserRenderer
from job_finder.filtering import normalize_job
from job_finder.models import (
    Company,
    CompanyCrawlResult,
    CompanyStatus,
    CrawlError,
    CrawlReport,
    CrawlStats,
    Job,
)


class CrawlSettings(BaseModel):
    concurrency: int = Field(default=8, ge=1, le=50)
    per_domain: int = Field(default=2, ge=1, le=5)
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    company_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    retries: int = Field(default=2, ge=0, le=5)
    browser_enabled: bool = True
    browser_pages: int = Field(default=2, ge=1, le=5)
    browser_pool_wait_seconds: float = Field(default=30.0, gt=0, le=120)
    respect_robots: bool = True


class Extractor(Protocol):
    async def extract(self, company: Company): ...


ProgressCallback = Callable[
    [CompanyCrawlResult, int, int], Awaitable[None] | None
]


def _status_count(results: list[CompanyCrawlResult], status: CompanyStatus) -> int:
    return sum(result.status == status for result in results)


_UNVERIFIED_WARNING = re.compile(
    r"(?:\b(?:greenhouse|lever|workday|ashby|smartrecruiters|recruitee|workable|"
    r"pinpoint|bamboohr|rippling|staff\.am) "
    r"adapter failed|browser (?:render|pagination) failed|"
    r"playwright (?:unavailable|page pool busy)|"
    r"pagination page failed|careers page could not be verified|"
    r"careers page was not found)",
    re.IGNORECASE,
)
_UNSUPPORTED_WARNING = re.compile(
    r"visible job listings were found, but the parser extracted none",
    re.IGNORECASE,
)


def _is_unverified_extraction(jobs_found: int, warnings: list[str]) -> bool:
    return jobs_found == 0 and any(_UNVERIFIED_WARNING.search(warning) for warning in warnings)


def _is_unsupported_extraction(jobs_found: int, warnings: list[str]) -> bool:
    return jobs_found == 0 and any(_UNSUPPORTED_WARNING.search(warning) for warning in warnings)


async def crawl_companies(
    companies: list[Company],
    settings: CrawlSettings,
    *,
    extractor: Extractor | None = None,
    run_id: str | None = None,
    started_at: datetime | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CrawlReport:
    started_at = started_at or datetime.now(timezone.utc)
    run_id = run_id or started_at.strftime("%Y%m%dT%H%M%S%fZ")
    own_resources = extractor is None
    browser: BrowserRenderer | None = None
    client: httpx.AsyncClient | None = None
    if extractor is None:
        client = httpx.AsyncClient()
        fetcher = HttpFetcher(
            client,
            per_domain=settings.per_domain,
            timeout_seconds=settings.request_timeout_seconds,
            retries=settings.retries,
            respect_robots=settings.respect_robots,
        )
        browser = BrowserRenderer(
            max_pages=settings.browser_pages,
            pool_wait_seconds=settings.browser_pool_wait_seconds,
        )
        extractor = AutoAdapter(
            fetcher,
            browser=browser,
            browser_enabled=settings.browser_enabled,
        )

    queue: asyncio.Queue[tuple[int, Company] | None] = asyncio.Queue()
    for index, company in enumerate(companies):
        queue.put_nowait((index, company))
    for _ in range(min(settings.concurrency, max(len(companies), 1))):
        queue.put_nowait(None)

    results: list[CompanyCrawlResult | None] = [None] * len(companies)
    jobs_by_company: list[list[Job]] = [[] for _ in companies]
    processed_count = 0
    progress_lock = asyncio.Lock()

    async def notify_progress(result: CompanyCrawlResult) -> None:
        nonlocal processed_count
        if progress_callback is None:
            return
        async with progress_lock:
            processed_count += 1
            callback_result = progress_callback(result, processed_count, len(companies))
            if inspect.isawaitable(callback_result):
                await callback_result

    async def process(index: int, company: Company) -> None:
        began = time.monotonic()
        website_url = str(company.website_url)
        careers_url = str(company.careers_url) if company.careers_url else None
        if not company.enabled:
            results[index] = CompanyCrawlResult(
                company_id=company.id,
                company=company.name,
                website_url=website_url,
                careers_url=careers_url,
                status=CompanyStatus.SKIPPED,
            )
            results[index].duration_ms = round((time.monotonic() - began) * 1000)
            await notify_progress(results[index])
            return
        try:
            async with asyncio.timeout(settings.company_timeout_seconds):
                extracted = await extractor.extract(company)
            found_at = datetime.now(timezone.utc)
            normalized = [
                job
                for raw in extracted.jobs
                if (job := normalize_job(raw, company, found_at)) is not None
            ]
            jobs_by_company[index] = normalized
            status = (
                CompanyStatus.SUCCESS
                if normalized
                else CompanyStatus.UNSUPPORTED
                if _is_unsupported_extraction(len(extracted.jobs), extracted.warnings)
                else CompanyStatus.UNVERIFIED
                if _is_unverified_extraction(len(extracted.jobs), extracted.warnings)
                else CompanyStatus.NO_JOBS
            )
            results[index] = CompanyCrawlResult(
                company_id=company.id,
                company=company.name,
                website_url=website_url,
                careers_url=careers_url,
                resolved_careers_url=extracted.resolved_careers_url,
                careers_url_discovered=extracted.careers_url_discovered,
                status=status,
                adapter=extracted.adapter,
                candidates_found=len(extracted.jobs),
                matching_jobs=len(normalized),
                error=(
                    "Vacancy extraction could not be verified; see warnings"
                    if status == CompanyStatus.UNVERIFIED
                    else "Vacancies are visible, but the current parser could not extract them"
                    if status == CompanyStatus.UNSUPPORTED
                    else None
                ),
                warnings=extracted.warnings,
            )
        except BlockedError as exc:
            results[index] = CompanyCrawlResult(
                company_id=company.id,
                company=company.name,
                website_url=website_url,
                careers_url=careers_url,
                status=CompanyStatus.BLOCKED,
                error=str(exc),
            )
        except TimeoutError:
            results[index] = CompanyCrawlResult(
                company_id=company.id,
                company=company.name,
                website_url=website_url,
                careers_url=careers_url,
                status=CompanyStatus.FAILED,
                error=f"Company timeout after {settings.company_timeout_seconds:g}s",
            )
        except Exception as exc:
            results[index] = CompanyCrawlResult(
                company_id=company.id,
                company=company.name,
                website_url=website_url,
                careers_url=careers_url,
                status=CompanyStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if results[index] is not None:
                if results[index].status != CompanyStatus.SKIPPED:
                    results[index].last_crawled_at = datetime.now(timezone.utc)
                results[index].duration_ms = round((time.monotonic() - began) * 1000)
                await notify_progress(results[index])

    async def worker() -> None:
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                await process(*item)
            finally:
                queue.task_done()

    worker_count = min(settings.concurrency, max(len(companies), 1))
    workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
    try:
        await queue.join()
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    finally:
        if own_resources:
            if browser is not None:
                await browser.close()
            if client is not None:
                await client.aclose()

    completed_results = [result for result in results if result is not None]
    all_jobs = [job for company_jobs in jobs_by_company for job in company_jobs]
    def quality(job: Job) -> tuple[int, int, int]:
        return (
            int(job.source_job_id is not None),
            int(job.location is not None),
            len(job.description),
        )

    unique_jobs: dict[str, Job] = {}
    for job in all_jobs:
        existing = unique_jobs.get(job.job_id)
        if existing is None or quality(job) > quality(existing):
            unique_jobs[job.job_id] = job
    deduplicated = sorted(
        unique_jobs.values(), key=lambda job: (job.company.casefold(), job.title.casefold())
    )
    errors = [
        CrawlError(
            company_id=result.company_id,
            company=result.company,
            status=result.status,
            message=result.error or "unknown error",
        )
        for result in completed_results
        if result.status
        in {
            CompanyStatus.BLOCKED,
            CompanyStatus.FAILED,
            CompanyStatus.UNVERIFIED,
            CompanyStatus.UNSUPPORTED,
        }
    ]
    stats = CrawlStats(
        total_companies=len(companies),
        success=_status_count(completed_results, CompanyStatus.SUCCESS),
        no_jobs=_status_count(completed_results, CompanyStatus.NO_JOBS),
        unsupported=_status_count(completed_results, CompanyStatus.UNSUPPORTED),
        blocked=_status_count(completed_results, CompanyStatus.BLOCKED),
        failed=_status_count(completed_results, CompanyStatus.FAILED),
        unverified=_status_count(completed_results, CompanyStatus.UNVERIFIED),
        skipped=_status_count(completed_results, CompanyStatus.SKIPPED),
        jobs_found=len(deduplicated),
        duplicates_removed=len(all_jobs) - len(deduplicated),
    )
    return CrawlReport(
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        stats=stats,
        companies=completed_results,
        errors=errors,
        jobs=deduplicated,
    )
