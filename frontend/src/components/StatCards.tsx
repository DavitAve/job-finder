import type { CrawlStats } from "../types";

export type ReportTab = "jobs" | "blocked" | "failed";

interface Props {
  stats: CrawlStats;
  activeTab: ReportTab;
  onTabChange: (tab: ReportTab) => void;
}

export function StatCards({ stats, activeTab, onTabChange }: Props) {
  const cards: ReadonlyArray<{ label: string; value: number; tab?: ReportTab }> = [
    { label: "Обработано", value: stats.success + stats.no_jobs },
    { label: "Вакансии", value: stats.jobs_found, tab: "jobs" },
    { label: "Заблокировано", value: stats.blocked, tab: "blocked" },
    { label: "Ошибки", value: stats.failed, tab: "failed" },
  ];
  return (
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Статистика поиска">
      {cards.map((card) => card.tab ? (
        <button
          aria-pressed={activeTab === card.tab}
          className={`rounded-xl border p-4 text-left transition focus:outline-none focus:ring-2 focus:ring-admin-primary/30 ${activeTab === card.tab ? "border-admin-primary bg-admin-primary text-white shadow-sm" : "border-admin-border bg-white hover:border-admin-primary/50 hover:bg-admin-primary/5"}`}
          key={card.label}
          onClick={() => { if (card.tab) onTabChange(card.tab); }}
          type="button"
        >
          <div className={`text-2xl font-semibold ${activeTab === card.tab ? "text-white" : "text-admin-ink"}`}>{card.value}</div>
          <div className={`mt-1 text-sm ${activeTab === card.tab ? "text-white/80" : "text-admin-muted"}`}>{card.label}</div>
        </button>
      ) : (
        <div className="rounded-xl border border-admin-border bg-white p-4" key={card.label}>
          <div className="text-2xl font-semibold text-admin-ink">{card.value}</div>
          <div className="mt-1 text-sm text-admin-muted">{card.label}</div>
        </div>
      ))}
    </section>
  );
}
