from datetime import datetime, timedelta, timezone

from job_finder.database import DatabaseStore
from job_finder.models import Company, CompanyCrawlResult, CompanyStatus, CrawlReport, CrawlStats


def make_store(tmp_path, *, user_id: str = "local") -> DatabaseStore:
    store = DatabaseStore(f"sqlite:///{(tmp_path / 'job_finder.db').as_posix()}", user_id=user_id)
    store.initialize()
    return store


def report(index: int, company_id: str = "acme") -> CrawlReport:
    moment = datetime(2026, 8, 28, tzinfo=timezone.utc) + timedelta(minutes=index)
    return CrawlReport(
        run_id=moment.strftime("%Y%m%dT%H%M%S000000Z"),
        started_at=moment,
        finished_at=moment + timedelta(seconds=2),
        stats=CrawlStats(total_companies=1, no_jobs=1),
        processed_company_ids=[company_id],
        companies=[CompanyCrawlResult(
            company_id=company_id,
            company="Acme",
            website_url="https://acme.example",
            careers_url="https://acme.example/jobs",
            status=CompanyStatus.NO_JOBS,
            adapter="html",
            last_crawled_at=moment,
            duration_ms=2000,
        )],
        errors=[],
        jobs=[],
    )


def test_database_isolates_company_lists_by_user(tmp_path) -> None:
    local = make_store(tmp_path)
    second = make_store(tmp_path, user_id="second-user")
    local.replace_companies([Company(id="acme", name="Acme", website_url="https://acme.example")])
    second.replace_companies([Company(id="other", name="Other", website_url="https://other.example")])

    assert [item.id for item in local.list_companies()] == ["acme"]
    assert [item.id for item in second.list_companies()] == ["other"]


def test_database_stores_latest_three_previous_runs_and_company_history(tmp_path) -> None:
    store = make_store(tmp_path)
    store.replace_companies([Company(id="acme", name="Acme", website_url="https://acme.example")])
    reports = [report(index) for index in range(5)]
    for item in reports:
        store.write_report(item)

    assert store.read_latest().run_id == reports[-1].run_id  # type: ignore[union-attr]
    assert [item.run_id for item in store.list_history(10)] == [
        reports[3].run_id,
        reports[2].run_id,
        reports[1].run_id,
    ]
    history = store.read_company_history("acme", limit=5)
    assert [item["run_id"] for item in history] == [
        reports[4].run_id,
        reports[3].run_id,
        reports[2].run_id,
        reports[1].run_id,
        reports[0].run_id,
    ]
    assert history[0]["adapter"] == "html"


def test_database_bootstraps_legacy_json_only_once(tmp_path) -> None:
    companies_path = tmp_path / "companies.json"
    output = tmp_path / "output"
    companies_path.write_text(
        '[{"id":"acme","name":"Acme","website_url":"https://acme.example"}]',
        encoding="utf-8",
    )
    store = make_store(tmp_path)
    store.bootstrap_legacy(companies_path, output)
    companies_path.write_text(
        '[{"id":"changed","name":"Changed","website_url":"https://changed.example"}]',
        encoding="utf-8",
    )
    store.bootstrap_legacy(companies_path, output)

    assert [item.id for item in store.list_companies()] == ["acme"]
