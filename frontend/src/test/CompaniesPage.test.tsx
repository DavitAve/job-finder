import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { CompaniesPage } from "../pages/CompaniesPage";
import type { CompanyDiagnostics, CompanyHistoryItem, CompanySummary } from "../types";

vi.mock("../lib/api", () => ({ api: {
  companies: vi.fn(), importCompanies: vi.fn(), previewCompanies: vi.fn(),
  updateCompany: vi.fn(), bulkCompanies: vi.fn(), decideCareers: vi.fn(), start: vi.fn(), active: vi.fn(), companyDiagnostics: vi.fn(), companyHistory: vi.fn(),
} }));

const companies: CompanySummary[] = [
  {
    id: "acme",
    name: "Acme",
    website_url: "https://acme.example/",
    careers_url: "https://acme.example/jobs",
    configured_careers_url: "https://acme.example/old-jobs",
    resolved_careers_url: "https://acme.example/jobs",
    careers_url_discovered: true,
    discovery_pending: true,
    type: "SaaS",
    locations: "Armenia / Europe",
    remote_compatibility: "HIGH",
    frontend_compatibility: "HIGH",
    adapter: "auto",
    last_adapter: "greenhouse",
    enabled: true,
    crawl_status: "success",
    jobs_found: 3,
    last_crawled_at: "2026-08-27T10:00:00Z",
    refresh_due: false,
  },
  {
    id: "other",
    name: "Other Company",
    website_url: "https://other.example/",
    careers_url: null,
    configured_careers_url: null,
    resolved_careers_url: null,
    careers_url_discovered: false,
    discovery_pending: false,
    type: null,
    locations: "USA",
    remote_compatibility: null,
    frontend_compatibility: null,
    adapter: "auto",
    last_adapter: "html",
    enabled: true,
    crawl_status: "no_jobs",
    jobs_found: 0,
    last_crawled_at: "2026-08-25T10:00:00Z",
    refresh_due: true,
  },
];

