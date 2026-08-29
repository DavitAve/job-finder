import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ExternalIcon } from "../components/Icons";
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/QueryState";
import { api, ApiError } from "../lib/api";
import { formatDate } from "../lib/format";
import type { CompanyStatus, RunSummary } from "../types";

const pageSize = 20;
const verifiedStatuses = new Set<CompanyStatus>(["success", "no_jobs"]);
const atsNames = new Set([
  "ashby",
  "bamboohr",
  "greenhouse",
  "lever",
  "pinpoint",
  "recruitee",
  "rippling",
  "smartrecruiters",
  "staff.am",
  "workable",
  "workday",
]);

const statusLabels: Partial<Record<CompanyStatus, string>> = {
  success: "Есть вакансии",
  no_jobs: "Вакансий нет",
  blocked: "Заблокировано",
  failed: "Ошибка",
  unsupported: "Не извлечено",
  unverified: "Не подтверждено",
  skipped: "Отключено",
};

interface AdapterCoverage {
  name: string;
  companies: number;
  verified: number;
  jobs: number;
  kind: "ATS" | "Парсер" | "Не определён";
}

export function CoveragePage() {
  const companiesQuery = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const latestQuery = useQuery({
    queryKey: ["latest-run"],
    queryFn: async () => {
      try {
        return await api.latest();
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    retry: false,
  });
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: api.history });
  const [staleDays, setStaleDays] = useState(7);
  const [page, setPage] = useState(1);
  const tableRef = useRef<HTMLElement>(null);

  const activeCompanies = useMemo(
    () => (companiesQuery.data ?? []).filter((company) => company.enabled),
    [companiesQuery.data],
  );
  const verified = activeCompanies.filter((company) => company.crawl_status && verifiedStatuses.has(company.crawl_status)).length;
  const successful = activeCompanies.filter((company) => company.crawl_status === "success").length;
  const knownCareers = activeCompanies.filter((company) => Boolean(company.careers_url || company.resolved_careers_url)).length;
  const careersPercent = activeCompanies.length ? Math.round((knownCareers / activeCompanies.length) * 100) : 0;
  const verifiedPercent = activeCompanies.length ? Math.round((verified / activeCompanies.length) * 100) : 0;

  const adapters = useMemo<AdapterCoverage[]>(() => {
    const groups = new Map<string, AdapterCoverage>();
    for (const company of latestQuery.data?.companies ?? []) {
      const name = company.adapter?.trim() || "Не определён";
      const normalized = name.toLocaleLowerCase();
      const group = groups.get(name) ?? {
        name,
        companies: 0,
        verified: 0,
        jobs: 0,
        kind: name === "Не определён" ? "Не определён" : normalized.split("+").some((part) => atsNames.has(part)) ? "ATS" : "Парсер",
      };
      group.companies += 1;
      group.verified += verifiedStatuses.has(company.status) ? 1 : 0;
      group.jobs += company.matching_jobs;
      groups.set(name, group);
    }
    return [...groups.values()].sort((left, right) => right.companies - left.companies || left.name.localeCompare(right.name));
  }, [latestQuery.data]);

  const trend = useMemo<RunSummary[]>(() => {
    const latest = latestQuery.data ? [{
      run_id: latestQuery.data.run_id,
      started_at: latestQuery.data.started_at,
      finished_at: latestQuery.data.finished_at,
      stats: latestQuery.data.stats,
    }] : [];
    const unique = new Map([...latest, ...(historyQuery.data ?? [])].map((run) => [run.run_id, run]));
    return [...unique.values()]
      .sort((left, right) => Date.parse(left.finished_at) - Date.parse(right.finished_at))
      .slice(-4);
  }, [historyQuery.data, latestQuery.data]);

  const staleCompanies = useMemo(() => {
    const cutoff = Date.now() - staleDays * 24 * 60 * 60 * 1000;
    return activeCompanies
      .filter((company) => !company.last_crawled_at || Date.parse(company.last_crawled_at) < cutoff)
      .sort((left, right) => {
        if (!left.last_crawled_at) return right.last_crawled_at ? -1 : left.name.localeCompare(right.name);
        if (!right.last_crawled_at) return 1;
        return Date.parse(left.last_crawled_at) - Date.parse(right.last_crawled_at);
      });
  }, [activeCompanies, staleDays]);
  const pages = Math.max(1, Math.ceil(staleCompanies.length / pageSize));
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visibleStale = staleCompanies.slice(firstVisible, firstVisible + pageSize);
  useEffect(() => setPage(1), [staleDays]);

  const loading = companiesQuery.isLoading || latestQuery.isLoading || historyQuery.isLoading;
  const error = companiesQuery.error ?? latestQuery.error ?? historyQuery.error;

  if (loading) return <PageFrame><LoadingState /></PageFrame>;
  if (error) return <PageFrame><ErrorState message={error.message} onRetry={() => {
    void companiesQuery.refetch();
    void latestQuery.refetch();
    void historyQuery.refetch();
  }} /></PageFrame>;

  return (
    <PageFrame>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-admin-ink">Покрытие</h1>
        <p className="mt-1 text-sm text-admin-muted">Качество источников, состояние обхода и проблемные зоны базы компаний</p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Основные показатели покрытия">
        <MetricCard label="Активные компании" value={activeCompanies.length} detail={`${companiesQuery.data?.length ?? 0} всего в базе`} />
        <MetricCard label="Успешно проверено" value={verified} detail={`${verifiedPercent}% · ${successful} с вакансиями`} progress={verifiedPercent} />
        <MetricCard label="Career URL известен" value={`${careersPercent}%`} detail={`${knownCareers} из ${activeCompanies.length} компаний`} progress={careersPercent} />
        <MetricCard label="Требуют внимания" value={staleCompanies.length} detail={`Не проверялись более ${staleDays} дн. или никогда`} tone={staleCompanies.length ? "warning" : "success"} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <TrendPanel runs={trend} />
        <AdapterPanel adapters={adapters} />
      </section>

      <section ref={tableRef} className="scroll-mt-4 overflow-hidden rounded-xl border border-admin-border bg-white">
        <div className="flex flex-col gap-3 border-b border-admin-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold text-admin-ink">Давно не проверялись</h2>
            <p className="mt-0.5 text-sm text-admin-muted">Включая компании, которые ещё ни разу не обрабатывались</p>
          </div>
          <label className="flex items-center gap-2 text-sm text-admin-muted">
            Старше
            <select
              className="h-9 rounded-lg border border-admin-border bg-white px-3 text-admin-ink outline-none focus:border-admin-primary"
              value={staleDays}
              onChange={(event) => setStaleDays(Number(event.target.value))}
            >
              <option value={1}>1 дня</option>
              <option value={7}>7 дней</option>
              <option value={30}>30 дней</option>
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-sm" aria-label="Компании, давно не проверявшиеся">
            <thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase text-admin-muted">
              <tr><th className="px-4 py-3">Компания</th><th className="px-4 py-3">Статус</th><th className="px-4 py-3">Последняя проверка</th><th className="px-4 py-3">Career URL</th><th className="px-4 py-3">Сайт</th></tr>
            </thead>
            <tbody className="divide-y divide-admin-border">
              {visibleStale.map((company) => (
                <tr key={company.id} className="hover:bg-admin-soft/70">
                  <td className="px-4 py-3 font-medium text-admin-ink">{company.name}</td>
                  <td className="px-4 py-3 text-admin-muted">{company.crawl_status ? statusLabels[company.crawl_status] : "Не проверялась"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-admin-muted">{formatDate(company.last_crawled_at)}</td>
                  <td className="px-4 py-3">{company.careers_url ? <ExternalLink href={company.careers_url} label="Открыть Careers" /> : <span className="text-amber-700">Не найден</span>}</td>
                  <td className="px-4 py-3"><ExternalLink href={company.website_url} label="Открыть сайт" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!visibleStale.length ? (
          <div className="px-4 py-12 text-center text-sm text-admin-muted">Все активные компании проверялись в выбранный период</div>
        ) : (
          <footer className="flex flex-col gap-3 border-t border-admin-border px-4 py-3 text-sm text-admin-muted sm:flex-row sm:items-center sm:justify-between">
            <span>Показано {firstVisible + 1}–{firstVisible + visibleStale.length} из {staleCompanies.length}</span>
            <Pagination page={currentPage} pages={pages} onChange={setPage} scrollTarget={tableRef} />
          </footer>
        )}
      </section>
    </PageFrame>
  );
}

function PageFrame({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full min-w-0 max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">{children}</div>;
}

function MetricCard({ label, value, detail, progress, tone = "default" }: { label: string; value: number | string; detail: string; progress?: number; tone?: "default" | "warning" | "success" }) {
  const valueClass = tone === "warning" ? "text-amber-700" : tone === "success" ? "text-emerald-700" : "text-admin-ink";
  return (
    <div className="rounded-xl border border-admin-border bg-white p-4">
      <p className="text-sm text-admin-muted">{label}</p>
      <strong className={`mt-1 block text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</strong>
      <p className="mt-1 text-xs text-admin-muted">{detail}</p>
      {progress !== undefined && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-admin-primary/10"><div className="h-full rounded-full bg-admin-primary" style={{ width: `${progress}%` }} /></div>}
    </div>
  );
}

const trendStatuses = [
  { key: "success", label: "С вакансиями", color: "bg-emerald-500" },
  { key: "blocked", label: "Заблокировано", color: "bg-amber-500" },
  { key: "failed", label: "Ошибки", color: "bg-red-500" },
  { key: "unverified", label: "Не подтверждено", color: "bg-slate-400" },
] as const;

function TrendPanel({ runs }: { runs: RunSummary[] }) {
  return (
    <section className="rounded-xl border border-admin-border bg-white p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div><h2 className="font-semibold text-admin-ink">Динамика статусов</h2><p className="mt-0.5 text-sm text-admin-muted">Текущий и три предыдущих завершённых поиска</p></div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-admin-muted">{trendStatuses.map((status) => <span key={status.key} className="inline-flex items-center gap-1.5"><span className={`size-2 rounded-full ${status.color}`} />{status.label}</span>)}</div>
      </div>
      <div className="mt-6 space-y-5">
        {runs.map((run) => <TrendRow key={run.run_id} run={run} />)}
        {!runs.length && <p className="py-8 text-center text-sm text-admin-muted">Истории поисков пока нет</p>}
      </div>
    </section>
  );
}

function TrendRow({ run }: { run: RunSummary }) {
  const total = Math.max(1, run.stats.total_companies);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-4 text-xs"><span className="text-admin-muted">{formatDate(run.finished_at)}</span><span className="font-medium tabular-nums text-admin-ink">{run.stats.total_companies} компаний</span></div>
      <div className="flex h-3 overflow-hidden rounded-full bg-admin-soft" aria-label={`Статусы запуска ${run.run_id}`}>
        {trendStatuses.map((status) => <div key={status.key} className={status.color} style={{ width: `${((run.stats[status.key] ?? 0) / total) * 100}%` }} title={`${status.label}: ${run.stats[status.key] ?? 0}`} />)}
      </div>
      <div className="mt-2 grid grid-cols-4 gap-2 text-xs tabular-nums text-admin-muted">{trendStatuses.map((status) => <span key={status.key}>{run.stats[status.key] ?? 0}</span>)}</div>
    </div>
  );
}

function AdapterPanel({ adapters }: { adapters: AdapterCoverage[] }) {
  return (
    <section className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <div className="border-b border-admin-border px-5 py-4"><h2 className="font-semibold text-admin-ink">ATS и способы обработки</h2><p className="mt-0.5 text-sm text-admin-muted">По последнему сохранённому состоянию</p></div>
      <div className="max-h-[390px] overflow-auto">
        <table className="w-full min-w-[520px] text-left text-sm" aria-label="ATS и способы обработки">
          <thead className="sticky top-0 bg-admin-soft text-xs uppercase text-admin-muted"><tr><th className="px-4 py-3">Источник</th><th className="px-4 py-3">Компании</th><th className="px-4 py-3">Проверено</th><th className="px-4 py-3">Вакансии</th></tr></thead>
          <tbody className="divide-y divide-admin-border">{adapters.map((adapter) => (
            <tr key={adapter.name}>
              <td className="px-4 py-3"><span className="font-medium text-admin-ink">{formatAdapterName(adapter.name)}</span><span className="ml-2 rounded bg-admin-soft px-1.5 py-0.5 text-[10px] uppercase text-admin-muted">{adapter.kind}</span></td>
              <td className="px-4 py-3 tabular-nums">{adapter.companies}</td>
              <td className="px-4 py-3 tabular-nums text-admin-muted">{adapter.verified} ({Math.round((adapter.verified / adapter.companies) * 100)}%)</td>
              <td className="px-4 py-3 tabular-nums">{adapter.jobs}</td>
            </tr>
          ))}</tbody>
        </table>
        {!adapters.length && <p className="px-4 py-12 text-center text-sm text-admin-muted">Источники ещё не определены</p>}
      </div>
    </section>
  );
}

function formatAdapterName(value: string) {
  if (value === "Не определён") return value;
  const labels: Record<string, string> = { html: "HTML", jsonld: "JSON-LD", "staff.am": "Staff.am" };
  return value.split("+").map((part) => labels[part] ?? part.charAt(0).toUpperCase() + part.slice(1)).join(" + ");
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return <a className="inline-flex items-center gap-1 text-admin-primary hover:underline" href={href} target="_blank" rel="noreferrer"><ExternalIcon className="size-4" />{label}</a>;
}
