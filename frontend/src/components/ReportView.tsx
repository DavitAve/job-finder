import { useEffect, useMemo, useState } from "react";
import { availableCompanies, availableStacks, filterJobs, type JobFilters as Filters } from "../lib/jobs";
import { classifyIssue, collectIssues, problemCompanyIds, type ErrorCategory, type IssueStatus } from "../lib/issues";
import type { CrawlReport, CrawlStats, ResumeMatches } from "../types";
import { CompanyIssuesTable } from "./CompanyIssuesTable";
import { ErrorAnalysis } from "./ErrorAnalysis";
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
  onRetryProblems?: (companyIds: string[]) => void;
  isRetryingProblems?: boolean;
}

const blockedStatuses: readonly IssueStatus[] = ["blocked"];
const failedStatuses: readonly IssueStatus[] = ["failed"];
const noJobStatuses: readonly IssueStatus[] = ["no_jobs"];
const unsupportedStatuses: readonly IssueStatus[] = ["unsupported"];
const unverifiedStatuses: readonly IssueStatus[] = ["unverified"];

export function ReportView({ report, showStats = true, liveStats, isSearching = false, newJobIds, resumeMatches, onRetryProblems, isRetryingProblems = false }: Props) {
  const [filters, setFilters] = useState(initialFilters);
  const [activeTab, setActiveTab] = useState<ReportTab>("jobs");
  const [errorCategory, setErrorCategory] = useState<ErrorCategory | "all">("all");
  const stacks = useMemo(() => availableStacks(report.jobs), [report.jobs]);
  const companies = useMemo(() => availableCompanies(report.jobs), [report.jobs]);
  const matchMap = useMemo(() => new Map(resumeMatches?.matches.map((match) => [match.job_id, match]) ?? []), [resumeMatches]);
  const jobs = useMemo(() => {
    const filtered = filterJobs(report.jobs, filters, newJobIds);
    if (!filters.resumeMatch) return filtered;
    return filtered.filter((job) => (matchMap.get(job.job_id)?.score ?? 0) >= 35).sort((a, b) => (matchMap.get(b.job_id)?.score ?? 0) - (matchMap.get(a.job_id)?.score ?? 0));
  }, [report.jobs, filters, newJobIds, matchMap]);
  const stats = liveStats ?? report.stats;
  const inferredUnverified = useMemo(
    () => collectIssues(report.companies ?? [], report.errors, unverifiedStatuses)
      .filter((issue) => issue.status === "unverified").length,
    [report.companies, report.errors],
  );
  const displayedStats = inferredUnverified > (stats.unverified ?? 0)
    ? { ...stats, unverified: inferredUnverified }
    : stats;
  const issueStatuses = activeTab === "blocked"
    ? blockedStatuses
    : activeTab === "no_jobs"
      ? noJobStatuses
      : activeTab === "unsupported"
        ? unsupportedStatuses
        : activeTab === "unverified"
          ? unverifiedStatuses
          : failedStatuses;
  const issues = useMemo(
    () => collectIssues(report.companies ?? [], report.errors, issueStatuses),
    [issueStatuses, report.companies, report.errors],
  );
  const filteredIssueCount = useMemo(
    () => activeTab === "no_jobs" || errorCategory === "all" ? issues.length : issues.filter(
      (issue) => classifyIssue(issue, report.errors) === errorCategory,
    ).length,
    [activeTab, errorCategory, issues, report.errors],
  );
  const retryCompanyIds = useMemo(() => problemCompanyIds(report), [report]);

  useEffect(() => setErrorCategory("all"), [activeTab]);

  return (
    <div className="min-w-0 space-y-4">
      {showStats && <StatCards activeTab={activeTab} onTabChange={setActiveTab} stats={displayedStats} />}
      {isSearching ? <TableSkeleton /> : activeTab === "jobs" ? (
        <>
          <JobFilters companies={companies} filters={filters} stacks={stacks} resumeAvailable={Boolean(resumeMatches?.active_resume_id)} onChange={setFilters} />
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-admin-ink">Найденные вакансии</h2>
            <span className="text-sm text-admin-muted">{jobs.length} результатов</span>
          </div>
          <JobsTable jobs={jobs} newJobIds={newJobIds} resumeMatches={resumeMatches?.active_resume_id ? matchMap : undefined} />
        </>
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-semibold text-admin-ink">
              {activeTab === "blocked"
                ? "Заблокированные компании"
                : activeTab === "no_jobs"
                  ? "Карьерная страница найдена — вакансий нет"
                  : activeTab === "unsupported"
                    ? "Вакансии видны, но не извлечены"
                    : activeTab === "unverified"
                      ? "Карьерная страница не найдена или не проверена"
                      : "Компании с ошибками"}
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-admin-muted">{filteredIssueCount} результатов</span>
              {onRetryProblems && activeTab !== "no_jobs" && (
                <button
                  className="rounded-lg bg-admin-primary px-3 py-2 text-sm font-semibold text-white transition hover:bg-admin-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isRetryingProblems || retryCompanyIds.length === 0}
                  onClick={() => onRetryProblems(retryCompanyIds)}
                  type="button"
                >
                  {isRetryingProblems ? "Запускаем…" : `Повторить проблемные (${retryCompanyIds.length})`}
                </button>
              )}
            </div>
          </div>
          {activeTab !== "no_jobs" && (
            <ErrorAnalysis errors={report.errors} issues={issues} onChange={setErrorCategory} selected={errorCategory} />
          )}
          <CompanyIssuesTable category={activeTab === "no_jobs" ? "all" : errorCategory} companies={report.companies ?? []} errors={report.errors} status={issueStatuses} />
        </>
      )}
    </div>
  );
}
