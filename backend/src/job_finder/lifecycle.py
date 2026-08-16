from __future__ import annotations

from job_finder.models import CrawlReport, JobLifecycle


def apply_job_lifecycle(
    report: CrawlReport,
    previous: CrawlReport | None,
    processed_company_names: set[str],
) -> CrawlReport:
    previous_jobs = {job.job_id: job for job in (previous.jobs if previous else [])}
    jobs = []
    for job in report.jobs:
        old = previous_jobs.get(job.job_id)
        if old is None:
            jobs.append(
                job.model_copy(
                    update={
                        "first_seen_at": job.first_seen_at or job.found_at,
                        "last_seen_at": report.finished_at,
                        "lifecycle": JobLifecycle.NEW,
                    }
                )
            )
            continue
        jobs.append(
            job.model_copy(
                update={
                    "first_seen_at": old.first_seen_at or old.found_at,
                    "last_seen_at": (
                        report.finished_at
                        if job.company in processed_company_names
                        else old.last_seen_at or old.found_at
                    ),
                    "lifecycle": JobLifecycle.ACTIVE,
                }
            )
        )
    return report.model_copy(update={"jobs": jobs})
