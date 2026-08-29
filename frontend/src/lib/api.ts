import type { ActiveRun, AuthUser, CompanyDiagnostics, CompanyHistoryItem, CompanyImportPreview, CompanyImportResult, CompanyMutationResult, CompanySummary, CrawlReport, JobChanges, ResumeList, ResumeMatches, RunSummary } from "../types";
import { announceApiUnavailable } from "./events";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/json", ...init?.headers },
      ...init,
    });
  } catch (error) {
    announceApiUnavailable();
    throw error;
  }
  if (!response.ok) {
    let message = `Ошибка API (${response.status})`;
    let hasApiDetail = false;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
        hasApiDetail = true;
      }
    } catch {
      // The default message is useful when the response is not JSON.
    }
    if (response.status >= 500 && !hasApiDetail) announceApiUnavailable();
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<AuthUser>("/api/auth/me"),
  register: (values: { email: string; password: string; display_name: string }) => request<AuthUser>("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) }),
  login: (values: { email: string; password: string }) => request<AuthUser>("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  companies: () => request<CompanySummary[]>("/api/companies"),
  companyDiagnostics: (companyId: string) => request<CompanyDiagnostics>(`/api/companies/${encodeURIComponent(companyId)}/diagnostics`),
  companyHistory: (companyId: string) => request<CompanyHistoryItem[]>(`/api/companies/${encodeURIComponent(companyId)}/history?limit=5`),
  importCompanies: (file: File, options: { resetExisting: boolean; deduplicate: boolean }) => {
    const query = new URLSearchParams({
      filename: file.name,
      reset_existing: String(options.resetExisting),
      deduplicate: String(options.deduplicate),
    });
    return request<CompanyImportResult>(`/api/companies/import?${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: file,
    });
  },
  previewCompanies: (file: File, options: { resetExisting: boolean; deduplicate: boolean }) => {
    const query = new URLSearchParams({
      filename: file.name,
      reset_existing: String(options.resetExisting),
      deduplicate: String(options.deduplicate),
    });
    return request<CompanyImportPreview>(`/api/companies/import/preview?${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      body: file,
    });
  },
  updateCompany: (companyId: string, values: Record<string, unknown>) => request<CompanyMutationResult>(`/api/companies/${encodeURIComponent(companyId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) }),
  bulkCompanies: (companyIds: string[], action: "enable" | "disable" | "delete") => request<CompanyMutationResult>("/api/companies/bulk", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company_ids: companyIds, action }) }),
  decideCareers: (companyId: string, decision: "approve" | "reject", url: string) => request<CompanyMutationResult>(`/api/companies/${encodeURIComponent(companyId)}/careers-decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, url }) }),
  latest: () => request<CrawlReport>("/api/runs/latest"),
  history: () => request<RunSummary[]>("/api/runs/history?limit=3"),
  report: (runId: string) => request<CrawlReport>(`/api/runs/${encodeURIComponent(runId)}`),
  active: () => request<ActiveRun>("/api/crawls/status"),
  start: (options: { scope: "full" | "new" | "stale" | "selected"; company_ids?: string[] } = { scope: "full" }) => request<ActiveRun>("/api/crawls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options) }),
  stop: () => request<ActiveRun>("/api/crawls/stop", { method: "POST" }),
  jobChanges: () => request<JobChanges>("/api/jobs/changes"),
  resumes: () => request<ResumeList>("/api/resumes"),
  uploadResume: (file: File, language: "en" | "ru") => {
    const query = new URLSearchParams({ filename: file.name, language });
    return request<ResumeList>(`/api/resumes?${query}`, {
      method: "POST", headers: { "Content-Type": "application/pdf" }, body: file,
    });
  },
  activateResume: (resumeId: string) => request<ResumeList>(`/api/resumes/${encodeURIComponent(resumeId)}/activate`, { method: "PATCH" }),
  deleteResume: (resumeId: string) => request<ResumeList>(`/api/resumes/${encodeURIComponent(resumeId)}`, { method: "DELETE" }),
  resumeMatches: (runId?: string) => request<ResumeMatches>(`/api/resume-matches${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
};
