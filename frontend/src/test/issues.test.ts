import { describe, expect, it } from "vitest";
import { classifyIssue, collectIssues, problemCompanyIds } from "../lib/issues";
import type { CompanyCrawlResult, CrawlReport } from "../types";

function issue(error: string, warnings: string[] = []): CompanyCrawlResult {
  return {
    company_id: error,
    company: error,
    status: "failed",
    adapter: null,
    candidates_found: 0,
    matching_jobs: 0,
    duration_ms: 0,
    error,
    warnings,
  };
}

describe("error analysis", () => {
  it.each([
    ["HTTP 403 for URL", "http_access"],
    ["HTTP 429 rate limit", "http_access"],
    ["Company timeout after 60s", "timeout"],
    ["getaddrinfo failed", "dns_tls"],
    ["SSL certificate has expired", "dns_tls"],
    ["robots.txt disallows URL", "robots"],
    ["CAPTCHA challenge detected", "captcha"],
    ["HTTP 404 Not Found", "invalid_url"],
    ["greenhouse adapter failed", "unsupported_ats"],
    ["Playwright browser render failed", "playwright"],
    ["Unexpected parser error", "other"],
  ] as const)("classifies %s", (message, category) => {
    expect(classifyIssue(issue(message), [])).toBe(category);
  });

  it("returns unique failed, blocked and unverified company ids", () => {
    const report = {
      companies: [
        { ...issue("failed"), company_id: "failed", status: "failed" },
        { ...issue("blocked"), company_id: "blocked", status: "blocked" },
        { ...issue("manual"), company_id: "manual", status: "unverified" },
        { ...issue("empty"), company_id: "empty", status: "no_jobs" },
        {
          ...issue("legacy", ["greenhouse adapter failed: HTTP 404"]),
          company_id: "legacy",
          status: "no_jobs",
        },
      ],
      errors: [
        { company_id: "failed", company: "Failed", status: "failed", message: "timeout" },
      ],
    } as CrawlReport;

    expect(problemCompanyIds(report)).toEqual(["failed", "blocked", "manual", "legacy"]);
    const errors = collectIssues(report.companies ?? [], report.errors, ["failed", "unverified"]);
    expect(errors.find((item) => item.company_id === "legacy")?.status).toBe("unverified");
  });
});
