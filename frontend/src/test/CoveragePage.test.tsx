import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CoveragePage } from "../pages/CoveragePage";
import { api } from "../lib/api";
import type { CompanySummary, CrawlReport, RunSummary } from "../types";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } },
  api: { companies: vi.fn(), latest: vi.fn(), history: vi.fn() },
}));

const baseCompany: CompanySummary = {
  id: "company",
  name: "Company",
  website_url: "https://example.com",
  careers_url: null,
  configured_careers_url: null,
  resolved_careers_url: null,
  careers_url_discovered: false,
  discovery_pending: false,
  type: null,
  locations: null,
  remote_compatibility: null,
  frontend_compatibility: null,
  adapter: "auto",
  last_adapter: null,
  enabled: true,
  crawl_status: null,
  jobs_found: 0,
};

const stats = { total_companies: 3, success: 1, no_jobs: 1, blocked: 0, failed: 1, unverified: 0, skipped: 0, jobs_found: 2, duplicates_removed: 0 };

describe("CoveragePage", () => {
  it("shows coverage, adapters, trend and stale companies", async () => {
    const recent = new Date().toISOString();
    const old = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();
    const companies: CompanySummary[] = [
      { ...baseCompany, id: "one", name: "Green Co", careers_url: "https://one.example/jobs", crawl_status: "success", jobs_found: 2, last_crawled_at: recent },
      { ...baseCompany, id: "two", name: "Old Co", website_url: "https://old.example", resolved_careers_url: "https://old.example/careers", crawl_status: "no_jobs", last_crawled_at: old },
      { ...baseCompany, id: "three", name: "Never Co", website_url: "https://never.example", crawl_status: "failed", last_crawled_at: null },
    ];
    const latest: CrawlReport = {
      schema_version: "2.0",
      run_id: "latest",
      started_at: recent,
      finished_at: recent,
      stats,
      errors: [],
      jobs: [],
      companies: [
        { company_id: "one", company: "Green Co", status: "success", adapter: "greenhouse", candidates_found: 3, matching_jobs: 2, duration_ms: 10, error: null, warnings: [] },
        { company_id: "two", company: "Old Co", status: "no_jobs", adapter: "html", candidates_found: 0, matching_jobs: 0, duration_ms: 10, error: null, warnings: [] },
        { company_id: "three", company: "Never Co", status: "failed", adapter: null, candidates_found: 0, matching_jobs: 0, duration_ms: 10, error: "timeout", warnings: [] },
      ],
    };
    const history: RunSummary[] = [{ run_id: "previous", started_at: old, finished_at: old, stats: { ...stats, success: 0, blocked: 1, failed: 2 } }];
    vi.mocked(api.companies).mockResolvedValue(companies);
    vi.mocked(api.latest).mockResolvedValue(latest);
    vi.mocked(api.history).mockResolvedValue(history);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={client}><MemoryRouter><CoveragePage /></MemoryRouter></QueryClientProvider>);

    expect(await screen.findByRole("heading", { name: "Покрытие" })).toBeInTheDocument();
    const metrics = screen.getByLabelText("Основные показатели покрытия");
    expect(metrics).toHaveTextContent("Успешно проверено267%");
    expect(metrics).toHaveTextContent("Career URL известен67%");
    expect(screen.getByText("Greenhouse")).toBeInTheDocument();
    expect(screen.getByText("HTML")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Статусы запуска/)).toHaveLength(2);

    const staleTable = screen.getByRole("table", { name: "Компании, давно не проверявшиеся" });
    expect(within(staleTable).getByText("Old Co")).toBeInTheDocument();
    expect(within(staleTable).getByText("Never Co")).toBeInTheDocument();
    expect(within(staleTable).queryByText("Green Co")).not.toBeInTheDocument();
  });
});
