import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CurrentPage } from "../pages/CurrentPage";
import { api } from "../lib/api";
import type { ActiveRun, CrawlReport } from "../types";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } },
  api: { companies: vi.fn(), latest: vi.fn(), active: vi.fn(), start: vi.fn(), history: vi.fn(), report: vi.fn(), jobChanges: vi.fn(), resumeMatches: vi.fn() },
}));

const stats = { total_companies: 3, success: 2, no_jobs: 1, blocked: 0, failed: 0, skipped: 0, jobs_found: 0, duplicates_removed: 0 };
const report: CrawlReport = { schema_version: "1.0", run_id: "run-1", started_at: "2026-08-14T10:00:00Z", finished_at: "2026-08-14T10:01:00Z", stats, errors: [], jobs: [] };
const idle: ActiveRun = { run_id: null, state: "idle", processed: 0, total: 0, jobs_found: 0 };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><CurrentPage /></MemoryRouter></QueryClientProvider>);
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
      "2Заблокировано",
      "3Ошибки",
    ]);
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
