import type { CompanyDiagnostics, CompanySummary } from "../types";

export type RecommendationAction = "set_browser" | "set_auto" | "rediscover" | "retry";

export interface SourceRecommendation {
  id: string;
  title: string;
  message: string;
  tone: "info" | "warning" | "error";
  action?: RecommendationAction;
  actionLabel?: string;
}

const problematicStatuses = new Set(["blocked", "failed", "unsupported", "unverified"]);
const atsPattern = /\b(workday|greenhouse|lever)\b/i;

export function buildSourceRecommendations(
  company: Pick<CompanySummary, "adapter" | "website_url" | "configured_careers_url">,
  diagnostics: CompanyDiagnostics | undefined,
): SourceRecommendation[] {
  if (!diagnostics) return [];
  const result = diagnostics.latest_result;
  const evidence = [result?.error, ...(result?.warnings ?? []), diagnostics.fetch_error]
    .filter(Boolean)
    .join(" \n");
  const recommendations: SourceRecommendation[] = [];
  const problematic = Boolean(result && problematicStatuses.has(result.status));
  const ats = `${result?.adapter ?? ""} ${evidence}`.match(atsPattern)?.[1];

  if (/timeout|timed out|http 429|rate limit|too many requests/i.test(evidence)) {
    recommendations.push({
      id: "retry-transient",
      title: "Повторить после timeout/429",
      message: "Ошибка выглядит временной. Повторная проверка может завершиться успешно после освобождения лимита или восстановления сайта.",
      tone: "warning",
      action: "retry",
      actionLabel: "Повторить проверку",
    });
  }

  if (/careers page was not found|custom not-found|custom 404|\bhttp 404\b|configured careers url failed.*404/i.test(evidence)) {
    recommendations.push({
      id: "rediscover-careers",
      title: "Найти Careers URL заново",
      message: "Настроенная карьерная ссылка не найдена. Можно очистить её и разрешить crawler повторно выполнить discovery с основного сайта.",
      tone: "error",
      action: "rediscover",
      actionLabel: "Очистить URL",
    });
  }

  if (isHomepageRedirect(company, diagnostics) || /homepage redirect|redirected to (?:the )?homepage/i.test(evidence)) {
    recommendations.push({
      id: "homepage-redirect",
      title: "Ссылка ведёт на homepage",
      message: "Карьерная ссылка перенаправляет на главную страницу. Проверьте URL вручную или запустите повторный поиск Careers URL.",
      tone: "warning",
    });
  }

  if (
    company.adapter !== "browser" &&
    (/visible job listings.*parser extracted none|enable javascript|javascript.*required|browser fallback|\bhttp 403\b/i.test(evidence) || result?.status === "unsupported")
  ) {
    recommendations.push({
      id: "try-playwright",
      title: "Попробовать Playwright",
      message: "Страница выглядит динамической или вакансии видны, но HTML-парсер их не извлёк.",
      tone: "info",
      action: "set_browser",
      actionLabel: "Выбрать Playwright",
    });
  }

  if (company.adapter !== "auto" && problematic) {
    recommendations.push({
      id: "return-auto",
      title: "Вернуть автоматический адаптер",
      message: "Принудительно выбранный адаптер не дал стабильного результата. Автоматический режим сможет попробовать ATS, JSON-LD, HTML и browser fallback.",
      tone: "info",
      action: "set_auto",
      actionLabel: "Вернуть Auto",
    });
  }

  if (ats) {
    const label = ats.charAt(0).toUpperCase() + ats.slice(1).toLowerCase();
    recommendations.push({
      id: `ats-${ats.toLowerCase()}`,
      title: `Обнаружен ${label}`,
      message: `Последний лог содержит признаки ATS ${label}. Автоматический режим обычно является оптимальным для этого источника.`,
      tone: "info",
      ...(company.adapter !== "auto" ? { action: "set_auto" as const, actionLabel: "Использовать Auto" } : {}),
    });
  }

  return recommendations;
}

function isHomepageRedirect(
  company: Pick<CompanySummary, "website_url" | "configured_careers_url">,
  diagnostics: CompanyDiagnostics,
) {
  if (!company.configured_careers_url || !diagnostics.response_url) return false;
  try {
    const configured = new URL(company.configured_careers_url);
    const website = new URL(company.website_url);
    const response = new URL(diagnostics.response_url);
    const configuredHasPath = configured.pathname.replace(/\/+$/, "") !== "";
    const responseIsHomepage = response.pathname.replace(/\/+$/, "") === "";
    return configuredHasPath && responseIsHomepage && response.host === website.host;
  } catch {
    return false;
  }
}
