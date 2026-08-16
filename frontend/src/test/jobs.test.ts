import { describe, expect, it } from "vitest";
import { filterJobs, jobFormat } from "../lib/jobs";
import type { Job } from "../types";

const base: Job = { job_id: "1", company: "Acme", title: "Senior React Developer", url: "https://example.com/1", location: "Yerevan, Armenia", remote: false, seniority: "senior", technologies: ["React", "TypeScript"], description: "", published_at: null, source: "test", found_at: "2026-08-14T00:00:00Z", match_reasons: [] };

describe("job filters", () => {
  it("filters by title, stack OR logic and Armenia", () => {
    const result = filterJobs([base, { ...base, job_id: "2", title: "Vue Developer", location: "Berlin" }], { title: "react", stacks: ["TypeScript", "Vue"], excludedCompanies: [], location: "armenia", format: "all" });
    expect(result).toEqual([base]);
  });

  it.each(["Armenia", "Yerevan", "Երևան"])("recognizes Armenia location variant %s", (location) => {
    const job = { ...base, location };
    expect(filterJobs([job], { title: "", stacks: [], excludedCompanies: [], location: "armenia", format: "all" })).toEqual([job]);
  });

  it.each(["remote", "hybrid", "onsite", "unknown"] as const)("filters explicit %s work format", (workFormat) => {
    const job = { ...base, work_format: workFormat };
    expect(filterJobs([job], { title: "", stacks: [], excludedCompanies: [], location: "all", format: workFormat })).toEqual([job]);
  });

  it("does not guess onsite when remote is false", () => expect(jobFormat(base)).toBe("unknown"));
  it("uses the explicit normalized work format", () => expect(jobFormat({ ...base, work_format: "hybrid" })).toBe("hybrid"));
  it("excludes selected companies", () => {
    const other = { ...base, job_id: "2", company: "Other" };
    expect(filterJobs([base, other], { title: "", stacks: [], excludedCompanies: ["Acme"], location: "all", format: "all" })).toEqual([other]);
  });
  it("shows only jobs marked as new", () => {
    const other = { ...base, job_id: "2", title: "Vue Developer" };
    expect(filterJobs([base, other], { title: "", stacks: [], excludedCompanies: [], location: "all", format: "all", onlyNew: true }, new Set(["2"]))).toEqual([other]);
  });
});
