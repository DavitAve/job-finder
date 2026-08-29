import type { CompanyCrawlResult, CompanyStatus, CrawlError, CrawlReport } from "../types";

export type IssueStatus = Extract<CompanyStatus, "no_jobs" | "unsupported" | "blocked" | "failed" | "unverified">;
export type ErrorCategory =
  | "http_access"
  | "timeout"
  | "dns_tls"
  | "robots"
  | "captcha"
  | "invalid_url"
  | "unsupported_ats"
  | "parser"
  | "playwright"
  | "other";

export const ERROR_CATEGORIES: ReadonlyArray<{ id: ErrorCategory; label: string }> = [
  { id: "http_access", label: "HTTP 403 / 429" },
  { id: "timeout", label: "Timeout" },
  { id: "dns_tls", label: "DNS / TLS" },
  { id: "robots", label: "robots.txt" },
  { id: "captcha", label: "CAPTCHA" },
  { id: "invalid_url", label: "Неверный URL" },
  { id: "unsupported_ats", label: "Неподдерживаемый ATS" },
  { id: "parser", label: "Парсер не извлёк" },
  { id: "playwright", label: "Playwright" },
  { id: "other", label: "Прочее" },
];

export function issueMessage(item: CompanyCrawlResult, errors: CrawlError[]): string {
  if (item.status === "no_jobs" && !item.error) {
    return "Карьерная страница найдена и обработана: открытых вакансий сейчас нет.";
  }
  return (
    item.error ??
    errors.find((error) => error.company_id === item.company_id && error.status === item.status)?.message ??
    "Подробности не были предоставлены источником."
  );
}

function diagnosticText(item: CompanyCrawlResult, errors: CrawlError[]): string {
  return [issueMessage(item, errors), ...item.warnings].join("\n").toLowerCase();
}

export function classifyIssue(item: CompanyCrawlResult, errors: CrawlError[]): ErrorCategory {
  const text = diagnosticText(item, errors);
  if (item.status === "unsupported" || /visible job listings.*parser extracted none/.test(text)) return "parser";
  if (/robots?\.txt|robotsdenied|disallows/.test(text)) return "robots";
  if (/captcha|recaptcha|hcaptcha|verify (?:that )?you are human|security check|challenge page|attention required/.test(text)) return "captcha";
  if (/\bhttp\s*(?:403|429)\b|rate limit|too many requests|access denied|forbidden/.test(text)) return "http_access";
  if (/(?:greenhouse|lever|workday|ashby|smartrecruiters|recruitee|staff\.am).{0,40}adapter failed|unsupported ats|unknown ats/.test(text)) return "unsupported_ats";
  if (/playwright|browser (?:render|pagination).*(?:failed|error)|browser unavailable|chromium/.test(text)) return "playwright";
  if (/timeout|timed out|time out/.test(text)) return "timeout";
  if (/\bdns\b|getaddrinfo|name or service not known|nodename nor servname|ssl|tls|certificate|handshake|decrypt(?:ion)?_failed/.test(text)) return "dns_tls";
  if (/\bhttp\s*(?:404|410)\b|not[- ]found|not found|invalid (?:url|uri)|url_parsing|unsupported protocol|missing host/.test(text)) return "invalid_url";
  return "other";
}

export function collectIssues(
  companies: CompanyCrawlResult[],
  errors: CrawlError[],
  statuses: readonly IssueStatus[],
): CompanyCrawlResult[] {
  const allowed = new Set<CompanyStatus>(statuses);
  const includeLegacyUnverified = allowed.has("unverified");
  const issues = companies.flatMap((company) => {
    if (allowed.has(company.status)) return [company];
    if (includeLegacyUnverified && isLegacyUnverified(company)) {
      return [{
        ...company,
        status: "unverified" as const,
        error: company.error ?? "Vacancy extraction could not be verified; see warnings",
      }];
    }
    return [];
  });
  const known = new Set(issues.map((company) => company.company_id));
  for (const error of errors) {
    if (!allowed.has(error.status) || known.has(error.company_id)) continue;
    issues.push({
      company_id: error.company_id,
      company: error.company,
      careers_url: null,
      status: error.status,
      adapter: null,
      candidates_found: 0,
      matching_jobs: 0,
      duration_ms: 0,
      error: error.message,
      warnings: [],
    });
  }
  return issues;
}

export function problemCompanyIds(report: CrawlReport): string[] {
  const statuses = new Set<CompanyStatus>(["blocked", "failed", "unsupported", "unverified"]);
  const ids = new Set(
    (report.companies ?? [])
      .filter(
        (company) =>
          statuses.has(company.status) ||
          isLegacyUnverified(company),
      )
      .map((company) => company.company_id),
  );
  for (const error of report.errors) {
    if (statuses.has(error.status)) ids.add(error.company_id);
  }
  return [...ids];
}

function isLegacyUnverified(company: CompanyCrawlResult): boolean {
  return company.status === "no_jobs" && company.warnings.some((warning) =>
    /(?:\b(?:greenhouse|lever|workday|ashby|smartrecruiters|recruitee|workable|staff\.am) adapter failed|browser (?:render|pagination) failed|playwright (?:unavailable|page pool busy)|pagination page failed|careers page (?:could not be verified|was not found))/i.test(
      warning,
    ),
  );
}
