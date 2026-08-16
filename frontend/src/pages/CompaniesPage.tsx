import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ExternalIcon } from "../components/Icons";
import { ErrorState, LoadingState } from "../components/QueryState";
import { api } from "../lib/api";
import type { CompanyStatus, CompanySummary } from "../types";

const pageSize = 20;
type StatusFilter = "all" | CompanyStatus | "unprocessed" | "discovery";

const statusLabel: Record<CompanyStatus, string> = {
  success: "Есть вакансии", no_jobs: "Нет вакансий", blocked: "Заблокировано",
  failed: "Ошибка", skipped: "Отключена",
};
const control = "h-10 rounded-lg border border-admin-border bg-white px-3 text-sm text-admin-ink outline-none transition focus:border-admin-primary focus:ring-2 focus:ring-admin-primary/15";

export function CompaniesPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const fileInput = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [resetExisting, setResetExisting] = useState(false);
  const [deduplicate, setDeduplicate] = useState(true);
  const [editCompany, setEditCompany] = useState<CompanySummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const companies = useMemo(() => {
    const value = search.trim().toLocaleLowerCase();
    return (query.data ?? []).filter((company) => {
      if (value && !company.name.toLocaleLowerCase().includes(value)) return false;
      if (statusFilter === "unprocessed") return company.crawl_status === null;
      if (statusFilter === "discovery") return company.discovery_pending;
      return statusFilter === "all" || company.crawl_status === statusFilter;
    });
  }, [query.data, search, statusFilter]);
  const pages = Math.max(1, Math.ceil(companies.length / pageSize));
  const currentPage = Math.min(page, pages);
  const firstVisible = (currentPage - 1) * pageSize;
  const visible = companies.slice(firstVisible, firstVisible + pageSize);
  const visibleIds = visible.map((company) => company.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  const preview = useQuery({
    queryKey: ["company-import-preview", selectedFile?.name, selectedFile?.size, resetExisting, deduplicate],
    queryFn: () => api.previewCompanies(selectedFile!, { resetExisting, deduplicate }),
    enabled: Boolean(selectedFile), retry: false,
  });
  const importMutation = useMutation({
    mutationFn: () => api.importCompanies(selectedFile!, { resetExisting, deduplicate }),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["companies"] });
      setMessage(`Добавлено: ${result.added}. Пропущено дубликатов: ${result.duplicates_skipped}. Всего компаний: ${result.total}.`);
      closeImport();
    },
  });
  const bulkMutation = useMutation({
    mutationFn: ({ action, ids }: { action: "enable" | "disable" | "delete"; ids: string[] }) => api.bulkCompanies(ids, action),
    onSuccess: (result) => { void client.invalidateQueries({ queryKey: ["companies"] }); setSelectedIds(new Set()); setMessage(`Изменено компаний: ${result.changed}. Всего компаний: ${result.total}.`); },
  });
  const editMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Record<string, unknown> }) => api.updateCompany(id, values),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["companies"] }); setEditCompany(null); setMessage("Данные компании обновлены."); },
  });
  const decisionMutation = useMutation({
    mutationFn: ({ company, decision }: { company: CompanySummary; decision: "approve" | "reject" }) => api.decideCareers(company.id, decision, company.resolved_careers_url!),
    onSuccess: (_, variables) => { void client.invalidateQueries({ queryKey: ["companies"] }); setMessage(variables.decision === "approve" ? "Career URL сохранён." : "Career URL отклонён."); },
  });
  const selectedCrawl = useMutation({ mutationFn: (ids: string[]) => api.start({ scope: "selected", company_ids: ids }), onSuccess: (result) => setMessage(`Поиск запущен для ${result.total} выбранных компаний.`) });

  function closeImport() { setSelectedFile(null); setResetExisting(false); setDeduplicate(true); importMutation.reset(); if (fileInput.current) fileInput.current.value = ""; }
  function toggleVisible() { setSelectedIds((current) => { const next = new Set(current); if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id)); else visibleIds.forEach((id) => next.add(id)); return next; }); }
  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editCompany) return;
    const data = new FormData(event.currentTarget);
    editMutation.mutate({ id: editCompany.id, values: { name: data.get("name"), website_url: data.get("website_url"), careers_url: data.get("careers_url"), locations: data.get("locations"), type: data.get("type") } });
  }
  useEffect(() => setPage(1), [search, statusFilter]);

  return <div className="mx-auto max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><h1 className="text-2xl font-semibold tracking-tight text-admin-ink">Компании</h1><p className="mt-1 text-sm text-admin-muted">Текущий список компаний, участвующих в поиске вакансий</p></div><button className="inline-flex h-10 items-center justify-center rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white hover:bg-admin-primary-dark" onClick={() => fileInput.current?.click()}>Добавить новые компании</button><input ref={fileInput} className="hidden" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => { setMessage(null); setSelectedFile(event.target.files?.[0] ?? null); }} /></header>
    {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div>}
    {(bulkMutation.isError || selectedCrawl.isError) && <ErrorState message={(bulkMutation.error ?? selectedCrawl.error)?.message ?? "Ошибка"} />}
    <section className="rounded-xl border border-admin-border bg-white p-4"><div className="grid gap-3 md:grid-cols-2"><label className="grid gap-1.5 text-xs font-medium text-admin-muted">Поиск по названию<input className={control} placeholder="Например, Picsart" value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="grid gap-1.5 text-xs font-medium text-admin-muted">Статус<select className={control} value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}><option value="all">Все компании</option><option value="success">Есть вакансии</option><option value="no_jobs">Нет вакансий</option><option value="failed">Ошибки</option><option value="blocked">Заблокировано</option><option value="unprocessed">Не обработано</option><option value="discovery">Нужно проверить Careers URL</option><option value="skipped">Отключено</option></select></label></div></section>
    {selectedIds.size > 0 && <section className="flex flex-wrap items-center gap-2 rounded-xl border border-admin-primary/20 bg-white p-3"><span className="mr-auto text-sm font-medium">Выбрано: {selectedIds.size}</span><button className="pager-button" onClick={() => selectedCrawl.mutate([...selectedIds])}>Искать выбранные</button><button className="pager-button" onClick={() => bulkMutation.mutate({ action: "enable", ids: [...selectedIds] })}>Включить</button><button className="pager-button" onClick={() => bulkMutation.mutate({ action: "disable", ids: [...selectedIds] })}>Отключить</button><button className="h-9 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50" onClick={() => window.confirm(`Удалить ${selectedIds.size} компаний?`) && bulkMutation.mutate({ action: "delete", ids: [...selectedIds] })}>Удалить</button></section>}
    {query.isLoading ? <LoadingState /> : query.isError ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()} /> : <section className="overflow-hidden rounded-xl border border-admin-border bg-white"><div className="flex items-center justify-between border-b border-admin-border px-4 py-3"><h2 className="font-semibold">Список компаний</h2><span className="text-sm text-admin-muted">{companies.length} результатов</span></div><div className="overflow-x-auto"><table className="w-full min-w-[1200px] text-left text-sm"><thead className="border-b border-admin-border bg-admin-soft text-xs font-semibold uppercase text-admin-muted"><tr><th className="px-4 py-3"><input aria-label="Выбрать компании на странице" className="accent-admin-primary" type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} /></th><th className="px-4 py-3">Компания</th><th className="px-4 py-3">Тип</th><th className="px-4 py-3">Локация</th><th className="px-4 py-3">Remote</th><th className="px-4 py-3">Статус</th><th className="px-4 py-3">Вакансии</th><th className="px-4 py-3">Ссылки и действия</th></tr></thead><tbody className="divide-y divide-admin-border">{visible.map((company) => <CompanyRow key={company.id} company={company} selected={selectedIds.has(company.id)} onSelect={() => setSelectedIds((current) => { const next = new Set(current); next.has(company.id) ? next.delete(company.id) : next.add(company.id); return next; })} onEdit={() => setEditCompany(company)} onDecision={(decision) => decisionMutation.mutate({ company, decision })} />)}</tbody></table></div>{!visible.length ? <div className="border-t border-admin-border px-4 py-12 text-center text-admin-muted">Компании не найдены</div> : <footer className="flex items-center justify-between border-t border-admin-border px-4 py-3 text-sm text-admin-muted"><span>Показано {firstVisible + 1}–{firstVisible + visible.length} из {companies.length}</span><div className="flex items-center gap-2"><button className="pager-button" disabled={currentPage === 1} onClick={() => setPage((value) => value - 1)}>Назад</button><span>{currentPage} / {pages}</span><button className="pager-button" disabled={currentPage === pages} onClick={() => setPage((value) => value + 1)}>Далее</button></div></footer>}</section>}
    {selectedFile && <ImportModal file={selectedFile} resetExisting={resetExisting} deduplicate={deduplicate} preview={preview} importing={importMutation.isPending} importError={importMutation.error?.message} onReset={setResetExisting} onDeduplicate={setDeduplicate} onClose={closeImport} onConfirm={() => importMutation.mutate()} />}
    {editCompany && <EditModal company={editCompany} pending={editMutation.isPending} error={editMutation.error?.message} onClose={() => setEditCompany(null)} onSubmit={submitEdit} />}
  </div>;
}

