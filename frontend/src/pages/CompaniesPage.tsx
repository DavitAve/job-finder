import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ExternalIcon, RefreshIcon } from "../components/Icons";
import { Modal } from "../components/Modal";
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/QueryState";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { buildSourceRecommendations } from "../lib/sourceRecommendations";
import type { RecommendationAction } from "../lib/sourceRecommendations";
import type { ActiveRun, CompanyCrawlResult, CompanyDiagnostics, CompanyHistoryItem, CompanyStatus, CompanySummary } from "../types";

const pageSize = 20;
type StatusFilter = "all" | CompanyStatus | "unprocessed" | "discovery" | "refresh_due";
type RetryPhase = "starting" | "running" | "refreshing" | "completed" | "failed";

interface SourceSnapshot {
  status: CompanyStatus | null;
  jobs: number;
  adapter: string | null;
  careersUrl: string | null;
  result: CompanyCrawlResult | null;
}

interface SourceRetryState {
  companyId: string;
  runId: string | null;
  phase: RetryPhase;
  before: SourceSnapshot;
  after?: SourceSnapshot;
  error?: string;
}

const statusLabel: Record<CompanyStatus, string> = {
  success: "Есть вакансии",
  no_jobs: "Нет вакансий",
  unsupported: "Вакансии не извлечены",
  blocked: "Заблокировано",
  failed: "Ошибка",
  unverified: "Не проверено",
  skipped: "Отключена",
};

function sourceSnapshot(company: CompanySummary, result: CompanyCrawlResult | null): SourceSnapshot {
  return {
    status: result?.status ?? company.crawl_status,
    jobs: result?.matching_jobs ?? company.jobs_found,
    adapter: result?.adapter ?? company.last_adapter,
    careersUrl: result?.resolved_careers_url ?? company.careers_url,
    result,
  };
}
const control =
  "h-10 rounded-lg border border-admin-border bg-white px-3 text-sm text-admin-ink outline-none transition focus:border-admin-primary focus:ring-2 focus:ring-admin-primary/15";

