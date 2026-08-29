import { useEffect, useRef, useState } from "react";
import { ExternalIcon } from "./Icons";
import { formatDate } from "../lib/format";
import { jobFormat } from "../lib/jobs";
import type { Job, ResumeMatch, WorkFormat } from "../types";
import { Pagination } from "./Pagination";

const formatLabels: Record<WorkFormat, string> = {
  remote: "Удалённо",
  hybrid: "Гибрид",
  onsite: "В офисе",
  unknown: "Не указан",
};

interface Props { jobs: Job[]; pageSize?: number; newJobIds?: ReadonlySet<string>; resumeMatches?: ReadonlyMap<string, ResumeMatch> }

export function JobsTable({ jobs, pageSize = 20, newJobIds, resumeMatches }: Props) {
  const [page, setPage] = useState(1);
  const tableRef = useRef<HTMLElement>(null);
  const pages = Math.max(1, Math.ceil(jobs.length / pageSize));
  useEffect(() => setPage(1), [jobs]);
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visible = jobs.slice(firstVisible, firstVisible + pageSize);

  if (!jobs.length) {
    return <div className="rounded-xl border border-dashed border-admin-border bg-white px-6 py-14 text-center"><p className="font-medium text-admin-ink">Вакансии не найдены</p><p className="mt-1 text-sm text-admin-muted">Измените фильтры или запустите новый поиск.</p></div>;
  }

  return (
    <section className="scroll-mt-4 overflow-hidden rounded-xl border border-admin-border bg-white" ref={tableRef}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1050px] text-left text-sm">
          <thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase tracking-wide text-admin-muted">
            <tr><th className="px-4 py-3">Компания</th><th className="px-4 py-3">Вакансия</th>{resumeMatches && <th className="px-4 py-3">Матч</th>}<th className="px-4 py-3">Уровень</th><th className="px-4 py-3">Стек</th><th className="px-4 py-3">Локация</th><th className="px-4 py-3">Формат</th><th className="px-4 py-3">Дата</th><th className="w-12"><span className="sr-only">Открыть</span></th></tr>
          </thead>
          <tbody className="divide-y divide-admin-border">
            {visible.map((job) => (
              <tr className="transition hover:bg-admin-soft/70" key={job.job_id}>
                <td className="px-4 py-3 font-medium text-admin-ink">{job.company}</td>
                <td className="max-w-xs px-4 py-3"><div className="flex items-center gap-2 justify-between"><a className="block min-w-0 truncate font-medium text-admin-primary-dark hover:underline" href={job.url} target="_blank" rel="noreferrer" title={job.title}>{job.title}</a>{(newJobIds?.has(job.job_id) || job.lifecycle === "new") && <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">Новая</span>}</div></td>
                {resumeMatches && <td className="px-4 py-3"><MatchBadge match={resumeMatches.get(job.job_id)} /></td>}
                <td className="px-4 py-3 text-admin-muted">{job.seniority ?? "Не указан"}</td>
                <td className="px-4 py-3"><div className="flex max-w-56 flex-wrap gap-1">{job.technologies.length ? job.technologies.slice(0, 3).map((item) => <span className="rounded-md bg-admin-primary/8 px-2 py-1 text-xs text-admin-primary-dark" key={item}>{item}</span>) : <span className="text-admin-muted">—</span>}</div></td>
                <td className="max-w-52 px-4 py-3 text-admin-muted"><span className="line-clamp-2">{job.location ?? "Не указана"}</span></td>
                <td className="px-4 py-3 text-admin-muted">{formatLabels[jobFormat(job)]}</td>
                <td className="whitespace-nowrap px-4 py-3 text-admin-muted">{formatDate(job.published_at ?? job.found_at)}</td>
                <td className="pr-4"><a className="inline-flex rounded-lg p-2 text-admin-primary transition hover:bg-admin-primary/10" href={job.url} target="_blank" rel="noreferrer" aria-label={`Открыть вакансию ${job.title}`}><ExternalIcon className="size-4" /></a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="flex flex-col gap-3 border-t border-admin-border px-4 py-3 text-sm text-admin-muted sm:flex-row sm:items-center sm:justify-between">
        <span>Показано {firstVisible + 1}–{firstVisible + visible.length} из {jobs.length}</span>
        <Pagination page={currentPage} pages={pages} onChange={setPage} scrollTarget={tableRef} />
      </footer>
    </section>
  );
}

function MatchBadge({ match }: { match?: ResumeMatch }) {
  if (!match) return <span className="text-admin-muted">—</span>;
  const color = match.score >= 70 ? "bg-emerald-100 text-emerald-700" : match.score >= 35 ? "bg-amber-100 text-amber-700" : "bg-admin-soft text-admin-muted";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${color}`} title={match.reasons.join(". ") || "Совпадений мало"}>{match.score}%</span>;
}
