import json
from datetime import datetime, timezone

import pytest

import job_finder.service as service_module
from job_finder.crawler import CrawlSettings
from job_finder.models import CrawlReport, CrawlStats
from job_finder.output import read_latest
from job_finder.service import CrawlBusyError, CrawlService


def write_companies(path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "id": "acme",
                    "name": "Acme",
                    "website_url": "https://example.com",
                    "careers_url": "https://example.com/jobs",
                }
            ]
        ),
        encoding="utf-8",
    )


async def test_service_owns_shared_lock_crawl_and_commit(tmp_path, monkeypatch) -> None:
    companies_path = tmp_path / "companies.json"
    output_directory = tmp_path / "output"
    write_companies(companies_path)
    service = CrawlService(companies_path, output_directory)
    observed: dict[str, object] = {}

    async def fake_crawl(companies, settings, **kwargs):
        observed["companies"] = len(companies)
        observed["run_id"] = kwargs["run_id"]
        with pytest.raises(CrawlBusyError):
            service.prepare()
        return CrawlReport(
            run_id=kwargs["run_id"],
            started_at=kwargs["started_at"],
            finished_at=datetime.now(timezone.utc),
            stats=CrawlStats(total_companies=len(companies)),
            companies=[],
            errors=[],
            jobs=[],
        )

    monkeypatch.setattr(service_module, "crawl_companies", fake_crawl)
    report = await service.run(CrawlSettings(browser_enabled=False))

    assert observed == {"companies": 1, "run_id": report.run_id}
    assert read_latest(output_directory).run_id == report.run_id  # type: ignore[union-attr]
    prepared = service.prepare()
    service.release(prepared)


async def test_service_releases_lock_when_crawl_fails(tmp_path, monkeypatch) -> None:
    companies_path = tmp_path / "companies.json"
    write_companies(companies_path)
    service = CrawlService(companies_path, tmp_path / "output")

    async def fail_crawl(*args, **kwargs):
        raise RuntimeError("catastrophic failure")

    monkeypatch.setattr(service_module, "crawl_companies", fail_crawl)
    with pytest.raises(RuntimeError, match="catastrophic"):
        await service.run(CrawlSettings(browser_enabled=False))

    prepared = service.prepare()
    service.release(prepared)
