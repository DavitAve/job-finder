export function LoadingState() { return <div className="grid min-h-64 place-items-center"><div className="flex items-center gap-3 text-sm text-admin-muted"><span className="size-5 animate-spin rounded-full border-2 border-admin-primary/20 border-t-admin-primary" />Загрузка данных…</div></div>; }

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-8 text-center"><p className="font-medium text-red-800">Не удалось загрузить данные</p><p className="mt-1 text-sm text-red-600">{message}</p>{onRetry && <button className="mt-4 rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white" onClick={onRetry}>Повторить</button>}</div>;
}
