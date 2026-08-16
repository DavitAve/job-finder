from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable

from filelock import FileLock, Timeout as FileLockTimeout

from job_finder.crawler import CrawlSettings, ProgressCallback, crawl_companies
from job_finder.excel import load_companies
from job_finder.models import Company, CrawlReport
from job_finder.output import write_report
from job_finder.output import read_latest
from job_finder.lifecycle import apply_job_lifecycle


class CrawlBusyError(RuntimeError):
    pass


@dataclass(slots=True)
class PreparedCrawl:
    companies: list[Company]
    run_id: str
    started_at: datetime
    lock: FileLock


class CrawlService:
    """Shared lock -> crawl -> commit lifecycle for CLI and HTTP callers."""

    def __init__(self, companies_path: Path, output_directory: Path) -> None:
        self.companies_path = companies_path
        self.output_directory = output_directory

    def prepare(
        self,
        *,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> PreparedCrawl:
        companies = load_companies(self.companies_path)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.output_directory / "crawl.lock"))
        try:
            lock.acquire(timeout=0)
        except FileLockTimeout as exc:
            raise CrawlBusyError("A crawl is already running in another process") from exc
        try:
            started_at = started_at or datetime.now(timezone.utc)
            run_id = run_id or started_at.strftime("%Y%m%dT%H%M%S%fZ")
            return PreparedCrawl(companies, run_id, started_at, lock)
        except BaseException:
            lock.release()
            raise

    @staticmethod
    def release(prepared: PreparedCrawl) -> None:
        if prepared.lock.is_locked:
            prepared.lock.release()

    async def execute(
        self,
        prepared: PreparedCrawl,
        settings: CrawlSettings,
        *,
        progress_callback: ProgressCallback | None = None,
        report_transform: Callable[[CrawlReport], CrawlReport] | None = None,
    ) -> CrawlReport:
        try:
            previous = read_latest(self.output_directory)
            report = await crawl_companies(
                prepared.companies,
                settings,
                run_id=prepared.run_id,
                started_at=prepared.started_at,
                progress_callback=progress_callback,
            )
            if report_transform is not None:
                report = report_transform(report)
            if not report.processed_company_ids:
                report = report.model_copy(
                    update={
                        "processed_company_ids": [company.id for company in prepared.companies]
                    }
                )
            report = apply_job_lifecycle(
                report,
                previous,
                {company.name for company in prepared.companies},
            )
            write_report(report, self.output_directory)
            return report
        finally:
            self.release(prepared)

    async def run(
        self,
        settings: CrawlSettings,
        *,
        progress_callback: ProgressCallback | None = None,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> CrawlReport:
        prepared = self.prepare(run_id=run_id, started_at=started_at)
        return await self.execute(
            prepared, settings, progress_callback=progress_callback
        )