describe("CompaniesPage", () => {
  it("filters companies by name and renders website and careers links", async () => {
    vi.mocked(api.companies).mockResolvedValue(companies);
    vi.mocked(api.previewCompanies).mockResolvedValue({
      uploaded: 2,
      would_add: 1,
      duplicates_found: 1,
      current_total: 2,
      total_after_import: 3,
      replaced_existing: false,
      validation_errors: [],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><CompaniesPage /></QueryClientProvider>);

    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Сайт/ })[0]).toHaveAttribute("href", "https://acme.example/");
    expect(screen.getByRole("link", { name: /Careers/ })).toHaveAttribute("href", "https://acme.example/jobs");

    await user.type(screen.getByLabelText("Поиск по названию"), "other");
    expect(screen.queryByText("Acme")).not.toBeInTheDocument();
    const otherRow = screen.getByText("Other Company").closest("tr");
    expect(otherRow).not.toBeNull();
    expect(within(otherRow!).getByText("Пора обновить")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Поиск по названию"));
    await user.selectOptions(screen.getByLabelText("Статус"), "refresh_due");
    expect(screen.queryByText("Acme")).not.toBeInTheDocument();
    expect(screen.getByText("Other Company")).toBeInTheDocument();
  });

  it("confirms XLSX import with safe default options", async () => {
    vi.mocked(api.companies).mockResolvedValue(companies);
    vi.mocked(api.previewCompanies).mockResolvedValue({
      uploaded: 2, would_add: 1, duplicates_found: 1, current_total: 2,
      total_after_import: 3, replaced_existing: false, validation_errors: [],
    });
    vi.mocked(api.importCompanies).mockResolvedValue({
      uploaded: 2,
      added: 1,
      duplicates_skipped: 1,
      total: 3,
      replaced_existing: false,
      backup_file: "backup.json",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    const { container } = render(<QueryClientProvider client={client}><CompaniesPage /></QueryClientProvider>);
    await screen.findByText("Acme");

    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(["xlsx"], "new-companies.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    await user.upload(input!, file);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Обнулить данные/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Отфильтровать дубликаты/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Да" }));

    await waitFor(() => expect(api.importCompanies).toHaveBeenCalledWith(file, {
      resetExisting: false,
      deduplicate: true,
    }));
    expect(await screen.findByText(/Добавлено: 1/)).toBeInTheDocument();
  });

  it("manages a company source, diagnostics and a single-company retry", async () => {
    const initialDiagnostics: CompanyDiagnostics = {
      company_id: "acme",
      company: "Acme",
      configured_adapter: "auto",
      latest_result: {
        company_id: "acme",
        company: "Acme",
        status: "success",
        adapter: "greenhouse",
        candidates_found: 5,
        matching_jobs: 3,
        duration_ms: 1200,
        last_crawled_at: "2026-08-27T10:00:00Z",
        resolved_careers_url: "https://acme.example/jobs",
        error: null,
        warnings: ["Used discovered careers URL"],
      },
      request_url: "https://acme.example/old-jobs",
      response_url: "https://acme.example/jobs",
      response_status: 200,
      response_headers: { "content-type": "text/html" },
      raw_preview: "<html>raw careers response</html>",
      raw_truncated: false,
      fetch_error: null,
    };
    const updatedCompanies: CompanySummary[] = [
      { ...companies[0], careers_url: "https://acme.example/careers-v2", resolved_careers_url: "https://acme.example/careers-v2", crawl_status: "no_jobs", jobs_found: 0, last_adapter: "html" },
      companies[1],
    ];
    const updatedDiagnostics: CompanyDiagnostics = {
      ...initialDiagnostics,
      latest_result: {
        ...initialDiagnostics.latest_result!,
        status: "no_jobs" as const,
        adapter: "html",
        candidates_found: 0,
        matching_jobs: 0,
        duration_ms: 800,
        resolved_careers_url: "https://acme.example/careers-v2",
        warnings: ["Careers URL changed after redirect"],
      },
      request_url: "https://acme.example/careers-v2",
      response_url: "https://acme.example/careers-v2",
      raw_preview: "<html>updated raw response</html>",
    };
    const initialHistory: CompanyHistoryItem[] = [{
      run_id: "old-run",
      checked_at: "2026-08-27T10:00:00Z",
      status: "success",
      careers_url: "https://acme.example/jobs",
      adapter: "greenhouse",
      jobs_found: 3,
      error: null,
      duration_ms: 1200,
    }];
    const updatedHistory: CompanyHistoryItem[] = [{
      run_id: "single-run",
      checked_at: "2026-08-28T10:00:00Z",
      status: "no_jobs",
      careers_url: "https://acme.example/careers-v2",
      adapter: "html",
      jobs_found: 0,
      error: "Temporary parser warning",
      duration_ms: 800,
    }, ...initialHistory];
    vi.mocked(api.companies).mockResolvedValueOnce(companies).mockResolvedValue(updatedCompanies);
    vi.mocked(api.companyDiagnostics).mockResolvedValueOnce(initialDiagnostics).mockResolvedValue(updatedDiagnostics);
    vi.mocked(api.companyHistory).mockResolvedValueOnce(initialHistory).mockResolvedValue(updatedHistory);
    vi.mocked(api.start).mockResolvedValue({ run_id: "single-run", state: "running", processed: 0, total: 1, jobs_found: 0 });
    vi.mocked(api.active).mockResolvedValue({ run_id: "single-run", state: "completed", processed: 1, total: 1, jobs_found: 0 });
    vi.mocked(api.decideCareers).mockResolvedValue({ changed: 1, total: 2, backup_file: "backup.json" });
    vi.mocked(api.updateCompany).mockResolvedValue({ changed: 1, total: 2, backup_file: "backup.json" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const user = userEvent.setup();
    render(<QueryClientProvider client={client}><CompaniesPage /></QueryClientProvider>);

    const acmeRow = (await screen.findByText("Acme")).closest("tr")!;
    await user.click(within(acmeRow).getByRole("button", { name: "Источник" }));
    expect(await screen.findByText("<html>raw careers response</html>")).toBeInTheDocument();
    expect(screen.getByText("Used discovered careers URL")).toBeInTheDocument();
    const historyTable = screen.getByRole("table", { name: "История проверок компании" });
    expect(historyTable).toHaveTextContent("greenhouse");
    expect(historyTable).toHaveTextContent("3");
    expect(screen.getByRole("combobox", { name: "Адаптер" })).toHaveValue("auto");

    await user.click(screen.getByRole("button", { name: /Повторно проверить/ }));
    await waitFor(() => expect(api.start).toHaveBeenCalledWith({ scope: "selected", company_ids: ["acme"] }));
    expect(await screen.findByText("Повторная проверка завершена")).toBeInTheDocument();
    expect(screen.getByText("Careers URL изменился")).toBeInTheDocument();
    const comparison = screen.getByRole("table", { name: "Сравнение результатов повторной проверки" });
    expect(comparison).toHaveTextContent("Есть вакансии");
    expect(comparison).toHaveTextContent("Нет вакансий");
    expect(comparison).toHaveTextContent("greenhouse");
    expect(comparison).toHaveTextContent("html");
    expect(await screen.findByText("Careers URL changed after redirect")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "История проверок компании" })).toHaveTextContent("Temporary parser warning");

    await user.click(await screen.findByRole("button", { name: "Подтвердить URL" }));
    await waitFor(() => expect(api.decideCareers).toHaveBeenCalledWith("acme", "approve", "https://acme.example/careers-v2"));

    await user.click(within(acmeRow).getByRole("button", { name: "Источник" }));
    await user.selectOptions(await screen.findByRole("combobox", { name: "Адаптер" }), "browser");
    await user.click(screen.getByRole("button", { name: "Сохранить источник" }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledWith("acme", {
      careers_url: "https://acme.example/old-jobs",
      adapter: "browser",
    }));
  });
});
