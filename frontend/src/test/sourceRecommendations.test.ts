import { describe, expect, it } from "vitest";
import { buildSourceRecommendations } from "../lib/sourceRecommendations";
import type { CompanyDiagnostics } from "../types";

const company = {
  adapter: "html" as const,
  website_url: "https://acme.example/",
  configured_careers_url: "https://acme.example/careers",
};

function diagnostics(overrides: Partial<CompanyDiagnostics> = {}): CompanyDiagnostics {
  return {
    company_id: "acme",
    company: "Acme",
    configured_adapter: "html",
    latest_result: {
      company_id: "acme",
      company: "Acme",
      status: "unsupported",
      adapter: "workday",
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 15_000,
      error: "Timeout after HTTP 429 rate limit",
      warnings: [
        "Configured careers URL failed: HTTP 404 custom not-found",
        "Visible job listings were found, but the parser extracted none",
      ],
    },
    request_url: "https://acme.example/careers",
    response_url: "https://acme.example/",
    response_status: 200,
    response_headers: {},
    raw_preview: "<html />",
    raw_truncated: false,
    fetch_error: null,
    ...overrides,
  };
}

describe("source recommendations", () => {
  it("maps diagnostic evidence to all supported recommendations", () => {
    const recommendations = buildSourceRecommendations(company, diagnostics());

    expect(recommendations.map((item) => item.title)).toEqual([
      "Повторить после timeout/429",
      "Найти Careers URL заново",
      "Ссылка ведёт на homepage",
      "Попробовать Playwright",
      "Вернуть автоматический адаптер",
      "Обнаружен Workday",
    ]);
    expect(recommendations.map((item) => item.action).filter(Boolean)).toEqual([
      "retry",
      "rediscover",
      "set_browser",
      "set_auto",
      "set_auto",
    ]);
  });

  it("does not suggest changes for a successful generic source", () => {
    const clean = diagnostics({
      latest_result: {
        company_id: "acme",
        company: "Acme",
        status: "success",
        adapter: "html",
        candidates_found: 3,
        matching_jobs: 2,
        duration_ms: 800,
        error: null,
        warnings: [],
      },
      response_url: "https://acme.example/careers",
    });

    expect(buildSourceRecommendations({ ...company, adapter: "auto" }, clean)).toEqual([]);
  });
});
