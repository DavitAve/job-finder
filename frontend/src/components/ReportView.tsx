import { useMemo, useState } from "react";
import { availableCompanies, availableStacks, filterJobs, type JobFilters as Filters } from "../lib/jobs";
import type { CrawlReport, CrawlStats, ResumeMatches } from "../types";
import { CompanyIssuesTable } from "./CompanyIssuesTable";
import { JobFilters } from "./JobFilters";
import { JobsTable } from "./JobsTable";
import { StatCards, type ReportTab } from "./StatCards";
import { TableSkeleton } from "./TableSkeleton";

const initialFilters: Filters = { title: "", stacks: [], excludedCompanies: [], location: "all", format: "all", onlyNew: false, resumeMatch: false };

interface Props {
  report: CrawlReport;
  showStats?: boolean;
  liveStats?: CrawlStats;
  isSearching?: boolean;
  newJobIds?: ReadonlySet<string>;
  resumeMatches?: ResumeMatches;
}

export function ReportView({ report, showStats = true, liveStats, isSearching = false, newJobIds, resumeMatches }: Props) {
  const [filters, setFilters] = useState(initialFilters);
  const [activeTab, setActiveTab] = useState<ReportTab>("jobs");
  const stacks = useMemo(() => availableStacks(report.jobs), [report.jobs]);
  const companies = useMemo(() => availableCompanies(report.jobs), [report.jobs]);
  const matchMap = useMemo(() => new Map(resumeMatches?.matches.map((match) => [match.job_id, match]) ?? []), [resumeMatches]);
  const jobs = useMemo(() => {
    const filtered = filterJobs(report.jobs, filters, newJobIds);
    if (!filters.resumeMatch) return filtered;
    return filtered.filter((job) => (matchMap.get(job.job_id)?.score ?? 0) >= 35).sort((a, b) => (matchMap.get(b.job_id)?.score ?? 0) - (matchMap.get(a.job_id)?.score ?? 0));
  }, [report.jobs, filters, newJobIds, matchMap]);
  const stats = liveStats ?? report.stats;
  const issueStatus = activeTab === "blocked" ? "blocked" : "failed";
  const issueCount = issueStatus === "blocked" ? stats.blocked : stats.failed;

  return (
    <div className="space-y-4">
      {showStats && <StatCards activeTab={activeTab} onTabChange={setActiveTab} stats={stats} />}
      {isSearching ? <TableSkeleton /> : activeTab === "jobs" ? (
        <>
          <JobFilters companies={companies} filters={filters} stacks={stacks} resumeAvailable={Boolean(resumeMatches?.active_resume_id)} onChange={setFilters} />
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-admin-ink">Найденные вакансии</h2>
            <span className="text-sm text-admin-muted">{jobs.length} результатов</span>
          </div>
          <JobsTable jobs={jobs} newJobIds={newJobIds} resumeMatches={resumeMatches?.active_resume_id ? matchMap : undefined} />
        </>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-admin-ink">{activeTab === "blocked" ? "Заблокированные компании" : "Компании с ошибками"}</h2>
            <span className="text-sm text-admin-muted">{issueCount} результатов</span>
          </div>
          <CompanyIssuesTable companies={report.companies ?? []} errors={report.errors} status={issueStatus} />
        </>
      )}
    </div>
  );
}