function CompanyRow({ company, selected, onSelect, onEdit, onDecision }: { company: CompanySummary; selected: boolean; onSelect: () => void; onEdit: () => void; onDecision: (decision: "approve" | "reject") => void }) {
  return <tr className="transition hover:bg-admin-soft/70"><td className="px-4 py-3"><input aria-label={`Выбрать ${company.name}`} className="accent-admin-primary" type="checkbox" checked={selected} onChange={onSelect} /></td><td className="px-4 py-3 font-medium">{company.name}{!company.enabled && <span className="ml-2 text-xs text-admin-muted">выключена</span>}</td><td className="px-4 py-3 text-admin-muted">{company.type ?? "—"}</td><td className="max-w-72 px-4 py-3 text-admin-muted">{company.locations ?? "—"}</td><td className="px-4 py-3 text-admin-muted">{company.remote_compatibility ?? "—"}</td><td className="px-4 py-3"><span className="rounded-md bg-admin-primary/8 px-2 py-1 text-xs font-medium text-admin-primary">{company.crawl_status ? statusLabel[company.crawl_status] : "Не обработана"}</span></td><td className="px-4 py-3 font-medium">{company.jobs_found}</td><td className="px-4 py-3"><div className="flex flex-wrap items-center gap-2"><a className="inline-flex items-center gap-1 text-admin-primary hover:underline" href={company.website_url} rel="noreferrer" target="_blank">Сайт <ExternalIcon className="size-4" /></a>{company.careers_url && <a className="inline-flex items-center gap-1 text-admin-primary hover:underline" href={company.careers_url} rel="noreferrer" target="_blank">Careers <ExternalIcon className="size-4" /></a>}<button className="text-admin-primary hover:underline" onClick={onEdit}>Изменить</button>{company.discovery_pending && <><button className="text-emerald-700 hover:underline" onClick={() => onDecision("approve")}>Принять URL</button><button className="text-red-700 hover:underline" onClick={() => onDecision("reject")}>Отклонить</button></>}</div></td></tr>;
}

