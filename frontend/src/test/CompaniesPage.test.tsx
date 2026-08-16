import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { CompaniesPage } from "../pages/CompaniesPage";
import type { CompanySummary } from "../types";

vi.mock("../lib/api", () => ({ api: {
  companies: vi.fn(), importCompanies: vi.fn(), previewCompanies: vi.fn(),
  updateCompany: vi.fn(), bulkCompanies: vi.fn(), decideCareers: vi.fn(), start: vi.fn(),
} }));

const companies: CompanySummary[] = [
  {
    id: "acme",
    name: "Acme",
    website_url: "https://acme.example/",
    careers_url: "https://acme.example/jobs",
    configured_careers_url: "https://acme.example/jobs",
    resolved_careers_url: "https://acme.example/jobs",
    careers_url_discovered: true,
    discovery_pending: false,
    type: "SaaS",
    locations: "Armenia / Europe",
    remote_compatibility: "HIGH",
    frontend_compatibility: "HIGH",
    enabled: true,
    crawl_status: "success",
    jobs_found: 3,
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
    enabled: true,
    crawl_status: "no_jobs",
    jobs_found: 0,
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
});
