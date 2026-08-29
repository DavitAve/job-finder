import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CurrentPage } from "../pages/CurrentPage";
import { api } from "../lib/api";
import type { ActiveRun, CrawlReport } from "../types";
import { ToastProvider } from "../components/Toast";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } },
  api: { companies: vi.fn(), latest: vi.fn(), active: vi.fn(), start: vi.fn(), stop: vi.fn(), history: vi.fn(), report: vi.fn(), jobChanges: vi.fn(), resumeMatches: vi.fn() },
}));

const stats = { total_companies: 3, success: 2, no_jobs: 1, blocked: 0, failed: 0, skipped: 0, jobs_found: 0, duplicates_removed: 0 };
const report: CrawlReport = { schema_version: "1.0", run_id: "run-1", started_at: "2026-08-14T10:00:00Z", finished_at: "2026-08-14T10:01:00Z", stats, errors: [], jobs: [] };
const idle: ActiveRun = { run_id: null, state: "idle", processed: 0, total: 0, jobs_found: 0 };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter><CurrentPage /></MemoryRouter></ToastProvider></QueryClientProvider>);
}

describe("CurrentPage states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.companies).mockResolvedValue([]);
    vi.mocked(api.jobChanges).mockResolvedValue({ new_jobs: [], closed_jobs: [] });
    vi.mocked(api.resumeMatches).mockResolvedValue({ active_resume_id: null, matches: [] });
  });

  it("shows the current company count as a link to the companies page", async () => {
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValue(idle);
    vi.mocked(api.companies).mockResolvedValue(Array.from({ length: 626 }, (_, index) => ({
      id: `company-${index}`,
      name: `Company ${index}`,
      website_url: `https://company-${index}.example/`,
      careers_url: null,
      configured_careers_url: null,
      resolved_careers_url: null,
      careers_url_discovered: false,
      discovery_pending: false,
      type: null,
      locations: null,
      remote_compatibility: null,
      frontend_compatibility: null,
      adapter: "auto" as const,
      last_adapter: null,
      enabled: true,
      crawl_status: null,
      jobs_found: 0,
    })));
    renderPage();
    const link = await screen.findByRole("link", { name: "Открыть список компаний" });
    expect(link).toHaveAttribute("href", "/companies");
    await waitFor(() => expect(link).toHaveTextContent("626"));
  });

  it("shows loading while the latest report is pending", () => {
    vi.mocked(api.latest).mockReturnValue(new Promise(() => {}));
    vi.mocked(api.active).mockResolvedValue(idle);
    renderPage();
    expect(screen.getByText("Загрузка данных…")).toBeInTheDocument();
  });

  it("shows the empty table for a completed run with no jobs", async () => {
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValue({ ...idle, state: "completed", run_id: "run-1" });
    renderPage();
    expect(await screen.findByText("Вакансии не найдены")).toBeInTheDocument();
    expect(screen.getByText("00:01:00")).toBeInTheDocument();
  });

  it("shows background crawl progress and found vacancies", async () => {
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValue({ run_id: "run-2", state: "running", started_at: new Date().toISOString(), processed: 6, total: 8, jobs_found: 4, success: 1, no_jobs: 0, blocked: 2, failed: 3, skipped: 0 });
    renderPage();
    expect(await screen.findByText("6 из 8 · 4 вакансий")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Идёт поиск/ })).toBeDisabled();
    expect(screen.getByLabelText("Загрузка таблицы")).toBeInTheDocument();
    expect(Array.from(screen.getByLabelText("Статистика поиска").children).map((card) => card.textContent)).toEqual([
      "1Обработано",
      "4Вакансии",
      "0Нет вакансий",
      "0Не извлечено",
      "0Страница не найдена",
      "2Заблокировано",
      "3Ошибки",
    ]);
  });

  it("asks for confirmation before stopping a crawl", async () => {
    const user = userEvent.setup();
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValue({ run_id: "run-2", state: "running", started_at: new Date().toISOString(), processed: 6, total: 8, jobs_found: 4 });
    vi.mocked(api.stop).mockResolvedValue({ run_id: "run-2", state: "cancelled", processed: 6, total: 8, jobs_found: 4 });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Остановить поиск" }));
    expect(screen.getByRole("dialog", { name: "Остановить поиск?" })).toBeInTheDocument();
    expect(api.stop).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Да, остановить" }));
    await waitFor(() => expect(api.stop).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows an informational message when there are no new companies", async () => {
    const user = userEvent.setup();
    const noNewCompanies: ActiveRun = {
      run_id: null,
      state: "completed",
      processed: 0,
      total: 0,
      jobs_found: 0,
      scope: "new",
      message: "No new companies were found. All companies have already been processed.",
    };
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValueOnce(idle).mockResolvedValue(noNewCompanies);
    vi.mocked(api.start).mockResolvedValue(noNewCompanies);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Обработать новые компании" }));

    expect(await screen.findByText("Новых компаний нет — все компании уже были обработаны.")).toBeInTheDocument();
    expect(vi.mocked(api.start).mock.calls[0]?.[0]).toEqual({ scope: "new" });
  });

  it("refreshes only companies that are due", async () => {
    const user = userEvent.setup();
    const nothingDue: ActiveRun = {
      run_id: null,
      state: "completed",
      processed: 0,
      total: 0,
      jobs_found: 0,
      scope: "stale",
      message: "No companies are due for refresh.",
    };
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValueOnce(idle).mockResolvedValue(nothingDue);
    vi.mocked(api.start).mockResolvedValue(nothingDue);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Обновить вакансии (0)" }));

    expect(await screen.findByText("Обновление не требуется — все компании проверялись в течение последних 24 часов.")).toBeInTheDocument();
    expect(vi.mocked(api.start).mock.calls[0]?.[0]).toEqual({ scope: "stale" });
  });

  it("keeps the previous report visible when the background crawl fails", async () => {
    vi.mocked(api.latest).mockResolvedValue(report);
    vi.mocked(api.active).mockResolvedValue({ run_id: "run-2", state: "failed", processed: 1, total: 3, jobs_found: 0, error: "Сеть недоступна" });
    renderPage();
    expect(await screen.findByText("Сеть недоступна")).toBeInTheDocument();
    expect(await screen.findByText("Вакансии не найдены")).toBeInTheDocument();
  });

  it("shows an API error with retry", async () => {
    vi.mocked(api.latest).mockRejectedValue(new Error("API offline"));
    vi.mocked(api.active).mockResolvedValue(idle);
    renderPage();
    await waitFor(() => expect(screen.getByText("API offline")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});
