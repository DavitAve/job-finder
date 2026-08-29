from datetime import datetime, timezone

from job_finder.models import Company, CompanyCrawlResult, CompanyStatus, CrawlReport, CrawlStats, Job
from job_finder.partial import merge_partial_report


MOMENT = datetime(2026, 8, 1, tzinfo=timezone.utc)


def job(job_id: str, company: str) -> Job:
    return Job(job_id=job_id, company=company, title="Frontend Developer", url=f"https://example.com/{job_id}", source="test", found_at=MOMENT)


def result(company_id: str, company: str, status: CompanyStatus, jobs: int) -> CompanyCrawlResult:
    return CompanyCrawlResult(company_id=company_id, company=company, status=status, matching_jobs=jobs)


def report(run_id: str, companies, jobs) -> CrawlReport:
    return CrawlReport(run_id=run_id, started_at=MOMENT, finished_at=MOMENT, stats=CrawlStats(total_companies=len(companies), jobs_found=len(jobs)), companies=companies, errors=[], jobs=jobs)


def test_partial_report_replaces_selected_company_and_preserves_others() -> None:
    configured = [
        Company(id="acme", name="Acme", website_url="https://acme.example"),
        Company(id="other", name="Other", website_url="https://other.example"),
    ]
    previous = report("old", [result("acme", "Acme", CompanyStatus.SUCCESS, 1), result("other", "Other", CompanyStatus.SUCCESS, 1)], [job("old-acme", "Acme"), job("other", "Other")])
    partial = report("new", [result("acme", "Acme", CompanyStatus.NO_JOBS, 0)], [])

    merged = merge_partial_report(previous, partial, configured, {"acme"}, "selected")

    assert merged.scope == "selected"
    assert merged.processed_company_ids == ["acme"]
    assert [item.job_id for item in merged.jobs] == ["other"]
    assert {item.company_id: item.status for item in merged.companies} == {
        "acme": CompanyStatus.NO_JOBS,
        "other": CompanyStatus.SUCCESS,
    }
    assert merged.stats.total_companies == 2
    assert merged.stats.jobs_found == 1


def test_partial_report_preserves_unsupported_and_unverified_counts() -> None:
    configured = [
        Company(id="parser", name="Parser", website_url="https://parser.example"),
        Company(id="missing", name="Missing", website_url="https://missing.example"),
    ]
    previous = report(
        "old",
        [
            result("parser", "Parser", CompanyStatus.UNSUPPORTED, 0),
            result("missing", "Missing", CompanyStatus.SUCCESS, 1),
        ],
        [job("old-missing", "Missing")],
    )
    partial = report("new", [result("missing", "Missing", CompanyStatus.UNVERIFIED, 0)], [])

    merged = merge_partial_report(
        previous,
        partial,
        configured,
        {"missing"},
        "selected",
    )

    assert merged.stats.unsupported == 1
    assert merged.stats.unverified == 1
