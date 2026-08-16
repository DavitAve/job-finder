import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { HistoryPage } from "../pages/HistoryPage";
import type { CrawlReport, RunSummary } from "../types";

vi.mock("../lib/api", () => ({ api: { history: vi.fn(), report: vi.fn(), resumeMatches: vi.fn() } }));

const stats = { total_companies: 173, success: 120, no_jobs: 20, blocked: 3, failed: 2, skipped: 0, jobs_found: 8, duplicates_removed: 1 };
const runs: RunSummary[] = Array.from({ length: 4 }, (_, index) => ({ run_id: `run-${index}`, started_at: `2026-08-1${index}T10:00:00Z`, finished_at: `2026-08-1${index}T10:01:00Z`, stats }));
const report: CrawlReport = { ...runs[0], schema_version: "1.0", errors: [], jobs: [] };

describe("HistoryPage", () => {
  it("renders no more than three run cards with status statistics", async () => {
    vi.mocked(api.history).mockResolvedValue(runs);
    vi.mocked(api.report).mockResolvedValue(report);
    vi.mocked(api.resumeMatches).mockResolvedValue({ active_resume_id: null, matches: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/history/run-0"]}><Routes><Route path="/history/:runId" element={<HistoryPage />} /></Routes></MemoryRouter></QueryClientProvider>);
    expect(await screen.findAllByText("8 вакансий")).toHaveLength(3);
    expect(screen.getAllByText(/Успешно: 120/)).toHaveLength(3);
    expect(screen.queryByText("Поиск 4")).not.toBeInTheDocument();
  });
});