export function CompaniesPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const fileInput = useRef<HTMLInputElement>(null);
  const tableRef = useRef<HTMLElement>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [resetExisting, setResetExisting] = useState(false);
  const [deduplicate, setDeduplicate] = useState(true);
  const [editCompany, setEditCompany] = useState<CompanySummary | null>(null);
  const [sourceCompany, setSourceCompany] = useState<CompanySummary | null>(null);
  const [sourceRetry, setSourceRetry] = useState<SourceRetryState | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const companies = useMemo(() => {
    const value = search.trim().toLocaleLowerCase();
    return (query.data ?? []).filter((company) => {
      if (value && !company.name.toLocaleLowerCase().includes(value))
        return false;
      if (statusFilter === "unprocessed") return company.crawl_status === null;
      if (statusFilter === "discovery") return company.discovery_pending;
      if (statusFilter === "refresh_due") return company.refresh_due;
      return statusFilter === "all" || company.crawl_status === statusFilter;
    });
  }, [query.data, search, statusFilter]);
  const pages = Math.max(1, Math.ceil(companies.length / pageSize));
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visible = companies.slice(firstVisible, firstVisible + pageSize);
  const visibleIds = visible.map((company) => company.id);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  const preview = useQuery({
    queryKey: [
      "company-import-preview",
      selectedFile?.name,
      selectedFile?.size,
      resetExisting,
      deduplicate,
    ],
    queryFn: () =>
      api.previewCompanies(selectedFile!, { resetExisting, deduplicate }),
    enabled: Boolean(selectedFile),
    retry: false,
  });
  const diagnostics = useQuery({
    queryKey: ["company-diagnostics", sourceCompany?.id],
    queryFn: () => api.companyDiagnostics(sourceCompany!.id),
    enabled: Boolean(sourceCompany),
    retry: false,
  });
  const companyHistory = useQuery({
    queryKey: ["company-history", sourceCompany?.id],
    queryFn: () => api.companyHistory(sourceCompany!.id),
    enabled: Boolean(sourceCompany),
    retry: false,
  });
  const sourceRun = useQuery({
    queryKey: ["active-run"],
    queryFn: api.active,
    enabled: sourceRetry?.phase === "running",
    refetchInterval: (query) => query.state.data?.state === "running" || query.state.data?.state === "queued" ? 2_000 : false,
  });
  const importMutation = useMutation({
    mutationFn: () =>
      api.importCompanies(selectedFile!, { resetExisting, deduplicate }),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["companies"] });
      setMessage(
        `Добавлено: ${result.added}. Пропущено дубликатов: ${result.duplicates_skipped}. Всего компаний: ${result.total}.`,
      );
      closeImport();
    },
  });
  const bulkMutation = useMutation({
    mutationFn: ({
      action,
      ids,
    }: {
      action: "enable" | "disable" | "delete";
      ids: string[];
    }) => api.bulkCompanies(ids, action),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["companies"] });
      setSelectedIds(new Set());
      setMessage(
        `Изменено компаний: ${result.changed}. Всего компаний: ${result.total}.`,
      );
    },
  });
  const editMutation = useMutation({
    mutationFn: ({
      id,
      values,
    }: {
      id: string;
      values: Record<string, unknown>;
    }) => api.updateCompany(id, values),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["companies"] });
      setEditCompany(null);
      setSourceCompany(null);
      setMessage("Данные компании обновлены.");
    },
  });
  const decisionMutation = useMutation({
    mutationFn: ({
      company,
      decision,
    }: {
      company: CompanySummary;
      decision: "approve" | "reject";
    }) =>
      api.decideCareers(company.id, decision, company.resolved_careers_url!),
    onSuccess: (_, variables) => {
      void client.invalidateQueries({ queryKey: ["companies"] });
      setSourceCompany(null);
      setMessage(
        variables.decision === "approve"
          ? "Career URL сохранён."
          : "Career URL отклонён.",
      );
    },
  });
  const selectedCrawl = useMutation({
    mutationFn: (ids: string[]) =>
      api.start({ scope: "selected", company_ids: ids }),
    onSuccess: (result) =>
      {
        setMessage(`Поиск запущен для ${result.total} выбранных компаний.`);
      },
  });
  const singleCrawl = useMutation({
    mutationFn: (companyId: string) => api.start({ scope: "selected", company_ids: [companyId] }),
    onSuccess: (status, companyId) => {
      setSourceRetry((current) => current && current.companyId === companyId ? {
        ...current,
        runId: status.run_id,
        phase: "running",
      } : current);
      client.setQueryData(["active-run"], status);
    },
    onError: (error, companyId) => setSourceRetry((current) => current && current.companyId === companyId ? { ...current, phase: "failed", error: error.message } : current),
  });
  const recommendationMutation = useMutation({
    mutationFn: async ({ company, action }: { company: CompanySummary; action: Exclude<RecommendationAction, "retry"> }) => {
      const values = action === "set_browser"
        ? { adapter: "browser" }
        : action === "set_auto"
          ? { adapter: "auto" }
          : { adapter: "auto", careers_url: "" };
      await api.updateCompany(company.id, values);
      return { action, companies: await api.companies() };
    },
    onSuccess: ({ action, companies: updatedCompanies }) => {
      client.setQueryData(["companies"], updatedCompanies);
      const updated = updatedCompanies.find((company) => company.id === sourceCompany?.id);
      if (updated) setSourceCompany(updated);
      if (updated) void client.invalidateQueries({ queryKey: ["company-diagnostics", updated.id] });
      setMessage(action === "rediscover" ? "Careers URL очищен. Запустите повторную проверку для нового discovery." : "Рекомендованная настройка адаптера сохранена.");
    },
  });

  function closeImport() {
    setSelectedFile(null);
    setResetExisting(false);
    setDeduplicate(true);
    importMutation.reset();
    if (fileInput.current) fileInput.current.value = "";
  }
  function toggleVisible() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }
  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editCompany) return;
    const data = new FormData(event.currentTarget);
    editMutation.mutate({
      id: editCompany.id,
      values: {
        name: data.get("name"),
        website_url: data.get("website_url"),
        careers_url: data.get("careers_url"),
        locations: data.get("locations"),
        type: data.get("type"),
      },
    });
  }
  function submitSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sourceCompany) return;
    const data = new FormData(event.currentTarget);
    editMutation.mutate({
      id: sourceCompany.id,
      values: {
        careers_url: data.get("careers_url"),
        adapter: data.get("adapter"),
      },
    });
  }
  function retryCompany(company: CompanySummary) {
    const result = diagnostics.data?.company_id === company.id ? diagnostics.data.latest_result : null;
    setSourceRetry({
      companyId: company.id,
      runId: null,
      phase: "starting",
      before: sourceSnapshot(company, result),
    });
    singleCrawl.mutate(company.id);
  }
  useEffect(() => {
    const status = sourceRun.data;
    const retry = sourceRetry;
    if (!retry || retry.phase !== "running" || !status || status.run_id !== retry.runId) return;
    if (status.state === "running" || status.state === "queued") return;
    if (status.state !== "completed") {
      setSourceRetry({ ...retry, phase: "failed", error: status.error ?? (status.state === "cancelled" ? "Поиск был остановлен." : "Поиск завершился с ошибкой.") });
      return;
    }
    setSourceRetry({ ...retry, phase: "refreshing" });
    void Promise.all([api.companies(), api.companyDiagnostics(retry.companyId), api.companyHistory(retry.companyId)])
      .then(([updatedCompanies, updatedDiagnostics, updatedHistory]) => {
        client.setQueryData(["companies"], updatedCompanies);
        client.setQueryData(["company-diagnostics", retry.companyId], updatedDiagnostics);
        client.setQueryData(["company-history", retry.companyId], updatedHistory);
        const updatedCompany = updatedCompanies.find((company) => company.id === retry.companyId);
        if (!updatedCompany) throw new Error("Компания отсутствует в обновлённом списке.");
        setSourceCompany((current) => current?.id === updatedCompany.id ? updatedCompany : current);
        setSourceRetry((current) => current?.companyId === retry.companyId ? {
          ...current,
          phase: "completed",
          after: sourceSnapshot(updatedCompany, updatedDiagnostics.latest_result),
        } : current);
        void client.invalidateQueries({ queryKey: ["latest-run"] });
        void client.invalidateQueries({ queryKey: ["history"] });
        setMessage(`Повторная проверка ${updatedCompany.name} завершена.`);
      })
      .catch((error: Error) => setSourceRetry((current) => current?.companyId === retry.companyId ? { ...current, phase: "failed", error: error.message } : current));
  }, [client, sourceRetry, sourceRun.data]);
  useEffect(() => setPage(1), [search, statusFilter]);

  return (
    <div className="mx-auto w-full min-w-0 max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-admin-ink">
            Компании
          </h1>
          <p className="mt-1 text-sm text-admin-muted">
            Текущий список компаний, участвующих в поиске вакансий
          </p>
        </div>
        <button
          className="inline-flex h-10 items-center justify-center rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white hover:bg-admin-primary-dark"
          onClick={() => fileInput.current?.click()}
        >
          Добавить новые компании
        </button>
        <input
          ref={fileInput}
          className="hidden"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(event) => {
            setMessage(null);
            setSelectedFile(event.target.files?.[0] ?? null);
          }}
        />
      </header>
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {message}
        </div>
      )}
      {(bulkMutation.isError || selectedCrawl.isError) && (
        <ErrorState
          message={
            (bulkMutation.error ?? selectedCrawl.error)?.message ?? "Ошибка"
          }
        />
      )}
      <section className="rounded-xl border border-admin-border bg-white p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
            Поиск по названию
            <input
              className={control}
              placeholder="Например, Picsart"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
            Статус
            <select
              className={control}
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as StatusFilter)
              }
            >
              <option value="all">Все компании</option>
              <option value="success">Есть вакансии</option>
              <option value="no_jobs">Нет вакансий</option>
              <option value="unsupported">Вакансии не извлечены</option>
              <option value="failed">Ошибки</option>
              <option value="unverified">Не проверено</option>
              <option value="blocked">Заблокировано</option>
              <option value="unprocessed">Не обработано</option>
              <option value="refresh_due">Пора обновить</option>
              <option value="discovery">Нужно проверить Careers URL</option>
              <option value="skipped">Отключено</option>
            </select>
          </label>
        </div>
      </section>
      {selectedIds.size > 0 && (
        <section className="flex flex-wrap items-center gap-2 rounded-xl border border-admin-primary/20 bg-white p-3">
          <span className="mr-auto text-sm font-medium">
            Выбрано: {selectedIds.size}
          </span>
          <button
            className="pager-button"
            onClick={() => selectedCrawl.mutate([...selectedIds])}
          >
            Искать выбранные
          </button>
          <button
            className="pager-button"
            onClick={() =>
              bulkMutation.mutate({ action: "enable", ids: [...selectedIds] })
            }
          >
            Включить
          </button>
          <button
            className="pager-button"
            onClick={() =>
              bulkMutation.mutate({ action: "disable", ids: [...selectedIds] })
            }
          >
            Отключить
          </button>
          <button
            className="h-9 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50"
            onClick={() =>
              window.confirm(`Удалить ${selectedIds.size} компаний?`) &&
              bulkMutation.mutate({ action: "delete", ids: [...selectedIds] })
            }
          >
            Удалить
          </button>
        </section>
      )}
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState
          message={query.error.message}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <section ref={tableRef} className="scroll-mt-4 overflow-hidden rounded-xl border border-admin-border bg-white">
          <div className="flex items-center justify-between border-b border-admin-border px-4 py-3">
            <h2 className="font-semibold">Список компаний</h2>
            <span className="text-sm text-admin-muted">
              {companies.length} результатов
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1200px] text-left text-sm">
              <thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase text-admin-muted">
                <tr>
                  <th className="px-4 py-3">
                    <input
                      aria-label="Выбрать компании на странице"
                      className="accent-admin-primary"
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleVisible}
                    />
                  </th>
                  <th className="px-4 py-3">Компания</th>
                  <th className="px-4 py-3">Тип</th>
                  <th className="px-4 py-3">Локация</th>
                  <th className="px-4 py-3">Remote</th>
                  <th className="px-4 py-3">Статус</th>
                  <th className="px-4 py-3">Вакансии</th>
                  <th className="px-4 py-3">Последняя проверка</th>
                  <th className="px-4 py-3">Ссылки и действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-admin-border">
                {visible.map((company) => (
                  <CompanyRow
                    key={company.id}
                    company={company}
                    selected={selectedIds.has(company.id)}
                    onSelect={() =>
                      setSelectedIds((current) => {
                        const next = new Set(current);
                        next.has(company.id)
                          ? next.delete(company.id)
                          : next.add(company.id);
                        return next;
                      })
                    }
                    onEdit={() => setEditCompany(company)}
                    onSource={() => {
                      if (sourceRetry?.companyId !== company.id || sourceRetry.phase !== "running") setSourceRetry(null);
                      setSourceCompany(company);
                    }}
                    onDecision={(decision) =>
                      decisionMutation.mutate({ company, decision })
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
          {!visible.length ? (
            <div className="border-t border-admin-border px-4 py-12 text-center text-admin-muted">
              Компании не найдены
            </div>
          ) : (
            <footer className="flex flex-col gap-3 border-t border-admin-border px-4 py-3 text-sm text-admin-muted sm:flex-row sm:items-center sm:justify-between">
              <span>
                Показано {firstVisible + 1}–{firstVisible + visible.length} из{" "}
                {companies.length}
              </span>
              <Pagination page={currentPage} pages={pages} onChange={setPage} scrollTarget={tableRef} />
            </footer>
          )}
        </section>
      )}
      {selectedFile && (
        <ImportModal
          file={selectedFile}
          resetExisting={resetExisting}
          deduplicate={deduplicate}
          preview={preview}
          importing={importMutation.isPending}
          importError={importMutation.error?.message}
          onReset={setResetExisting}
          onDeduplicate={setDeduplicate}
          onClose={closeImport}
          onConfirm={() => importMutation.mutate()}
        />
      )}
      {editCompany && (
        <EditModal
          company={editCompany}
          pending={editMutation.isPending}
          error={editMutation.error?.message}
          onClose={() => setEditCompany(null)}
          onSubmit={submitEdit}
        />
      )}
      {sourceCompany && (
        <SourceModal
          company={sourceCompany}
          diagnostics={diagnostics}
          history={companyHistory}
          pending={editMutation.isPending || singleCrawl.isPending || decisionMutation.isPending || recommendationMutation.isPending}
          error={editMutation.error?.message ?? singleCrawl.error?.message ?? decisionMutation.error?.message ?? recommendationMutation.error?.message}
          retry={sourceRetry?.companyId === sourceCompany.id ? sourceRetry : null}
          runStatus={sourceRetry?.companyId === sourceCompany.id ? sourceRun.data : undefined}
          onClose={() => setSourceCompany(null)}
          onSubmit={submitSource}
          onRetry={() => retryCompany(sourceCompany)}
          onRecommendation={(action) => recommendationMutation.mutate({ company: sourceCompany, action })}
          onDecision={(decision) => decisionMutation.mutate({ company: sourceCompany, decision })}
        />
      )}
    </div>
  );
}

