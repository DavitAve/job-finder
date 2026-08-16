import type { Job, WorkFormat } from "../types";

export interface JobFilters {
  title: string;
  stacks: string[];
  excludedCompanies: string[];
  location: "all" | "armenia";
  format: "all" | WorkFormat;
  onlyNew?: boolean;
  resumeMatch?: boolean;
}

const armenianLocations = /\b(armenia|yerevan|gyumri|vanadzor)\b|հայաստան|երևան/i;

export function jobFormat(job: Job): WorkFormat {
  if (job.work_format) return job.work_format;
  if (job.remote === true) return "remote";
  return "unknown";
}

export function filterJobs(jobs: Job[], filters: JobFilters, newJobIds?: ReadonlySet<string>): Job[] {
  const title = filters.title.trim().toLocaleLowerCase();
  const excludedCompanies = new Set(filters.excludedCompanies.map((company) => company.toLocaleLowerCase()));
  return jobs.filter((job) => {
    if (filters.onlyNew && !(newJobIds?.has(job.job_id) || job.lifecycle === "new")) return false;
    if (title && !job.title.toLocaleLowerCase().includes(title)) return false;
    if (filters.stacks.length && !filters.stacks.some((stack) => job.technologies.includes(stack))) return false;
    if (filters.location === "armenia" && !armenianLocations.test(job.location ?? "")) return false;
    if (filters.format !== "all" && jobFormat(job) !== filters.format) return false;
    if (excludedCompanies.has(job.company.toLocaleLowerCase())) return false;
    return true;
  });
}

export function availableCompanies(jobs: Job[]): string[] {
  return [...new Set(jobs.map((job) => job.company))].sort((a, b) => a.localeCompare(b));
}

export function availableStacks(jobs: Job[]): string[] {
  return [...new Set(jobs.flatMap((job) => job.technologies))].sort((a, b) => a.localeCompare(b));
}
