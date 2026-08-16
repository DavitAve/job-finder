import type { ActiveRun, CompanyImportPreview, CompanyImportResult, CompanyMutationResult, CompanySummary, CrawlReport, JobChanges, ResumeList, ResumeMatches, RunSummary } from "../types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let message = `Ошибка API (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // The default message is useful when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  companies: () => request<CompanySummary[]>("/api/companies"),
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
  start: (options: { scope: "full" | "new" | "selected"; company_ids?: string[] } = { scope: "full" }) => request<ActiveRun>("/api/crawls", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options) }),
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