function ImportModal({ file, resetExisting, deduplicate, preview, importing, importError, onReset, onDeduplicate, onClose, onConfirm }: any) {
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-4" role="dialog" aria-modal="true" aria-labelledby="company-import-title"><div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"><h2 className="text-xl font-semibold" id="company-import-title">Хотите добавить эти компании?</h2><p className="mt-2 break-all text-sm text-admin-muted">Файл: {file.name}</p><div className="mt-5 space-y-3"><CheckOption checked={resetExisting} title="Обнулить данные" description="Заменить рабочий список компаниями из файла." onChange={onReset} /><CheckOption checked={deduplicate} title="Отфильтровать дубликаты" description="Сравнить название и основной сайт." onChange={onDeduplicate} /></div><div className="mt-4 rounded-xl bg-admin-soft p-4">{preview.isLoading ? <p className="text-sm text-admin-muted">Проверяем файл…</p> : preview.isError ? <p className="text-sm text-red-700">{preview.error.message}</p> : preview.data && <div className="grid grid-cols-2 gap-3 text-sm"><Metric label="В файле" value={preview.data.uploaded} /><Metric label="Будет добавлено" value={preview.data.would_add} /><Metric label="Дубликаты" value={preview.data.duplicates_found} /><Metric label="Итого после импорта" value={preview.data.total_after_import} /></div>}</div>{resetExisting && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">Текущий список будет заменён. Backend создаст резервную копию.</p>}{importError && <p className="mt-3 text-sm text-red-700">{importError}</p>}<div className="mt-6 flex justify-end gap-3"><button className="pager-button" disabled={importing} onClick={onClose}>Нет</button><button className="h-10 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white disabled:opacity-60" disabled={importing || preview.isLoading || preview.isError} onClick={onConfirm}>{importing ? "Добавляем…" : "Да"}</button></div></div></div>;
}

function CheckOption({ checked, title, description, onChange }: { checked: boolean; title: string; description: string; onChange: (value: boolean) => void }) { return <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-admin-border p-3 text-sm"><input className="mt-0.5 accent-admin-primary" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span><strong className="block">{title}</strong><span className="text-admin-muted">{description}</span></span></label>; }
function Metric({ label, value }: { label: string; value: number }) { return <div><span className="text-admin-muted">{label}</span><strong className="block text-lg">{value}</strong></div>; }
function EditModal({ company, pending, error, onClose, onSubmit }: { company: CompanySummary; pending: boolean; error?: string; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) { return <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-4" role="dialog" aria-modal="true" aria-labelledby="company-edit-title"><form className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onSubmit={onSubmit}><h2 className="text-xl font-semibold" id="company-edit-title">Изменить компанию</h2><div className="mt-5 grid gap-3"><EditField label="Название" name="name" value={company.name} required /><EditField label="Website" name="website_url" value={company.website_url} required /><EditField label="Careers URL" name="careers_url" value={company.configured_careers_url ?? ""} /><EditField label="Тип" name="type" value={company.type ?? ""} /><EditField label="Локации" name="locations" value={company.locations ?? ""} /></div>{error && <p className="mt-3 text-sm text-red-700">{error}</p>}<div className="mt-6 flex justify-end gap-3"><button className="pager-button" type="button" onClick={onClose}>Отмена</button><button className="h-10 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white" disabled={pending} type="submit">Сохранить</button></div></form></div>; }
function EditField({ label, name, value, required = false }: { label: string; name: string; value: string; required?: boolean }) { return <label className="grid gap-1 text-xs text-admin-muted">{label}<input className={control} name={name} defaultValue={value} required={required} /></label>; }
