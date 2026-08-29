import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReportView } from "../components/ReportView";
import type { CrawlReport } from "../types";

const report: CrawlReport = {
  schema_version: "2.0",
  run_id: "run-tabs",
  started_at: "2026-08-14T10:00:00Z",
  finished_at: "2026-08-14T10:01:00Z",
  stats: {
    total_companies: 6,
    success: 1,
    no_jobs: 1,
    unsupported: 1,
    unverified: 1,
    blocked: 1,
    failed: 1,
    skipped: 0,
    jobs_found: 1,
    duplicates_removed: 0,
  },
  companies: [
    {
      company_id: "empty-company",
      company: "Empty Company",
      website_url: "https://empty.example",
      careers_url: "https://empty.example/jobs",
      status: "no_jobs",
      adapter: "html",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 500,
      error: null,
      warnings: [],
    },
    {
      company_id: "unsupported-company",
      company: "Unsupported Company",
      website_url: "https://unsupported.example",
      careers_url: "https://unsupported.example/jobs",
      status: "unsupported",
      adapter: "html",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 700,
      error: "Vacancies are visible, but the current parser could not extract them",
      warnings: ["Visible job listings were found, but the parser extracted none"],
    },
    {
      company_id: "unverified-company",
      company: "Unverified Company",
      website_url: "https://unverified.example",
      careers_url: null,
      status: "unverified",
      adapter: "auto",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 600,
      error: "Vacancy extraction could not be verified",
      warnings: ["Careers page was not found on the company website"],
    },
    {
      company_id: "blocked-company",
      company: "Blocked Company",
      website_url: "https://blocked.example",
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
      website_url: "https://failed.example",
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
    { company_id: "unsupported-company", company: "Unsupported Company", status: "unsupported", message: "Vacancies are visible, but the current parser could not extract them" },
    { company_id: "unverified-company", company: "Unverified Company", status: "unverified", message: "Vacancy extraction could not be verified" },
    { company_id: "blocked-company", company: "Blocked Company", status: "blocked", message: "Blocked by robots.txt" },
    { company_id: "failed-company", company: "Failed Company", status: "failed", message: "Browser timeout" },
  ],
  jobs: [],
};

describe("Report status tabs", () => {
  it("reorders cards, highlights the active tab and expands issue details", async () => {
    const user = userEvent.setup();
    const retryProblems = vi.fn();
    render(<ReportView onRetryProblems={retryProblems} report={report} />);

    const cards = screen.getByLabelText("Статистика поиска");
    expect(Array.from(cards.children).map((card) => card.textContent)).toEqual([
      "4Обработано",
      "1Вакансии",
      "1Нет вакансий",
      "1Не извлечено",
      "1Страница не найдена",
      "1Заблокировано",
      "1Ошибки",
    ]);
    expect(screen.queryByRole("button", { name: /Обработано/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Вакансии/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Нет вакансий/ }));
    expect(screen.getByText("Карьерная страница найдена — вакансий нет")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Empty Company" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Повторить проблемные/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Не извлечено/ }));
    expect(screen.getByText("Вакансии видны, но не извлечены")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unsupported Company" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Страница не найдена/ }));
    expect(screen.getByText("Карьерная страница не найдена или не проверена")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unverified Company" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Заблокировано/ }));
    expect(screen.getByRole("button", { name: /Заблокировано/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("Фильтры вакансий")).not.toBeInTheDocument();
    expect(screen.getByText("Заблокированные компании")).toBeInTheDocument();
    const robotsCategory = screen.getByRole("button", { name: /robots\.txt/ });
    expect(robotsCategory).toHaveTextContent("1");
    await user.click(robotsCategory);
    expect(robotsCategory).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Повторить проблемные (4)" }));
    expect(retryProblems).toHaveBeenCalledWith(["unsupported-company", "unverified-company", "blocked-company", "failed-company"]);
    expect(screen.getAllByRole("link", { name: "Открыть" })[0]).toHaveAttribute(
      "href",
      "https://blocked.example",
    );
    const blockedRowButton = screen.getByRole("button", { name: "Blocked Company" });
    expect(blockedRowButton).toHaveAttribute("aria-expanded", "false");

    await user.click(blockedRowButton);
    expect(blockedRowButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Blocked by robots.txt")).toBeInTheDocument();
    expect(screen.getByText("robots.txt disallows this URL")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Ошибки/ }));
    expect(screen.getByText("Компании с ошибками")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Открыть" })[0]).toHaveAttribute(
      "href",
      "https://failed.example",
    );
    const failedRowButton = screen.getByRole("button", { name: "Failed Company" });
    await user.click(failedRowButton);
    expect(screen.getByText("Browser timeout")).toBeInTheDocument();

    expect(within(cards).getByRole("button", { name: /Ошибки/ })).toHaveClass("bg-admin-primary");
  });
});
