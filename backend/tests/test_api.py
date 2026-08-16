import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openpyxl import Workbook

from job_finder.api import CrawlAlreadyRunning, CrawlManager, CrawlState, CrawlStatus, create_app
from job_finder.excel import REQUIRED_COLUMNS, load_companies
from job_finder.models import CompanyCrawlResult, CompanyStatus, CrawlReport, CrawlStats
from job_finder.output import write_report
from job_finder.settings import AppSettings


class DummyManager:
    def __init__(self) -> None:
        self.running = False
        self.value = CrawlStatus()

    async def start(self, request=None) -> CrawlStatus:
        if self.running:
            raise CrawlAlreadyRunning("A crawl is already running")
        self.running = True
        self.value = CrawlStatus(
            state=CrawlState.RUNNING,
            run_id="20260101T000000000000Z",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            total=173,
        )
        return self.value

    def snapshot(self) -> CrawlStatus:
        return self.value


def make_report(run_id: str, minute: int) -> CrawlReport:
    moment = datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)
    return CrawlReport(
        run_id=run_id,
        started_at=moment,
        finished_at=moment,
        stats=CrawlStats(total_companies=173),
        companies=[],
        errors=[],
        jobs=[],
    )


def test_api_contract_and_concurrent_crawl_conflict(tmp_path) -> None:
    settings = AppSettings(
        companies_path=tmp_path / "companies.json",
        output_directory=tmp_path / "output",
    )
    settings.companies_path.write_text(
        '[{"id":"acme","name":"Acme","website_url":"https://acme.example",'
        '"careers_url":null,"metadata":{"Тип":"SaaS",'
        '"Страна / основные локации":"Armenia"}}]',
        encoding="utf-8",
    )
    first = make_report("20260101T000000000000Z", 0)
    second = make_report("20260101T000100000000Z", 1)
    write_report(first, settings.output_directory)
    write_report(second, settings.output_directory)
    client = TestClient(create_app(settings, DummyManager()))  # type: ignore[arg-type]

    assert client.get("/api/health").json() == {"status": "ok"}
    companies = client.get("/api/companies")
    assert companies.status_code == 200
    assert companies.json() == [
        {
            "id": "acme",
            "name": "Acme",
            "website_url": "https://acme.example/",
            "careers_url": None,
            "configured_careers_url": None,
            "resolved_careers_url": None,
            "careers_url_discovered": False,
            "discovery_pending": False,
            "type": "SaaS",
            "locations": "Armenia",
            "remote_compatibility": None,
            "frontend_compatibility": None,
            "enabled": True,
            "crawl_status": None,
            "jobs_found": 0,
        }
    ]
    response = client.post("/api/crawls")
    assert response.status_code == 202
    assert response.json()["total"] == 173
    assert response.json()["blocked"] == 0
    assert response.json()["failed"] == 0
    assert client.post("/api/crawls").status_code == 409
    assert client.get("/api/crawls/status").json()["state"] == "running"
    assert client.get("/api/runs/latest").json()["run_id"] == second.run_id
    history = client.get("/api/runs/history?limit=3")
    assert history.status_code == 200
    assert [item["run_id"] for item in history.json()] == [first.run_id]
    assert client.get(f"/api/runs/{first.run_id}").status_code == 200
    assert client.get("/api/runs/not-valid").status_code == 404
    assert client.get("/api/runs/history?limit=4").status_code == 422


async def test_crawl_manager_exposes_live_and_final_status_counts(tmp_path) -> None:
    settings = AppSettings(
        companies_path=tmp_path / "companies.json",
        output_directory=tmp_path / "output",
    )
    manager = CrawlManager(settings)
    progress_ready = asyncio.Event()
    finish = asyncio.Event()
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prepared = SimpleNamespace(
        companies=[object(), object(), object()],
        run_id="20260101T000000000000Z",
        started_at=started_at,
    )

    class FakeService:
        def prepare(self):
            return prepared

        @staticmethod
        def release(value) -> None:
            pass

        async def execute(self, value, crawl_settings, *, progress_callback, report_transform=None):
            progress_callback(
                CompanyCrawlResult(
                    company_id="ok",
                    company="OK",
                    careers_url="https://example.com/ok",
                    status=CompanyStatus.SUCCESS,
                    matching_jobs=2,
                ),
                1,
                3,
            )
            progress_callback(
                CompanyCrawlResult(
                    company_id="blocked",
                    company="Blocked",
                    careers_url="https://example.com/blocked",
                    status=CompanyStatus.BLOCKED,
                ),
                2,
                3,
            )
            progress_ready.set()
            await finish.wait()
            return CrawlReport(
                run_id=value.run_id,
                started_at=value.started_at,
                finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
                stats=CrawlStats(total_companies=3, success=1, blocked=1, failed=1, jobs_found=2),
                companies=[],
                errors=[],
                jobs=[],
            )

    manager.service = FakeService()  # type: ignore[assignment]
    await manager.start()
    await progress_ready.wait()
    live = manager.snapshot()
    assert (live.processed, live.success, live.blocked, live.failed, live.jobs_found) == (2, 1, 1, 0, 2)

    finish.set()
    assert manager._task is not None
    await manager._task
    completed = manager.snapshot()
    assert completed.state == CrawlState.COMPLETED
    assert (completed.success, completed.blocked, completed.failed, completed.jobs_found) == (1, 1, 1, 2)


