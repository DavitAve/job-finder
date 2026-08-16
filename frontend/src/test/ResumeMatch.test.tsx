import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ReportView } from "../components/ReportView";
import type { CrawlReport, Job } from "../types";

const job = (job_id: string, title: string): Job => ({ job_id, company: "Acme", title, url: `https://example.com/${job_id}`, location: null, remote: null, seniority: null, technologies: [], description: "", published_at: null, source: "test", found_at: "2026-08-16T10:00:00Z", match_reasons: [] });
const report: CrawlReport = { schema_version: "2.0", run_id: "run", started_at: "2026-08-16T10:00:00Z", finished_at: "2026-08-16T10:01:00Z", stats: { total_companies: 1, success: 1, no_jobs: 0, blocked: 0, failed: 0, skipped: 0, jobs_found: 2, duplicates_removed: 0 }, companies: [], errors: [], jobs: [job("low", "Angular Developer"), job("high", "React Developer")] };

describe("resume matching", () => {
  it("filters weak matches and sorts by active resume score", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report} resumeMatches={{ active_resume_id: "resume", matches: [
      { job_id: "low", score: 20, matched_skills: [], vacancy_skills: ["Angular"], reasons: [] },
      { job_id: "high", score: 85, matched_skills: ["React"], vacancy_skills: ["React"], reasons: ["Совпавшие навыки: React"] },
    ] }} />);

    await user.click(screen.getByRole("checkbox", { name: "Матч с активным резюме" }));
    const table = screen.getByRole("table");
    expect(within(table).getByText("React Developer")).toBeInTheDocument();
    expect(within(table).queryByText("Angular Developer")).not.toBeInTheDocument();
    expect(within(table).getByText("85%")).toHaveAttribute("title", "Совпавшие навыки: React");
  });
});