function CompanyRow({
  company,
  selected,
  onSelect,
  onEdit,
  onSource,
  onDecision,
}: {
  company: CompanySummary;
  selected: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onSource: () => void;
  onDecision: (decision: "approve" | "reject") => void;
}) {
  return (
    <tr className="transition hover:bg-admin-soft/70">
      <td className="px-4 py-3">
        <input
          aria-label={`Выбрать ${company.name}`}
          className="accent-admin-primary"
          type="checkbox"
          checked={selected}
          onChange={onSelect}
        />
      </td>
      <td className="px-4 py-3 font-medium">
        {company.name}
        {!company.enabled && (
          <span className="ml-2 text-xs text-admin-muted">выключена</span>
        )}
      </td>
      <td className="px-4 py-3 text-admin-muted">{company.type ?? "—"}</td>
      <td className="max-w-72 px-4 py-3 text-admin-muted">
        {company.locations ?? "—"}
      </td>
      <td className="px-4 py-3 text-admin-muted">
        {company.remote_compatibility ?? "—"}
      </td>
      <td className="px-4 py-3">
        <span className="rounded-md bg-admin-primary/8 px-2 py-1 text-xs font-medium text-admin-primary">
          {company.crawl_status
            ? statusLabel[company.crawl_status]
            : "Не обработана"}
        </span>
      </td>
      <td className="px-4 py-3 font-medium">{company.jobs_found}</td>
      <td className="whitespace-nowrap px-4 py-3 text-admin-muted">
        {formatDate(company.last_crawled_at)}
        {company.refresh_due && (
          <span className="ml-2 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">
            Пора обновить
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <a
            className="inline-flex items-center gap-1 text-admin-primary hover:underline"
            href={company.website_url}
            rel="noreferrer"
            target="_blank"
          >
            Сайт <ExternalIcon className="size-4" />
          </a>
          {company.careers_url && (
            <a
              className="inline-flex items-center gap-1 text-admin-primary hover:underline"
              href={company.careers_url}
              rel="noreferrer"
              target="_blank"
            >
              Careers <ExternalIcon className="size-4" />
            </a>
          )}
          <button
            className="text-admin-primary hover:underline"
            onClick={onEdit}
          >
            Изменить
          </button>
          <button
            className="text-admin-primary hover:underline"
            onClick={onSource}
          >
            Источник
          </button>
          {company.discovery_pending && (
            <>
              <button
                className="text-emerald-700 hover:underline"
                onClick={() => onDecision("approve")}
              >
                Принять URL
              </button>
              <button
                className="text-red-700 hover:underline"
                onClick={() => onDecision("reject")}
              >
                Отклонить
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

function ImportModal({
  file,
  resetExisting,
  deduplicate,
  preview,
  importing,
  importError,
  onReset,
  onDeduplicate,
  onClose,
  onConfirm,
}: any) {
  return (
    <Modal labelledBy="company-import-title" onClose={onClose} closeDisabled={importing}>
        <h2 className="text-xl font-semibold" id="company-import-title">
          Хотите добавить эти компании?
        </h2>
        <p className="mt-2 break-all text-sm text-admin-muted">
          Файл: {file.name}
        </p>
        <div className="mt-5 space-y-3">
          <CheckOption
            checked={resetExisting}
            title="Обнулить данные"
            description="Заменить рабочий список компаниями из файла."
            onChange={onReset}
          />
          <CheckOption
            checked={deduplicate}
            title="Отфильтровать дубликаты"
            description="Сравнить название и основной сайт."
            onChange={onDeduplicate}
          />
        </div>
        <div className="mt-4 rounded-xl bg-admin-soft p-4">
          {preview.isLoading ? (
            <p className="text-sm text-admin-muted">Проверяем файл…</p>
          ) : preview.isError ? (
            <p className="text-sm text-red-700">{preview.error.message}</p>
          ) : (
            preview.data && (
              <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <Metric label="В файле" value={preview.data.uploaded} />
                <Metric
                  label="Будет добавлено"
                  value={preview.data.would_add}
                />
                <Metric
                  label="Дубликаты"
                  value={preview.data.duplicates_found}
                />
                <Metric
                  label="Итого после импорта"
                  value={preview.data.total_after_import}
                />
              </div>
            )
          )}
        </div>
        {resetExisting && (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            Текущий список будет заменён. Backend создаст резервную копию.
          </p>
        )}
        {importError && (
          <p className="mt-3 text-sm text-red-700">{importError}</p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            className="pager-button"
            disabled={importing}
            onClick={onClose}
          >
            Нет
          </button>
          <button
            className="h-10 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white disabled:opacity-60"
            disabled={importing || preview.isLoading || preview.isError}
            onClick={onConfirm}
          >
            {importing ? "Добавляем…" : "Да"}
          </button>
        </div>
    </Modal>
  );
}

function CheckOption({
  checked,
  title,
  description,
  onChange,
}: {
  checked: boolean;
  title: string;
  description: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-admin-border p-3 text-sm">
      <input
        className="mt-0.5 accent-admin-primary"
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <strong className="block">{title}</strong>
        <span className="text-admin-muted">{description}</span>
      </span>
    </label>
  );
}
function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <span className="text-admin-muted">{label}</span>
      <strong className="block text-lg">{value}</strong>
    </div>
  );
}

function SourceModal({
  company,
  diagnostics,
  history,
  pending,
  error,
  retry,
  runStatus,
  onClose,
  onSubmit,
  onRetry,
  onRecommendation,
  onDecision,
}: {
  company: CompanySummary;
  diagnostics: UseQueryResult<CompanyDiagnostics, Error>;
  history: UseQueryResult<CompanyHistoryItem[], Error>;
  pending: boolean;
  error?: string;
  retry: SourceRetryState | null;
  runStatus?: ActiveRun;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRetry: () => void;
  onRecommendation: (action: Exclude<RecommendationAction, "retry">) => void;
  onDecision: (decision: "approve" | "reject") => void;
}) {
  const result = diagnostics.data?.latest_result;
  const retryBusy = retry?.phase === "starting" || retry?.phase === "running" || retry?.phase === "refreshing";
  const actionDisabled = pending || retryBusy;
  const recommendations = buildSourceRecommendations(company, diagnostics.data);
  return (
    <Modal labelledBy="company-source-title" onClose={onClose} closeDisabled={pending} size="wide">
      <div className="pr-10">
        <h2 className="text-xl font-semibold text-admin-ink" id="company-source-title">Источник: {company.name}</h2>
        <p className="mt-1 text-sm text-admin-muted">Настройка карьерной страницы, способа обработки и диагностика последнего результата.</p>
      </div>

      {retry && <RetryResult retry={retry} status={runStatus} />}

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="space-y-5">
          <form className="rounded-xl border border-admin-border p-4" onSubmit={onSubmit}>
            <h3 className="font-semibold text-admin-ink">Настройка источника</h3>
            <div className="mt-4 grid gap-3">
              <EditField label="Careers URL" name="careers_url" value={company.configured_careers_url ?? ""} />
              <label className="grid gap-1 text-xs text-admin-muted">
                Адаптер
                <select className={control} name="adapter" defaultValue={company.adapter}>
                  <option value="auto">Автоматически — ATS, JSON-LD, HTML, Playwright fallback</option>
                  <option value="html">Только HTTP / HTML</option>
                  <option value="browser">Playwright / браузер</option>
                </select>
              </label>
              <p className="text-xs leading-5 text-admin-muted">Обычно оставляйте «Автоматически». Принудительный режим полезен для диагностики нестандартных страниц.</p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="h-9 rounded-lg bg-admin-primary px-3 text-sm font-semibold text-white disabled:opacity-60" disabled={actionDisabled} type="submit">Сохранить источник</button>
              <button className="pager-button inline-flex items-center gap-2" disabled={actionDisabled || !company.enabled} onClick={onRetry} type="button"><RefreshIcon className={`size-4 ${retryBusy ? "animate-spin" : ""}`} />{retryBusy ? "Проверяем…" : "Повторно проверить"}</button>
            </div>
          </form>

          <RecommendationPanel
            recommendations={recommendations}
            disabled={actionDisabled}
            onAction={(action) => action === "retry" ? onRetry() : onRecommendation(action)}
          />

          {company.discovery_pending && company.resolved_careers_url && (
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <h3 className="font-semibold text-amber-900">Найдена новая карьерная страница</h3>
              <a className="mt-2 inline-flex max-w-full items-center gap-1 break-all text-sm text-admin-primary hover:underline" href={company.resolved_careers_url} target="_blank" rel="noreferrer">{company.resolved_careers_url}<ExternalIcon className="size-4 shrink-0" /></a>
              <div className="mt-4 flex gap-2">
                <button className="h-9 rounded-lg bg-emerald-700 px-3 text-sm font-semibold text-white disabled:opacity-60" disabled={actionDisabled} onClick={() => onDecision("approve")} type="button">Подтвердить URL</button>
                <button className="h-9 rounded-lg border border-red-200 bg-white px-3 text-sm font-medium text-red-700 disabled:opacity-60" disabled={actionDisabled} onClick={() => onDecision("reject")} type="button">Отклонить</button>
              </div>
            </section>
          )}

          <section className="rounded-xl border border-admin-border p-4">
            <h3 className="font-semibold text-admin-ink">{retry?.phase === "completed" ? "Новый лог обработки" : "Последний лог обработки"}</h3>
            {result ? (
              <>
                <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 text-sm sm:grid-cols-2">
                  <LogValue label="Статус" value={statusLabel[result.status]} />
                  <LogValue label="Адаптер" value={result.adapter ?? "Не определён"} />
                  <LogValue label="Найдено кандидатов" value={String(result.candidates_found)} />
                  <LogValue label="Frontend-вакансии" value={String(result.matching_jobs)} />
                  <LogValue label="Длительность" value={`${result.duration_ms} мс`} />
                  <LogValue label="Последняя проверка" value={formatDate(result.last_crawled_at)} />
                </dl>
                {result.error && <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{result.error}</div>}
                {result.warnings.length > 0 && <div className="mt-4"><p className="text-xs font-semibold uppercase text-admin-muted">Предупреждения</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-admin-muted">{result.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul></div>}
              </>
            ) : <p className="mt-3 text-sm text-admin-muted">Компания ещё не обрабатывалась.</p>}
          </section>
        </div>

        <section className="min-w-0 rounded-xl border border-admin-border p-4">
          <div className="flex items-start justify-between gap-3">
            <div><h3 className="font-semibold text-admin-ink">Raw HTTP response</h3><p className="mt-0.5 text-xs text-admin-muted">Свежий ограниченный preview текущего URL, без Playwright.</p></div>
            <button className="pager-button shrink-0" disabled={diagnostics.isFetching} onClick={() => void diagnostics.refetch()} type="button">Обновить</button>
          </div>
          {diagnostics.isLoading ? (
            <div className="grid min-h-48 place-items-center text-sm text-admin-muted">Загружаем ответ…</div>
          ) : diagnostics.isError ? (
            <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{diagnostics.error.message}</div>
          ) : diagnostics.data ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg bg-admin-soft p-3 text-xs">
                <p className="break-all"><span className="text-admin-muted">Request:</span> {diagnostics.data.request_url}</p>
                {diagnostics.data.response_url && <p className="mt-1 break-all"><span className="text-admin-muted">Response:</span> {diagnostics.data.response_status} · {diagnostics.data.response_url}</p>}
                {Object.entries(diagnostics.data.response_headers).map(([key, value]) => <p className="mt-1 break-all" key={key}><span className="text-admin-muted">{key}:</span> {value}</p>)}
              </div>
              {diagnostics.data.fetch_error && <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{diagnostics.data.fetch_error}</div>}
              {diagnostics.data.raw_preview !== null && <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-[#1f1f1f] p-4 text-xs leading-5 text-[#f3f4f4]">{diagnostics.data.raw_preview}</pre>}
              {diagnostics.data.raw_truncated && <p className="text-xs text-admin-muted">Ответ обрезан до первых 50 000 символов.</p>}
            </div>
          ) : null}
        </section>
      </div>
      <CompanyHistory history={history} />
      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    </Modal>
  );
}

function RecommendationPanel({
  recommendations,
  disabled,
  onAction,
}: {
  recommendations: ReturnType<typeof buildSourceRecommendations>;
  disabled: boolean;
  onAction: (action: RecommendationAction) => void;
}) {
  const tones = {
    info: "border-blue-200 bg-blue-50 text-blue-900",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
    error: "border-red-200 bg-red-50 text-red-900",
  };
  return (
    <section className="rounded-xl border border-admin-border p-4" aria-label="Рекомендации по источнику">
      <h3 className="font-semibold text-admin-ink">Рекомендации</h3>
      {!recommendations.length ? (
        <p className="mt-2 text-sm text-admin-muted">По последнему логу явных проблем, требующих изменения источника, не найдено.</p>
      ) : (
        <div className="mt-3 space-y-2">
          {recommendations.map((recommendation) => (
            <div className={`rounded-lg border p-3 ${tones[recommendation.tone]}`} key={recommendation.id}>
              <p className="text-sm font-semibold">{recommendation.title}</p>
              <p className="mt-1 text-xs leading-5 opacity-80">{recommendation.message}</p>
              {recommendation.action && recommendation.actionLabel && (
                <button className="mt-2 rounded-lg border border-current/20 bg-white px-2.5 py-1.5 text-xs font-semibold transition hover:bg-white/70 disabled:opacity-50" disabled={disabled} onClick={() => onAction(recommendation.action!)} type="button">{recommendation.actionLabel}</button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CompanyHistory({ history }: { history: UseQueryResult<CompanyHistoryItem[], Error> }) {
  return (
    <section className="mt-5 overflow-hidden rounded-xl border border-admin-border">
      <div className="flex items-start justify-between gap-3 border-b border-admin-border px-4 py-3">
        <div><h3 className="font-semibold text-admin-ink">История компании</h3><p className="mt-0.5 text-xs text-admin-muted">Последние пять реальных проверок этой компании</p></div>
        <button className="pager-button shrink-0" disabled={history.isFetching} onClick={() => void history.refetch()} type="button">Обновить</button>
      </div>
      {history.isLoading ? (
        <div className="grid min-h-28 place-items-center text-sm text-admin-muted">Загружаем историю…</div>
      ) : history.isError ? (
        <div className="m-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{history.error.message}</div>
      ) : !history.data?.length ? (
        <div className="px-4 py-10 text-center text-sm text-admin-muted">История появится после первой завершённой проверки.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm" aria-label="История проверок компании">
            <thead className="bg-admin-soft text-xs font-semibold uppercase text-admin-muted"><tr><th className="px-4 py-3">Дата</th><th className="px-4 py-3">Статус</th><th className="px-4 py-3">Careers URL</th><th className="px-4 py-3">Адаптер</th><th className="px-4 py-3">Вакансии</th><th className="px-4 py-3">Ошибка</th><th className="px-4 py-3">Длительность</th></tr></thead>
            <tbody className="divide-y divide-admin-border">{history.data.map((item) => (
              <tr key={item.run_id} className="align-top hover:bg-admin-soft/60">
                <td className="whitespace-nowrap px-4 py-3 text-admin-muted">{formatDate(item.checked_at)}</td>
                <td className="px-4 py-3"><span className="rounded-md bg-admin-primary/8 px-2 py-1 text-xs font-medium text-admin-primary">{statusLabel[item.status]}</span></td>
                <td className="max-w-72 px-4 py-3">{item.careers_url ? <a className="inline-flex items-start gap-1 break-all text-admin-primary hover:underline" href={item.careers_url} target="_blank" rel="noreferrer">{item.careers_url}<ExternalIcon className="mt-0.5 size-4 shrink-0" /></a> : <span className="text-admin-muted">Не найден</span>}</td>
                <td className="px-4 py-3 text-admin-muted">{item.adapter ?? "Не определён"}</td>
                <td className="px-4 py-3 font-medium tabular-nums">{item.jobs_found}</td>
                <td className="max-w-72 px-4 py-3 text-red-700">{item.error ?? "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 tabular-nums text-admin-muted">{formatMilliseconds(item.duration_ms)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function formatMilliseconds(value: number) {
  return value < 1_000 ? `${value} мс` : `${(value / 1_000).toFixed(1)} сек`;
}

function LogValue({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-admin-muted">{label}</dt><dd className="mt-0.5 break-words font-medium text-admin-ink">{value}</dd></div>;
}

function RetryResult({ retry, status }: { retry: SourceRetryState; status?: ActiveRun }) {
  if (retry.phase === "failed") {
    return <section className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4" aria-live="polite"><h3 className="font-semibold text-red-800">Повторная проверка не завершена</h3><p className="mt-1 text-sm text-red-700">{retry.error ?? "Неизвестная ошибка"}</p></section>;
  }
  if (retry.phase !== "completed" || !retry.after) {
    const processed = status?.run_id === retry.runId ? status.processed : 0;
    const total = status?.run_id === retry.runId ? status.total : 1;
    const progress = retry.phase === "refreshing" ? 100 : total > 0 ? Math.round((processed / total) * 100) : 0;
    const label = retry.phase === "starting" ? "Запускаем повторную проверку…" : retry.phase === "refreshing" ? "Обновляем результат и лог…" : "Повторно проверяем компанию…";
    return (
      <section className="mt-5 rounded-xl border border-admin-primary/20 bg-admin-primary/5 p-4" aria-live="polite">
        <div className="flex items-center justify-between gap-3 text-sm"><span className="font-semibold text-admin-ink">{label}</span><span className="tabular-nums text-admin-muted">{progress}%</span></div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-admin-primary/10"><div className="h-full rounded-full bg-admin-primary transition-all" style={{ width: `${progress}%` }} /></div>
      </section>
    );
  }
  const careersChanged = retry.before.careersUrl !== retry.after.careersUrl;
  const rows = [
    ["Статус", snapshotStatus(retry.before.status), snapshotStatus(retry.after.status)],
    ["Вакансии", String(retry.before.jobs), String(retry.after.jobs)],
    ["Адаптер", retry.before.adapter ?? "Не определён", retry.after.adapter ?? "Не определён"],
    ["Careers URL", retry.before.careersUrl ?? "Не найден", retry.after.careersUrl ?? "Не найден"],
  ];
  return (
    <section className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-emerald-900">Повторная проверка завершена</h3><p className="mt-0.5 text-sm text-emerald-800">Результат и диагностический лог обновлены автоматически.</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${careersChanged ? "bg-amber-100 text-amber-800" : "bg-white text-emerald-800"}`}>{careersChanged ? "Careers URL изменился" : "Careers URL без изменений"}</span></div>
      <div className="mt-4 overflow-x-auto rounded-lg border border-emerald-200 bg-white">
        <table className="w-full min-w-[560px] text-left text-sm" aria-label="Сравнение результатов повторной проверки">
          <thead className="bg-emerald-50 text-xs uppercase text-emerald-800"><tr><th className="px-3 py-2">Показатель</th><th className="px-3 py-2">До</th><th className="px-3 py-2">После</th></tr></thead>
          <tbody className="divide-y divide-admin-border">{rows.map(([label, before, after]) => <tr key={label}><th className="px-3 py-2 font-medium text-admin-muted">{label}</th><td className="max-w-64 break-all px-3 py-2 text-admin-muted">{before}</td><td className={`max-w-64 break-all px-3 py-2 font-medium ${before !== after ? "text-admin-primary" : "text-admin-ink"}`}>{after}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}

function snapshotStatus(status: CompanyStatus | null) {
  return status ? statusLabel[status] : "Не проверена";
}

function EditModal({
  company,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  company: CompanySummary;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <Modal as="form" labelledBy="company-edit-title" onClose={onClose} closeDisabled={pending} onSubmit={onSubmit}>
        <h2 className="text-xl font-semibold" id="company-edit-title">
          Изменить компанию
        </h2>
        <div className="mt-5 grid gap-3">
          <EditField
            label="Название"
            name="name"
            value={company.name}
            required
          />
          <EditField
            label="Website"
            name="website_url"
            value={company.website_url}
            required
          />
          <EditField
            label="Careers URL"
            name="careers_url"
            value={company.configured_careers_url ?? ""}
          />
          <EditField label="Тип" name="type" value={company.type ?? ""} />
          <EditField
            label="Локации"
            name="locations"
            value={company.locations ?? ""}
          />
        </div>
        {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button className="pager-button" type="button" onClick={onClose}>
            Отмена
          </button>
          <button
            className="h-10 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white"
            disabled={pending}
            type="submit"
          >
            Сохранить
          </button>
        </div>
    </Modal>
  );
}
function EditField({
  label,
  name,
  value,
  required = false,
}: {
  label: string;
  name: string;
  value: string;
  required?: boolean;
}) {
  return (
    <label className="grid gap-1 text-xs text-admin-muted">
      {label}
      <input
        className={control}
        name={name}
        defaultValue={value}
        required={required}
      />
    </label>
  );
}
