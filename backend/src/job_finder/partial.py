from __future__ import annotations

from job_finder.models import (
    Company,
    CompanyStatus,
    CrawlError,
    CrawlReport,
    CrawlStats,
)


def merge_partial_report(
    previous: CrawlReport | None,
    partial: CrawlReport,
    all_companies: list[Company],
    selected_company_ids: set[str],
    scope: str,
) -> CrawlReport:
    if previous is None:
        return partial.model_copy(
            update={
                "scope": scope,
                "processed_company_ids": sorted(selected_company_ids),
                "stats": partial.stats.model_copy(
                    update={"total_companies": len(all_companies)}
                ),
            }
        )
    configured_ids = {company.id for company in all_companies}
    selected_names = {
        company.name for company in all_companies if company.id in selected_company_ids
    }
    results_by_id = {
        result.company_id: result
        for result in previous.companies
        if result.company_id in configured_ids and result.company_id not in selected_company_ids
    }
    results_by_id.update({result.company_id: result for result in partial.companies})
    order = {company.id: index for index, company in enumerate(all_companies)}
    results = sorted(
        results_by_id.values(), key=lambda result: order.get(result.company_id, len(order))
    )

    jobs = {
        job.job_id: job
        for job in previous.jobs
        if job.company not in selected_names
    }
    jobs.update({job.job_id: job for job in partial.jobs})
    merged_jobs = sorted(
        jobs.values(), key=lambda job: (job.company.casefold(), job.title.casefold())
    )
    errors_by_id: dict[str, CrawlError] = {
        error.company_id: error
        for error in previous.errors
        if error.company_id in configured_ids and error.company_id not in selected_company_ids
    }
    errors_by_id.update({error.company_id: error for error in partial.errors})
    counts = {
        status: sum(result.status == status for result in results)
        for status in CompanyStatus
    }
    stats = CrawlStats(
        total_companies=len(all_companies),
        success=counts[CompanyStatus.SUCCESS],
        no_jobs=counts[CompanyStatus.NO_JOBS],
        unsupported=counts[CompanyStatus.UNSUPPORTED],
        blocked=counts[CompanyStatus.BLOCKED],
        failed=counts[CompanyStatus.FAILED],
        unverified=counts[CompanyStatus.UNVERIFIED],
        skipped=counts[CompanyStatus.SKIPPED],
        jobs_found=len(merged_jobs),
        duplicates_removed=partial.stats.duplicates_removed,
    )
    return partial.model_copy(
        update={
            "scope": scope,
            "processed_company_ids": sorted(selected_company_ids),
            "stats": stats,
            "companies": results,
            "errors": list(errors_by_id.values()),
            "jobs": merged_jobs,
        }
    )
