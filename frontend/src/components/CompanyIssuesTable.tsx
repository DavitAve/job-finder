import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { classifyIssue, collectIssues, issueMessage, type ErrorCategory, type IssueStatus } from "../lib/issues";
import type { CompanyCrawlResult, CrawlError } from "../types";
import { Pagination } from "./Pagination";

interface Props {
  companies: CompanyCrawlResult[];
  errors: CrawlError[];
  status: IssueStatus | readonly IssueStatus[];
  category?: ErrorCategory | "all";
  pageSize?: number;
}

const statusLabels: Record<IssueStatus, string> = {
  no_jobs: "Нет вакансий",
  unsupported: "Не извлечено",
  blocked: "Заблокировано",
  failed: "Ошибка",
  unverified: "Не проверено",
};

export function CompanyIssuesTable({
  companies,
  errors,
  status,
  category = "all",
  pageSize = 20,
}: Props) {
  const statuses = useMemo(
    () => (Array.isArray(status) ? status : [status]) as readonly IssueStatus[],
    [status],
  );
  const statusKey = statuses.join(",");
  const issues = useMemo(() => {
    const collected = collectIssues(companies, errors, statuses);
    return category === "all"
      ? collected
      : collected.filter((item) => classifyIssue(item, errors) === category);
  }, [category, companies, errors, statusKey]);
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const tableRef = useRef<HTMLElement>(null);
  const pages = Math.max(1, Math.ceil(issues.length / pageSize));
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visible = issues.slice(firstVisible, firstVisible + pageSize);

  useEffect(() => {
    setPage(1);
    setExpanded(null);
  }, [category, issues.length, statusKey]);

  if (!issues.length) {
    return (
      <div className="rounded-xl border border-dashed border-admin-border bg-white px-6 py-14 text-center">
        <p className="font-medium text-admin-ink">Записей нет</p>
        <p className="mt-1 text-sm text-admin-muted">
          В этом запуске нет компаний с выбранным статусом.
        </p>
      </div>
    );
  }

  return (
    <section className="scroll-mt-4 overflow-hidden rounded-xl border border-admin-border bg-white" ref={tableRef}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase tracking-wide text-admin-muted">
            <tr>
              <th className="px-4 py-3">Компания</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Адаптер</th>
              <th className="px-4 py-3">Кандидатов</th>
              <th className="px-4 py-3">Время</th>
              <th className="px-4 py-3">Сайт компании</th>
              <th className="px-4 py-3">Career page</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-admin-border">
            {visible.map((item) => {
              const rowKey = `${item.status}-${item.company_id}`;
              const careerUrl = item.resolved_careers_url ?? item.careers_url;
              const isExpanded = expanded === rowKey;
              const toggle = () =>
                setExpanded((current) => (current === rowKey ? null : rowKey));
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
                        onClick={(event) => {
                          event.stopPropagation();
                          toggle();
                        }}
                        type="button"
                      >
                        <span
                          className={`text-admin-primary transition ${isExpanded ? "rotate-180" : ""}`}
                          aria-hidden
                        >
                          ⌄
                        </span>
                        {item.company}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-md px-2 py-1 text-xs font-medium ${item.status === "no_jobs" ? "bg-emerald-50 text-emerald-700" : item.status === "blocked" ? "bg-amber-50 text-amber-700" : item.status === "unverified" ? "bg-sky-50 text-sky-700" : item.status === "unsupported" ? "bg-violet-50 text-violet-700" : "bg-red-50 text-red-700"}`}
                      >
                        {statusLabels[item.status as IssueStatus]}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-admin-muted">
                      {item.adapter ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-admin-muted">
                      {item.candidates_found}
                    </td>
                    <td className="px-4 py-3 text-admin-muted">
                      {item.duration_ms
                        ? `${(item.duration_ms / 1000).toFixed(1)} сек`
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {item.website_url ? (
                        <a
                          className="text-admin-primary hover:underline"
                          href={item.website_url}
                          onClick={(event) => event.stopPropagation()}
                          rel="noreferrer"
                          target="_blank"
                        >
                          Открыть
                        </a>
                      ) : (
                        <span className="text-admin-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {careerUrl ? (
                        <a
                          className="text-admin-primary hover:underline"
                          href={careerUrl}
                          onClick={(event) => event.stopPropagation()}
                          rel="noreferrer"
                          target="_blank"
                        >
                          Открыть
                        </a>
                      ) : (
                        <span className="text-admin-muted">—</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr id={`${rowKey}-details`}>
                      <td className="bg-admin-primary/5 px-5 py-4" colSpan={7}>
                        <div className="border-l-2 border-admin-primary pl-4">
                          <div className="text-xs font-semibold uppercase tracking-wide text-admin-primary">
                            Причина
                          </div>
                          <p className="mt-1 break-words text-sm text-admin-ink">
                            {issueMessage(item, errors)}
                          </p>
                          {item.careers_url_discovered &&
                            item.resolved_careers_url && (
                              <p className="mt-2 text-sm text-admin-muted">
                                Career page найдена автоматически:{" "}
                                <a
                                  className="text-admin-primary hover:underline"
                                  href={item.resolved_careers_url}
                                  rel="noreferrer"
                                  target="_blank"
                                >
                                  {item.resolved_careers_url}
                                </a>
                              </p>
                            )}
                          {item.warnings.length > 0 && (
                            <div className="mt-3">
                              <div className="text-xs font-semibold uppercase tracking-wide text-admin-muted">
                                Предупреждения
                              </div>
                              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-admin-muted">
                                {item.warnings.map((warning) => (
                                  <li key={warning}>{warning}</li>
                                ))}
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
      <footer className="flex flex-col gap-3 border-t border-admin-border px-4 py-3 text-sm text-admin-muted sm:flex-row sm:items-center sm:justify-between">
        <span>
          Показано {firstVisible + 1}–{firstVisible + visible.length} из{" "}
          {issues.length}
        </span>
        <Pagination page={currentPage} pages={pages} onChange={setPage} scrollTarget={tableRef} />
      </footer>
    </section>
  );
}
