import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { JobsTable } from "../components/JobsTable";
import type { Job } from "../types";

const jobs: Job[] = Array.from({ length: 12 }, (_, index) => ({ job_id: String(index), company: `Company ${index}`, title: `Frontend Developer ${index}`, url: `https://example.com/${index}`, location: "Yerevan", remote: true, seniority: null, technologies: ["React"], description: "", published_at: null, source: "test", found_at: "2026-08-14T00:00:00Z", match_reasons: [] }));

describe("JobsTable", () => {
  it("paginates jobs", async () => {
    const user = userEvent.setup();
    render(<JobsTable jobs={jobs} pageSize={10} />);
    expect(screen.getByText("Показано 1–10 из 12")).toBeInTheDocument();
    expect(screen.getByText("Frontend Developer 0")).toBeInTheDocument();
    expect(screen.queryByText("Frontend Developer 11")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Далее" }));
    expect(screen.getByText("Frontend Developer 11")).toBeInTheDocument();
    expect(screen.getByText("Показано 11–12 из 12")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });
});
