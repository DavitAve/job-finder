import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CompanyIssuesTable } from "../components/CompanyIssuesTable";
import type { CompanyCrawlResult } from "../types";

const companies: CompanyCrawlResult[] = Array.from({ length: 32 }, (_, index) => ({
  company_id: `failed-${index}`,
  company: `Failed ${index}`,
  careers_url: `https://example.com/${index}`,
  status: "failed",
  adapter: "html",
  candidates_found: 0,
  matching_jobs: 0,
  duration_ms: 100,
  error: "Request failed",
  warnings: [],
}));

describe("CompanyIssuesTable", () => {
  it("shows the absolute item range on every page", async () => {
    const user = userEvent.setup();
    render(<CompanyIssuesTable companies={companies} errors={[]} status="failed" />);
    expect(screen.getByText("Показано 1–20 из 32")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Далее" }));
    expect(screen.getByText("Показано 21–32 из 32")).toBeInTheDocument();
  });
});
