import { NavLink, Outlet } from "react-router-dom";
import { CompaniesIcon, HistoryIcon, SearchIcon, UserIcon } from "./Icons";

const linkClass = ({ isActive }: { isActive: boolean }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${isActive ? "bg-admin-primary text-white" : "text-white/65 hover:bg-white/8 hover:text-white"}`;

export function AppShell() {
  return (
    <div className="min-h-screen bg-admin-bg lg:grid lg:grid-cols-[230px_1fr]">
      <aside className="bg-admin-sidebar px-4 py-4 text-white lg:sticky lg:top-0 lg:h-screen lg:px-4 lg:py-6">
        <div className="flex items-center gap-3 px-2"><div className="grid size-9 place-items-center rounded-lg bg-admin-primary font-bold">JF</div><div><div className="text-sm font-semibold">Job Finder</div><div className="text-xs text-white/45">Frontend вакансии</div></div></div>
        <nav className="mt-5 flex gap-2 lg:mt-8 lg:flex-col" aria-label="Основная навигация">
          <NavLink className={linkClass} to="/" end><SearchIcon className="size-5" />Текущий поиск</NavLink>
          <NavLink className={linkClass} to="/companies"><CompaniesIcon className="size-5" />Компании</NavLink>
          <NavLink className={linkClass} to="/history"><HistoryIcon className="size-5" />История</NavLink>
          <NavLink className={linkClass} to="/account"><UserIcon className="size-5" />Аккаунт</NavLink>
        </nav>
      </aside>
      <main className="min-w-0"><Outlet /></main>
    </div>
  );
}
