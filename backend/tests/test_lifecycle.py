from datetime import datetime, timezone

from job_finder.lifecycle import apply_job_lifecycle
from job_finder.models import CrawlReport, CrawlStats, Job


def make_job(job_id: str, company: str, found_at: datetime) -> Job:
    return Job(
        job_id=job_id,
        company=company,
        title="Frontend Developer",
        url=f"https://example.com/{job_id}",
        source="test",
        found_at=found_at,
    )


def make_report(run_id: str, moment: datetime, jobs: list[Job]) -> CrawlReport:
    return CrawlReport(
        run_id=run_id,
        started_at=moment,
        finished_at=moment,
        stats=CrawlStats(total_companies=2, jobs_found=len(jobs)),
        companies=[],
        errors=[],
        jobs=jobs,
    )


def test_lifecycle_preserves_first_seen_and_updates_only_processed_companies() -> None:
    first = datetime(2026, 8, 1, tzinfo=timezone.utc)
    second = datetime(2026, 8, 2, tzinfo=timezone.utc)
    old = make_report("old", first, [make_job("same", "Acme", first), make_job("untouched", "Other", first)])
    current = make_report("new", second, [make_job("same", "Acme", second), make_job("untouched", "Other", first), make_job("fresh", "Acme", second)])

    result = apply_job_lifecycle(current, old, {"Acme"})
    by_id = {job.job_id: job for job in result.jobs}

    assert by_id["same"].lifecycle == "active"
    assert by_id["same"].first_seen_at == first
    assert by_id["same"].last_seen_at == second
    assert by_id["untouched"].last_seen_at == first
    assert by_id["fresh"].lifecycle == "new"
    assert by_id["fresh"].first_seen_at == second