def test_company_xlsx_import_endpoint_uses_safe_defaults(tmp_path) -> None:
    settings = AppSettings(
        companies_path=tmp_path / "companies.json",
        output_directory=tmp_path / "output",
    )
    settings.companies_path.write_text(
        '[{"id":"acme","name":"Acme","website_url":"https://acme.example"}]',
        encoding="utf-8",
    )
    company_header = next(
        header for header in REQUIRED_COLUMNS if header not in {"Website", "Careers / Jobs"}
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([company_header, "Website", "Careers / Jobs"])
    sheet.append(["Acme", "https://acme.example", None])
    sheet.append(["New Company", "https://new.example", None])
    stream = BytesIO()
    workbook.save(stream)
    client = TestClient(create_app(settings, DummyManager()))  # type: ignore[arg-type]

    response = client.post(
        "/api/companies/import?filename=companies.xlsx",
        content=stream.getvalue(),
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    assert response.status_code == 200
    assert response.json()["added"] == 1
    assert response.json()["duplicates_skipped"] == 1
    assert response.json()["total"] == 2


def test_clean_clone_returns_empty_company_list(tmp_path) -> None:
    settings = AppSettings(
        companies_path=tmp_path / "data" / "companies.json",
        output_directory=tmp_path / "output",
        resumes_directory=tmp_path / "resumes",
    )
    client = TestClient(create_app(settings, DummyManager()))  # type: ignore[arg-type]

    response = client.get("/api/companies")

    assert response.status_code == 200
    assert response.json() == []


def test_company_preview_and_management_endpoints(tmp_path) -> None:
    settings = AppSettings(
        companies_path=tmp_path / "companies.json",
        output_directory=tmp_path / "output",
    )
    settings.companies_path.write_text(
        '[{"id":"acme","name":"Acme","website_url":"https://acme.example"},'
        '{"id":"other","name":"Other","website_url":"https://other.example"}]',
        encoding="utf-8",
    )
    company_header = next(
        header for header in REQUIRED_COLUMNS if header not in {"Website", "Careers / Jobs"}
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([company_header, "Website", "Careers / Jobs"])
    sheet.append(["Acme", "https://acme.example", None])
    sheet.append(["New Company", "https://new.example", None])
    stream = BytesIO()
    workbook.save(stream)
    client = TestClient(create_app(settings, DummyManager()))  # type: ignore[arg-type]

    preview = client.post(
        "/api/companies/import/preview?filename=companies.xlsx",
        content=stream.getvalue(),
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    assert preview.status_code == 200
    assert preview.json()["validation_errors"] == []
    assert preview.json()["would_add"] == 1
    assert preview.json()["duplicates_found"] == 1
    assert len(load_companies(settings.companies_path)) == 2

    updated = client.patch(
        "/api/companies/acme",
        json={"name": "Acme Updated", "careers_url": "https://acme.example/jobs"},
    )
    assert updated.status_code == 200
    assert updated.json()["changed"] == 1
    disabled = client.post(
        "/api/companies/bulk",
        json={"company_ids": ["other"], "action": "disable"},
    )
    assert disabled.status_code == 200
    decision = client.post(
        "/api/companies/acme/careers-decision",
        json={"decision": "reject", "url": "https://jobs.example/acme"},
    )
    assert decision.status_code == 200

    companies = {company.id: company for company in load_companies(settings.companies_path)}
    assert companies["acme"].name == "Acme Updated"
    assert str(companies["acme"].careers_url) == "https://acme.example/jobs"
    assert "https://jobs.example/acme" in companies["acme"].metadata["Rejected Careers URLs"]
    assert companies["other"].enabled is False
