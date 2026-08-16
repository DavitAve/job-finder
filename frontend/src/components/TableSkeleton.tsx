export function TableSkeleton() {
  return (
    <section className="overflow-hidden rounded-xl border border-admin-border bg-white" aria-label="Загрузка таблицы" aria-live="polite">
      <div className="border-b border-admin-border bg-admin-soft px-4 py-3">
        <div className="h-3 w-2/3 animate-pulse rounded bg-admin-border/80" />
      </div>
      <div className="divide-y divide-admin-border">
        {Array.from({ length: 8 }, (_, row) => (
          <div className="grid grid-cols-[1.1fr_2fr_1fr_1.2fr_1fr] gap-5 px-4 py-4" key={row}>
            {Array.from({ length: 5 }, (_, column) => (
              <div
                className="h-4 animate-pulse rounded bg-admin-border/65"
                key={column}
                style={{ width: `${70 + ((row + column) % 3) * 12}%` }}
              />
            ))}
          </div>
        ))}
      </div>
      <span className="sr-only">Поиск вакансий выполняется</span>
    </section>
  );
}
