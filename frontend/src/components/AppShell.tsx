import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeftIcon, ChevronRightIcon, CloseIcon, CompaniesIcon, CoverageIcon, HistoryIcon, LogoutIcon, MenuIcon, SearchIcon, UserIcon } from "./Icons";
import { api } from "../lib/api";

const navigation = [
  { to: "/", label: "Текущий поиск", icon: SearchIcon, end: true },
  { to: "/companies", label: "Компании", icon: CompaniesIcon },
  { to: "/coverage", label: "Покрытие", icon: CoverageIcon },
  { to: "/history", label: "История", icon: HistoryIcon },
  { to: "/account", label: "Аккаунт", icon: UserIcon },
] as const;

export function AppShell() {
  const client = useQueryClient();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("job-finder-sidebar-collapsed") === "1"; }
    catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me, staleTime: 60_000 });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
      client.setQueryData(["auth"], null);
    },
  });

  useEffect(() => setMobileOpen(false), [location.pathname]);
  useEffect(() => {
    try { localStorage.setItem("job-finder-sidebar-collapsed", collapsed ? "1" : "0"); }
    catch { /* Storage can be unavailable in private browser contexts. */ }
  }, [collapsed]);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && setMobileOpen(false);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileOpen]);

  return (
    <div className="min-h-screen w-full min-w-0 overflow-x-clip bg-admin-bg">
      {mobileOpen && <button aria-label="Закрыть меню" className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[1px] lg:hidden" onClick={() => setMobileOpen(false)} type="button" />}
      <aside
        id="app-sidebar"
        aria-label="Боковая навигация"
        className={`fixed inset-y-0 left-0 z-50 flex h-dvh w-[min(18rem,calc(100vw-3rem))] min-w-0 flex-col overflow-visible bg-admin-sidebar px-4 py-5 text-white shadow-2xl transition-[transform,width,padding] duration-200 lg:z-20 lg:translate-x-0 lg:shadow-none ${mobileOpen ? "translate-x-0" : "-translate-x-full"} ${collapsed ? "lg:w-[76px] lg:px-2" : "lg:w-[230px] lg:px-4 lg:py-6"}`}
      >
        <div className={`flex h-11 items-center ${collapsed ? "lg:justify-center" : "justify-between"}`}>
          <div className={`flex min-w-0 items-center gap-3 ${collapsed ? "lg:gap-0" : ""}`}>
            <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-admin-primary font-bold">JF</div>
            <div className={`min-w-0 ${collapsed ? "lg:hidden" : ""}`}><div className="truncate text-sm font-semibold">Job Finder</div><div className="truncate text-xs text-white/45">Frontend вакансии</div></div>
          </div>
          <button aria-label="Закрыть боковое меню" className="grid size-9 shrink-0 place-items-center rounded-lg text-white/65 hover:bg-white/10 hover:text-white lg:hidden" onClick={() => setMobileOpen(false)} type="button"><CloseIcon className="size-5" /></button>
        </div>
        <nav className="mt-7 flex min-w-0 flex-col gap-2" aria-label="Основная навигация">
          {navigation.map(({ to, label, icon: Icon, ...item }) => (
            <NavLink
              className={({ isActive }) => `flex min-w-0 items-center rounded-lg py-2.5 text-sm font-medium transition ${collapsed ? "gap-3 px-3 lg:justify-center lg:px-0" : "gap-3 px-3"} ${isActive ? "bg-admin-primary text-white" : "text-white/65 hover:bg-white/8 hover:text-white"}`}
              end={"end" in item ? item.end : undefined}
              key={to}
              title={collapsed ? label : undefined}
              to={to}
            >
              <Icon className="size-5 shrink-0" /><span className={`truncate ${collapsed ? "lg:sr-only" : ""}`}>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={`mt-auto border-t border-white/10 pt-4 ${collapsed ? "lg:text-center" : ""}`}>
          <div className={collapsed ? "lg:hidden" : ""}><p className="truncate text-sm font-medium">{auth.data?.display_name}</p><p className="mt-0.5 truncate text-xs text-white/45">{auth.data?.email}</p></div>
          <button aria-label="Выйти из аккаунта" className={`mt-3 inline-flex items-center text-xs font-semibold text-white/65 transition hover:text-white disabled:opacity-50 ${collapsed ? "gap-2 lg:grid lg:size-10 lg:place-items-center" : "gap-2"}`} disabled={logout.isPending} onClick={() => logout.mutate()} title="Выйти из аккаунта" type="button"><LogoutIcon className="size-4 shrink-0" /><span className={collapsed ? "lg:sr-only" : ""}>Выйти из аккаунта</span></button>
        </div>
        <button aria-label={collapsed ? "Развернуть боковое меню" : "Свернуть боковое меню"} aria-pressed={collapsed} className="absolute -right-3.5 top-7 z-10 hidden size-7 place-items-center rounded-full border border-admin-border bg-white text-admin-primary-dark shadow-md transition hover:border-admin-primary hover:bg-admin-primary hover:text-white lg:grid" onClick={() => setCollapsed((value) => !value)} title={collapsed ? "Развернуть меню" : "Свернуть меню"} type="button">{collapsed ? <ChevronRightIcon className="size-4" /> : <ChevronLeftIcon className="size-4" />}</button>
      </aside>
      <div className={`min-w-0 max-w-full transition-[margin-left] duration-200 ${collapsed ? "lg:ml-[76px]" : "lg:ml-[230px]"}`}>
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-black/5 bg-admin-sidebar px-4 text-white shadow-sm lg:hidden">
          <button aria-controls="app-sidebar" aria-expanded={mobileOpen} aria-label="Открыть боковое меню" className="grid size-10 place-items-center rounded-lg text-white/80 hover:bg-white/10 hover:text-white" onClick={() => setMobileOpen(true)} type="button"><MenuIcon className="size-6" /></button>
          <div className="flex items-center gap-2"><div className="grid size-8 place-items-center rounded-lg bg-admin-primary text-sm font-bold">JF</div><span className="text-sm font-semibold">Job Finder</span></div>
          <div className="size-10" aria-hidden />
        </header>
        <main className="min-w-0 max-w-full overflow-x-hidden"><Outlet /></main>
      </div>
    </div>
  );
}
