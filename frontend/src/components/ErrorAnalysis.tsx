import { ERROR_CATEGORIES, classifyIssue, type ErrorCategory } from "../lib/issues";
import type { CompanyCrawlResult, CrawlError } from "../types";

interface Props {
  issues: CompanyCrawlResult[];
  errors: CrawlError[];
  selected: ErrorCategory | "all";
  onChange: (category: ErrorCategory | "all") => void;
}

export function ErrorAnalysis({ issues, errors, selected, onChange }: Props) {
  const counts = new Map<ErrorCategory, number>();
  for (const issue of issues) {
    const category = classifyIssue(issue, errors);
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }

  return (
    <section className="rounded-xl border border-admin-border bg-white p-4" aria-label="Анализ причин ошибок">
      <div className="mb-3">
        <h3 className="font-semibold text-admin-ink">Причины проблем</h3>
        <p className="mt-1 text-sm text-admin-muted">Выберите категорию, чтобы отфильтровать таблицу.</p>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <CategoryButton active={selected === "all"} count={issues.length} label="Все причины" onClick={() => onChange("all")} />
        {ERROR_CATEGORIES.map((category) => (
          <CategoryButton
            active={selected === category.id}
            count={counts.get(category.id) ?? 0}
            key={category.id}
            label={category.label}
            onClick={() => onChange(category.id)}
          />
        ))}
      </div>
    </section>
  );
}

function CategoryButton({ active, count, label, onClick }: { active: boolean; count: number; label: string; onClick: () => void }) {
  return (
    <button
      aria-pressed={active}
      className={`rounded-lg border px-3 py-2 text-left transition ${active ? "border-admin-primary bg-admin-primary text-white" : "border-admin-border bg-admin-soft/50 hover:border-admin-primary/50"}`}
      onClick={onClick}
      type="button"
    >
      <span className={`block text-lg font-semibold tabular-nums ${active ? "text-white" : "text-admin-ink"}`}>{count}</span>
      <span className={`block text-xs ${active ? "text-white/80" : "text-admin-muted"}`}>{label}</span>
    </button>
  );
}
