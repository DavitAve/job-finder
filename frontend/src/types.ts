export type WorkFormat = "remote" | "hybrid" | "onsite" | "unknown";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface Job {
  job_id: string;
  company: string;
  title: string;
  url: string;
  location: string | null;
  remote: boolean | null;
  work_format?: WorkFormat;
  seniority: string | null;
  technologies: string[];
  description: string;
  published_at: string | null;
  source: string;
  source_job_id?: string | null;
  found_at: string;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  lifecycle?: "new" | "active";
  match_reasons: string[];
}

export interface CrawlStats {
  total_companies: number;
  success: number;
  no_jobs: number;
  unsupported?: number;
  blocked: number;
  failed: number;
  unverified?: number;
  skipped: number;
  jobs_found: number;
  duplicates_removed: number;
}

export interface CrawlError {
  company_id: string;
  company: string;
  status: "blocked" | "failed" | "unsupported" | "unverified";
  message: string;
}

export type CompanyStatus = "success" | "no_jobs" | "unsupported" | "blocked" | "failed" | "unverified" | "skipped";

export interface CompanyCrawlResult {
  company_id: string;
  company: string;
  website_url?: string | null;
  careers_url?: string | null;
  resolved_careers_url?: string | null;
  careers_url_discovered?: boolean;
  status: CompanyStatus;
  adapter: string | null;
  candidates_found: number;
  matching_jobs: number;
  duration_ms: number;
  last_crawled_at?: string | null;
  error: string | null;
  warnings: string[];
}

export interface CompanySummary {
  id: string;
  name: string;
  website_url: string;
  careers_url: string | null;
  configured_careers_url: string | null;
  resolved_careers_url: string | null;
  careers_url_discovered: boolean;
  discovery_pending: boolean;
  type: string | null;
  locations: string | null;
  remote_compatibility: string | null;
  frontend_compatibility: string | null;
  adapter: "auto" | "html" | "browser";
  last_adapter: string | null;
  enabled: boolean;
  crawl_status: CompanyStatus | null;
  jobs_found: number;
  last_crawled_at?: string | null;
  refresh_due?: boolean;
}

export interface CompanyImportResult {
  uploaded: number;
  added: number;
  duplicates_skipped: number;
  total: number;
  replaced_existing: boolean;
  backup_file: string;
}

export interface CompanyImportPreview {
  uploaded: number;
  would_add: number;
  duplicates_found: number;
  current_total: number;
  total_after_import: number;
  replaced_existing: boolean;
  validation_errors: string[];
}

export interface CompanyMutationResult {
  changed: number;
  total: number;
  backup_file: string;
}

export interface CompanyDiagnostics {
  company_id: string;
  company: string;
  configured_adapter: string;
  latest_result: CompanyCrawlResult | null;
  request_url: string;
  response_url: string | null;
  response_status: number | null;
  response_headers: Record<string, string>;
  raw_preview: string | null;
  raw_truncated: boolean;
  fetch_error: string | null;
}

export interface CompanyHistoryItem {
  run_id: string;
  checked_at: string;
  status: CompanyStatus;
  careers_url: string | null;
  adapter: string | null;
  jobs_found: number;
  error: string | null;
  duration_ms: number;
}

export interface JobChanges {
  new_jobs: Job[];
  closed_jobs: Job[];
}

export interface ResumeSummary {
  id: string;
  filename: string;
  language: "en" | "ru";
  created_at: string;
  size_bytes: number;
  page_count: number;
  skills: string[];
  active: boolean;
}

export interface ResumeList {
  resumes: ResumeSummary[];
  active_id: string | null;
  limit: number;
}

export interface ResumeMatch {
  job_id: string;
  score: number;
  matched_skills: string[];
  vacancy_skills: string[];
  reasons: string[];
}

export interface ResumeMatches {
  active_resume_id: string | null;
  matches: ResumeMatch[];
}

export interface CrawlReport {
  schema_version: string;
  scope?: "full" | "new" | "stale" | "selected";
  processed_company_ids?: string[];
  run_id: string;
  started_at: string;
  finished_at: string;
  stats: CrawlStats;
  companies?: CompanyCrawlResult[];
  errors: CrawlError[];
  jobs: Job[];
}

export interface RunSummary {
  run_id: string;
  started_at: string;
  finished_at: string;
  stats: CrawlStats;
}

export type RunStatus = "idle" | "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ActiveRun {
  run_id: string | null;
  state: RunStatus;
  started_at?: string | null;
  finished_at?: string | null;
  processed: number;
  total: number;
  jobs_found: number;
  scope?: "full" | "new" | "stale" | "selected";
  success?: number;
  no_jobs?: number;
  unsupported?: number;
  blocked?: number;
  failed?: number;
  unverified?: number;
  skipped?: number;
  last_company?: string | null;
  error?: string | null;
  message?: string | null;
}
