import type { JobFilters as Filters } from "../lib/jobs";
import { MultiSelect } from "./MultiSelect";

interface Props {
  filters: Filters;
  stacks: string[];
  companies: string[];
  onChange: (filters: Filters) => void;
  resumeAvailable?: boolean;
}

const control = "h-10 rounded-lg border border-admin-border bg-white px-3 text-sm text-admin-ink outline-none transition focus:border-admin-primary focus:ring-2 focus:ring-admin-primary/15";

export function JobFilters({ companies, filters, stacks, onChange, resumeAvailable = false }: Props) {
  const toggleStack = (stack: string) => onChange({
    ...filters,
    stacks: filters.stacks.includes(stack) ? filters.stacks.filter((item) => item !== stack) : [...filters.stacks, stack],
  });
  const toggleCompany = (company: string) => onChange({
    ...filters,
    excludedCompanies: filters.excludedCompanies.includes(company) ? filters.excludedCompanies.filter((item) => item !== company) : [...filters.excludedCompanies, company],
  });
  const hasFilters = Boolean(filters.title || filters.stacks.length || filters.excludedCompanies.length || filters.location !== "all" || filters.format !== "all" || filters.onlyNew || filters.resumeMatch);
  return (
    <section className="rounded-xl border border-admin-border bg-white p-4" aria-label="Фильтры вакансий">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
        Тайтл
        <input className={control} placeholder="Например, React Developer" value={filters.title} onChange={(e) => onChange({ ...filters, title: e.target.value })} />
      </label>
      <MultiSelect label="Стек" options={stacks} selected={filters.stacks} emptyLabel="Любой стек" selectedLabel={(count) => `Выбрано: ${count}`} onToggle={toggleStack} controlClassName={control} />
      <MultiSelect label="Исключить компании" options={companies} selected={filters.excludedCompanies} emptyLabel="Не исключать" selectedLabel={(count) => `Исключено: ${count}`} onToggle={toggleCompany} controlClassName={control} />
      <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
        Локация
        <select className={control} value={filters.location} onChange={(e) => onChange({ ...filters, location: e.target.value as Filters["location"] })}>
          <option value="all">Все локации</option>
          <option value="armenia">Армения</option>
        </select>
      </label>
      <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
        Формат
        <select className={control} value={filters.format} onChange={(e) => onChange({ ...filters, format: e.target.value as Filters["format"] })}>
          <option value="all">Любой формат</option>
          <option value="remote">Удалённо</option>
          <option value="hybrid">Гибрид</option>
          <option value="onsite">В офисе</option>
          <option value="unknown">Не указан</option>
        </select>
      </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-5"><label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-admin-ink">
          <input className="accent-admin-primary" type="checkbox" checked={Boolean(filters.onlyNew)} onChange={(event) => onChange({ ...filters, onlyNew: event.target.checked })} />
          Только новые вакансии
        </label><label className={`flex items-center gap-2 text-sm font-medium ${resumeAvailable ? "cursor-pointer text-admin-ink" : "cursor-not-allowed text-admin-muted"}`} title={resumeAvailable ? "Показать вакансии с совпадением от 35% и отсортировать по оценке" : "Добавьте и активируйте резюме в аккаунте"}>
          <input className="accent-admin-primary" type="checkbox" disabled={!resumeAvailable} checked={Boolean(filters.resumeMatch)} onChange={(event) => onChange({ ...filters, resumeMatch: event.target.checked })} />
          Матч с активным резюме
        </label></div>
        <button className="text-sm font-medium text-admin-primary transition hover:text-admin-primary-dark disabled:cursor-default disabled:opacity-40" disabled={!hasFilters} onClick={() => onChange({ title: "", stacks: [], excludedCompanies: [], location: "all", format: "all", onlyNew: false, resumeMatch: false })}>Сбросить фильтры</button>
      </div>
    </section>
  );
}
