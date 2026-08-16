import { Fragment, useEffect, useMemo, useState } from "react";
import type { CompanyCrawlResult, CrawlError } from "../types";

type IssueStatus = "blocked" | "failed";

interface Props {
  companies: CompanyCrawlResult[];
  errors: CrawlError[];
  status: IssueStatus;
  pageSize?: number;
}

const statusLabels: Record<IssueStatus, string> = {
  blocked: "Заблокировано",
  failed: "Ошибка",
};

function errorMessage(item: CompanyCrawlResult, errors: CrawlError[]): string {
  return item.error
    ?? errors.find((error) => error.company_id === item.company_id && error.status === item.status)?.message
    ?? "Подробности не были предоставлены источником.";
}

export function CompanyIssuesTable({ companies, errors, status, pageSize = 20 }: Props) {
  const issues = useMemo(() => {
    const companyIssues = companies.filter((company) => company.status === status);
    if (companyIssues.length) return companyIssues;
    return errors.filter((error) => error.status === status).map<CompanyCrawlResult>((error) => ({
      company_id: error.company_id,
      company: error.company,
      careers_url: "",
      status: error.status,
      adapter: null,
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 0,
      error: error.message,
      warnings: [],
    }));
  }, [companies, errors, status]);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const pages = Math.max(1, Math.ceil(issues.length / pageSize));
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visible = issues.slice(firstVisible, firstVisible + pageSize);

  useEffect(() => {
    setPage(1);
    setExpanded(null);
  }, [issues.length, status]);

  if (!issues.length) {
    return (
      <div className="rounded-xl border border-dashed border-admin-border bg-white px-6 py-14 text-center">
        <p className="font-medium text-admin-ink">Записей нет</p>
        <p className="mt-1 text-sm text-admin-muted">В этом запуске нет компаний с выбранным статусом.</p>
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-admin-border bg-white">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase tracking-wide text-admin-muted">
            <tr>
              <th className="px-4 py-3">Компания</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Адаптер</th>
              <th className="px-4 py-3">Кандидатов</th>
              <th className="px-4 py-3">Время</th>
              <th className="px-4 py-3">Career page</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-admin-border">
            {visible.map((item) => {
              const rowKey = `${item.status}-${item.company_id}`;
              const careerUrl = item.resolved_careers_url ?? item.careers_url;
              const isExpanded = expanded === rowKey;
              const toggle = () => setExpanded((current) => current === rowKey ? null : rowKey);
              return (
                <Fragment key={rowKey}>
                  <tr
                    className="cursor-pointer transition hover:bg-admin-soft/70"
                    onClick={toggle}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        toggle();
                      }
                    }}
                    tabIndex={0}
                  >
                    <td className="px-4 py-3 font-medium text-admin-ink">
                      <button
                        aria-expanded={isExpanded}
                        aria-controls={`${rowKey}-details`}
                        className="flex w-full items-center gap-2 text-left"
                        onClick={(event) => { event.stopPropagation(); toggle(); }}
                        type="button"
                      >
                        <span className={`text-admin-primary transition ${isExpanded ? "rotate-180" : ""}`} aria-hidden>⌄</span>
                        {item.company}
                      </button>
                    </td>
                    <td className="px-4 py-3"><span className={`rounded-md px-2 py-1 text-xs font-medium ${status === "blocked" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700"}`}>{statusLabels[status]}</span></td>
                    <td className="px-4 py-3 text-admin-muted">{item.adapter ?? "—"}</td>
                    <td className="px-4 py-3 text-admin-muted">{item.candidates_found}</td>
                    <td className="px-4 py-3 text-admin-muted">{item.duration_ms ? `${(item.duration_ms / 1000).toFixed(1)} сек` : "—"}</td>
                    <td className="px-4 py-3">
                      {careerUrl ? <a className="text-admin-primary hover:underline" href={careerUrl} onClick={(event) => event.stopPropagation()} rel="noreferrer" target="_blank">Открыть</a> : <span className="text-admin-muted">—</span>}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr id={`${rowKey}-details`}>
                      <td className="bg-admin-primary/5 px-5 py-4" colSpan={6}>
                        <div className="border-l-2 border-admin-primary pl-4">
                          <div className="text-xs font-semibold uppercase tracking-wide text-admin-primary">Причина</div>
                          <p className="mt-1 break-words text-sm text-admin-ink">{errorMessage(item, errors)}</p>
                          {item.careers_url_discovered && item.resolved_careers_url && (
                            <p className="mt-2 text-sm text-admin-muted">
                              Career page найдена автоматически: <a className="text-admin-primary hover:underline" href={item.resolved_careers_url} rel="noreferrer" target="_blank">{item.resolved_careers_url}</a>
                            </p>
                          )}
                          {item.warnings.length > 0 && (
                            <div className="mt-3">
                              <div className="text-xs font-semibold uppercase tracking-wide text-admin-muted">Предупреждения</div>
                              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-admin-muted">
                                {item.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                              </ul>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <footer className="flex items-center justify-between border-t border-admin-border px-4 py-3 text-sm text-admin-muted">
        <span>Показано {firstVisible + 1}–{firstVisible + visible.length} из {issues.length}</span>
        <div className="flex items-center gap-2">
          <button className="pager-button" disabled={currentPage === 1} onClick={() => setPage((value) => value - 1)}>Назад</button>
          <span>{currentPage} / {pages}</span>
          <button className="pager-button" disabled={currentPage === pages} onClick={() => setPage((value) => value + 1)}>Далее</button>
        </div>
      </footer>
    </section>
  );
}
