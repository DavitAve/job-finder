import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { CurrentPage } from "./pages/CurrentPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { HistoryPage } from "./pages/HistoryPage";
import { AccountPage } from "./pages/AccountPage";
import { CoveragePage } from "./pages/CoveragePage";
import { AuthPage } from "./pages/AuthPage";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./lib/api";
import type { AuthUser } from "./types";

const router = createBrowserRouter([
  { path: "/", element: <AppShell />, children: [
    { index: true, element: <CurrentPage /> },
    { path: "companies", element: <CompaniesPage /> },
    { path: "coverage", element: <CoveragePage /> },
    { path: "history", element: <HistoryPage /> },
    { path: "history/:runId", element: <HistoryPage /> },
    { path: "account", element: <AccountPage /> },
  ] },
]);

export function App() {
  const client = useQueryClient();
  const auth = useQuery<AuthUser | null>({
    queryKey: ["auth"],
    queryFn: api.me,
    retry: false,
    staleTime: 60_000,
  });
  if (auth.isPending) return <AuthLoading />;
  if (auth.data) return <RouterProvider router={router} />;
  if (auth.error && (!(auth.error instanceof ApiError) || auth.error.status !== 401)) {
    return <AuthUnavailable error={auth.error.message} onRetry={() => void auth.refetch()} />;
  }
  return <AuthPage onAuthenticated={(user) => client.setQueryData(["auth"], user)} />;
}

function AuthLoading() {
  return <main className="grid min-h-screen place-items-center bg-admin-bg"><div className="text-center"><div className="mx-auto grid size-12 place-items-center rounded-xl bg-admin-primary font-bold text-white">JF</div><p className="mt-3 text-sm text-admin-muted">Проверяем сессию…</p></div></main>;
}

function AuthUnavailable({ error, onRetry }: { error: string; onRetry: () => void }) {
  return <main className="grid min-h-screen place-items-center bg-admin-bg px-4"><div className="max-w-md rounded-2xl border border-admin-border bg-white p-7 text-center"><h1 className="text-xl font-semibold text-admin-ink">Backend недоступен</h1><p className="mt-2 text-sm text-admin-muted">{error}</p><button className="mt-5 rounded-xl bg-admin-primary px-4 py-2.5 text-sm font-semibold text-white" onClick={onRetry} type="button">Повторить</button></div></main>;
}
