import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/QueryState";
import { ReportView } from "../components/ReportView";
import { api } from "../lib/api";
import { formatDate, formatDuration } from "../lib/format";

export function HistoryPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const history = useQuery({ queryKey: ["history"], queryFn: api.history });
  useEffect(() => {
    if (!runId && history.data?.[0])
      navigate(`/history/${history.data[0].run_id}`, { replace: true });
  }, [history.data, navigate, runId]);
  const report = useQuery({
    queryKey: ["history-report", runId],
    queryFn: () => api.report(runId!),
    enabled: Boolean(runId),
  });
  const resumeMatches = useQuery({
    queryKey: ["resume-matches", runId],
    queryFn: () => api.resumeMatches(runId),
    enabled: Boolean(runId),
  });
  return (
    <div className="mx-auto w-full min-w-0 max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-admin-ink">
          История поиска
        </h1>
        <p className="mt-1 text-sm text-admin-muted">
          Три последних завершённых поиска
        </p>
      </header>
      {history.isLoading ? (
        <LoadingState />
      ) : history.isError ? (
        <ErrorState
          message={history.error.message}
          onRetry={() => void history.refetch()}
        />
      ) : !history.data?.length ? (
        <div className="rounded-xl border border-dashed border-admin-border bg-white p-12 text-center text-admin-muted">
          История пока пуста
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-3">
          {history.data.slice(0, 3).map((run, index) => (
            <Link
              className={`rounded-xl border p-4 transition ${run.run_id === runId ? "border-admin-primary bg-admin-primary/5" : "border-admin-border bg-white hover:border-admin-primary/40"}`}
              to={`/history/${run.run_id}`}
              key={run.run_id}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-admin-primary">
                  Поиск {Math.min(history.data.length, 3) - index}
                </span>
                <span className="text-xs text-admin-muted">
                  {formatDuration(run.started_at, run.finished_at)}
                </span>
              </div>
              <div className="mt-2 font-medium text-admin-ink">
                {formatDate(run.finished_at)}
              </div>
              <div className="mt-2 text-sm font-medium text-admin-ink">
                {run.stats.jobs_found} вакансий
              </div>
              <div className="mt-1 text-xs text-admin-muted">
                Успешно: {run.stats.success} · Не извлечено:{" "}
                {run.stats.unsupported ?? 0} · Не проверено:{" "}
                {run.stats.unverified ?? 0} · Заблокировано:{" "}
                {run.stats.blocked} · Ошибки: {run.stats.failed}
              </div>
            </Link>
          ))}
        </div>
      )}
      {runId &&
        (report.isLoading ? (
          <LoadingState />
        ) : report.isError ? (
          <ErrorState
            message={report.error.message}
            onRetry={() => void report.refetch()}
          />
        ) : report.data ? (
          <ReportView report={report.data} resumeMatches={resumeMatches.data} />
        ) : null)}
    </div>
  );
}
