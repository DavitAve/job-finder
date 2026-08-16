import asyncio

from job_finder.adapters.auto import ExtractionResult
from job_finder.crawler import CrawlSettings, crawl_companies
from job_finder.models import Company, CompanyStatus, RawJob


def company(company_id: str) -> Company:
    return Company(
        id=company_id,
        name=company_id.title(),
        website_url=f"https://{company_id}.example.com",
        careers_url=f"https://{company_id}.example.com/jobs",
    )


def company_without_careers(company_id: str) -> Company:
    return Company(
        id=company_id,
        name=company_id.title(),
        website_url=f"https://{company_id}.example.com",
    )


class FakeExtractor:
    async def extract(self, item: Company) -> ExtractionResult:
        if item.id == "slow":
            await asyncio.sleep(0.1)
        if item.id == "broken":
            raise RuntimeError("bad HTML")
        jobs = [
            RawJob(
                title="Frontend Developer",
                url=f"https://{item.id}.example.com/jobs/1?utm_source=a",
                source="test",
            ),
            RawJob(
                title="Frontend Developer",
                url=f"https://{item.id}.example.com/jobs/1?utm_source=b",
                source="test",
            ),
        ]
        return ExtractionResult(jobs=jobs, adapter="test")


async def test_failures_and_timeout_are_isolated_and_jobs_deduplicated() -> None:
    report = await crawl_companies(
        [company("good"), company("slow"), company("broken")],
        CrawlSettings(concurrency=3, company_timeout_seconds=0.02),
        extractor=FakeExtractor(),
    )
    statuses = {result.company_id: result.status for result in report.companies}
    assert statuses == {
        "good": CompanyStatus.SUCCESS,
        "slow": CompanyStatus.FAILED,
        "broken": CompanyStatus.FAILED,
    }
    assert len(report.jobs) == 1
    assert report.stats.duplicates_removed == 1
    assert report.stats.jobs_found == 1


class DistinctRequisitionsExtractor:
    async def extract(self, item: Company) -> ExtractionResult:
        return ExtractionResult(
            jobs=[
                RawJob(
                    title="Frontend Developer",
                    url=f"https://{item.id}.example.com/jobs/1",
                    location="Yerevan",
                    source="greenhouse",
                    source_job_id="1",
                ),
                RawJob(
                    title="Frontend Developer",
                    url=f"https://{item.id}.example.com/jobs/2",
                    location="Yerevan",
                    source="greenhouse",
                    source_job_id="2",
                ),
            ],
            adapter="test",
        )


async def test_distinct_ats_requisitions_are_not_semantically_collapsed() -> None:
    report = await crawl_companies(
        [company("good")],
        CrawlSettings(),
        extractor=DistinctRequisitionsExtractor(),
    )
    assert len(report.jobs) == 2
    assert {job.source_job_id for job in report.jobs} == {"1", "2"}


async def test_disabled_company_advances_progress() -> None:
    disabled = company("disabled").model_copy(update={"enabled": False})
    progress: list[tuple[int, int, CompanyStatus]] = []

    def on_progress(result, processed: int, total: int) -> None:
        progress.append((processed, total, result.status))

    report = await crawl_companies(
        [disabled],
        CrawlSettings(),
        extractor=FakeExtractor(),
        progress_callback=on_progress,
    )
    assert report.stats.skipped == 1
    assert progress == [(1, 1, CompanyStatus.SKIPPED)]


class DiscoveredCareersExtractor:
    async def extract(self, item: Company) -> ExtractionResult:
        return ExtractionResult(
            jobs=[],
            adapter="html",
            resolved_careers_url="https://jobs.example.com/acme",
            careers_url_discovered=True,
        )


async def test_crawler_records_discovered_careers_url() -> None:
    report = await crawl_companies(
        [company("acme")],
        CrawlSettings(),
        extractor=DiscoveredCareersExtractor(),
    )
    result = report.companies[0]
    assert result.resolved_careers_url == "https://jobs.example.com/acme"
    assert result.careers_url_discovered is True


async def test_crawler_report_allows_missing_configured_careers_url() -> None:
    report = await crawl_companies(
        [company_without_careers("acme")],
        CrawlSettings(),
        extractor=DiscoveredCareersExtractor(),
    )
    assert report.companies[0].careers_url is None
