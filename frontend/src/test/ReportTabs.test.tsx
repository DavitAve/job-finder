import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ReportView } from "../components/ReportView";
import type { CrawlReport } from "../types";

const report: CrawlReport = {
  schema_version: "2.0",
  run_id: "run-tabs",
  started_at: "2026-08-14T10:00:00Z",
  finished_at: "2026-08-14T10:01:00Z",
  stats: {
    total_companies: 4,
    success: 1,
    no_jobs: 1,
    blocked: 1,
    failed: 1,
    skipped: 0,
    jobs_found: 1,
    duplicates_removed: 0,
  },
  companies: [
    {
      company_id: "blocked-company",
      company: "Blocked Company",
      careers_url: "https://blocked.example/jobs",
      status: "blocked",
      adapter: "html",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 1200,
      error: "Blocked by robots.txt",
      warnings: ["robots.txt disallows this URL"],
    },
    {
      company_id: "failed-company",
      company: "Failed Company",
      careers_url: "https://failed.example/jobs",
      status: "failed",
      adapter: "browser",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 30000,
      error: "Browser timeout",
      warnings: [],
    },
  ],
  errors: [
    { company_id: "blocked-company", company: "Blocked Company", status: "blocked", message: "Blocked by robots.txt" },
    { company_id: "failed-company", company: "Failed Company", status: "failed", message: "Browser timeout" },
  ],
  jobs: [],
};

describe("Report status tabs", () => {
  it("reorders cards, highlights the active tab and expands issue details", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report} />);

    const cards = screen.getByLabelText("Статистика поиска");
    expect(Array.from(cards.children).map((card) => card.textContent)).toEqual([
      "2Обработано",
      "1Вакансии",
      "1Заблокировано",
      "1Ошибки",
    ]);
    expect(screen.queryByRole("button", { name: /Обработано/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Вакансии/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Заблокировано/ }));
    expect(screen.getByRole("button", { name: /Заблокировано/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("Фильтры вакансий")).not.toBeInTheDocument();
    expect(screen.getByText("Заблокированные компании")).toBeInTheDocument();
    const blockedRowButton = screen.getByRole("button", { name: "Blocked Company" });
    expect(blockedRowButton).toHaveAttribute("aria-expanded", "false");

    await user.click(blockedRowButton);
    expect(blockedRowButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Blocked by robots.txt")).toBeInTheDocument();
    expect(screen.getByText("robots.txt disallows this URL")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Ошибки/ }));
    expect(screen.getByText("Компании с ошибками")).toBeInTheDocument();
    const failedRowButton = screen.getByRole("button", { name: "Failed Company" });
    await user.click(failedRowButton);
    expect(screen.getByText("Browser timeout")).toBeInTheDocument();

    expect(within(cards).getByRole("button", { name: /Ошибки/ })).toHaveClass("bg-admin-primary");
  });
});
