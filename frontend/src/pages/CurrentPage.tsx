import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CompaniesIcon, RefreshIcon } from "../components/Icons";
import { JobsTable } from "../components/JobsTable";
import { ErrorState, LoadingState } from "../components/QueryState";
import { ReportView } from "../components/ReportView";
import { useCrawler } from "../hooks/useCrawler";
import { api, ApiError } from "../lib/api";
import { formatDate, formatTimer } from "../lib/format";
import type { CrawlReport, CrawlStats } from "../types";

const emptyStats: CrawlStats = {
  total_companies: 0,
  success: 0,
  no_jobs: 0,
  blocked: 0,
  failed: 0,
  skipped: 0,
  jobs_found: 0,
  duplicates_removed: 0,
};

export function CurrentPage() {
  const latest = useQuery({ queryKey: ["latest-run"], queryFn: api.latest });
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const changes = useQuery({ queryKey: ["job-changes"], queryFn: api.jobChanges, enabled: Boolean(latest.data) });
  const resumeMatches = useQuery({ queryKey: ["resume-matches", latest.data?.run_id], queryFn: () => api.resumeMatches(latest.data?.run_id), enabled: Boolean(latest.data) });
  const { active, start, isRunning } = useCrawler();
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!isRunning) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [isRunning, active.data?.run_id]);

  const newJobIds = useMemo(
    () => new Set(changes.data?.new_jobs.map((job) => job.job_id) ?? []),
    [changes.data],
  );
  const progress = active.data && active.data.total > 0
    ? Math.round(active.data.processed / active.data.total * 100)
    : 0;
  const liveStats: CrawlStats = isRunning ? {
    total_companies: active.data?.total ?? 0,
    success: active.data?.success ?? 0,
    no_jobs: active.data?.no_jobs ?? 0,
    blocked: active.data?.blocked ?? 0,
    failed: active.data?.failed ?? 0,
    skipped: active.data?.skipped ?? 0,
    jobs_found: active.data?.jobs_found ?? 0,
    duplicates_removed: 0,
  } : latest.data?.stats ?? emptyStats;
  const fallbackReport: CrawlReport = latest.data ?? {
    schema_version: "2.0",
    run_id: active.data?.run_id ?? "pending",
    started_at: active.data?.started_at ?? new Date(now).toISOString(),
    finished_at: active.data?.finished_at ?? new Date(now).toISOString(),
    stats: liveStats,
    companies: [],
    errors: [],
    jobs: [],
  };
  const runningStart = active.data?.started_at ? Date.parse(active.data.started_at) : Number.NaN;
  const completedStart = latest.data ? Date.parse(latest.data.started_at) : Number.NaN;
  const completedEnd = latest.data ? Date.parse(latest.data.finished_at) : Number.NaN;
  const elapsedMilliseconds = isRunning
    ? (Number.isFinite(runningStart) ? now - runningStart : 0)
    : (Number.isFinite(completedStart) && Number.isFinite(completedEnd) ? completedEnd - completedStart : null);

  return (
    <div className="mx-auto max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-admin-ink">Frontend вакансии</h1>
          <p className="mt-1 text-sm text-admin-muted">
            {latest.data ? `Последний поиск: ${formatDate(latest.data.finished_at)}` : "Запустите первый поиск вакансий"}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {elapsedMilliseconds !== null && (
            <div className="mr-1 text-right" aria-live={isRunning ? "polite" : "off"}>
              <div className="text-xs text-admin-muted">{isRunning ? "Идёт поиск" : "Последний поиск"}</div>
              <div className="font-mono text-sm font-semibold tabular-nums text-admin-ink">{formatTimer(elapsedMilliseconds)}</div>
            </div>
          )}
          <button
            className="h-10 rounded-lg border border-admin-primary px-3 text-sm font-semibold text-admin-primary transition hover:bg-admin-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isRunning}
            onClick={() => start.mutate({ scope: "new" })}
          >
            Искать только новые
          </button>
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white transition hover:bg-admin-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isRunning}
            onClick={() => start.mutate({ scope: "full" })}
          >
            <RefreshIcon className={`size-4 ${isRunning ? "animate-spin" : ""}`} />
            {isRunning ? "Идёт поиск…" : "Найти вакансии"}
          </button>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Link className="group flex items-center gap-4 rounded-xl border border-admin-border bg-white p-4 transition hover:border-admin-primary/50 hover:shadow-sm" to="/companies" aria-label="Открыть список компаний">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-admin-primary/10 text-admin-primary"><CompaniesIcon className="size-6" /></span>
          <span className="min-w-0 flex-1"><span className="block text-sm text-admin-muted">Компании в базе</span><span className="block text-2xl font-semibold tabular-nums text-admin-ink">{companies.isLoading ? "…" : companies.data?.length ?? "—"}</span></span>
          <span className="text-xl text-admin-primary transition group-hover:translate-x-1" aria-hidden>→</span>
        </Link>
        <div className="rounded-xl border border-admin-border bg-white p-4"><span className="text-sm text-admin-muted">Новые вакансии</span><strong className="mt-1 block text-2xl tabular-nums text-emerald-700">{changes.isLoading ? "…" : changes.data?.new_jobs.length ?? 0}</strong></div>
        <div className="rounded-xl border border-admin-border bg-white p-4"><span className="text-sm text-admin-muted">Закрытые вакансии</span><strong className="mt-1 block text-2xl tabular-nums text-admin-primary">{changes.isLoading ? "…" : changes.data?.closed_jobs.length ?? 0}</strong></div>
      </div>

      {isRunning && (
        <section className="rounded-xl border border-admin-primary/20 bg-white p-4" aria-live="polite">
          <div className="flex justify-between text-sm"><span className="font-medium text-admin-ink">Обрабатываем компании</span><span className="text-admin-muted">{active.data?.processed ?? 0} из {active.data?.total ?? 0} · {active.data?.jobs_found ?? 0} вакансий</span></div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-admin-primary/10"><div className="h-full rounded-full bg-admin-primary transition-all" style={{ width: `${progress}%` }} /></div>
        </section>
      )}
      {start.isError && <ErrorState message={start.error.message} />}
      {active.data?.state === "failed" && <ErrorState message={active.data.error ?? "Поиск завершился с ошибкой. Предыдущие результаты сохранены."} />}
      {active.isError && <ErrorState message={active.error.message} />}

      {isRunning ? (
        <ReportView isSearching liveStats={liveStats} report={fallbackReport} />
      ) : latest.isLoading ? (
        <LoadingState />
      ) : (
        <>
          {latest.isError && latest.data && <ErrorState message={`Не удалось обновить данные: ${latest.error.message}. Показан предыдущий результат.`} onRetry={() => void latest.refetch()} />}
          {latest.data ? (
            <ReportView report={latest.data} newJobIds={newJobIds} resumeMatches={resumeMatches.data} />
          ) : latest.isError && latest.error instanceof ApiError && latest.error.status === 404 ? (
            <div className="rounded-xl border border-dashed border-admin-border bg-white px-6 py-14 text-center"><p className="font-medium text-admin-ink">Поисков пока нет</p><p className="mt-1 text-sm text-admin-muted">Нажмите «Найти вакансии», чтобы получить первый результат.</p></div>
          ) : latest.isError ? (
            <ErrorState message={latest.error.message} onRetry={() => void latest.refetch()} />
          ) : null}
        </>
      )}

      {!isRunning && changes.data && changes.data.closed_jobs.length > 0 && (
        <details className="rounded-xl border border-admin-border bg-white">
          <summary className="cursor-pointer list-none px-5 py-4 font-semibold text-admin-ink">Закрытые после последнего поиска ({changes.data.closed_jobs.length})</summary>
          <div className="border-t border-admin-border p-4"><JobsTable jobs={changes.data.closed_jobs} /></div>
        </details>
      )}
    </div>
  );
}
