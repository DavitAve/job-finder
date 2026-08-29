import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useToast } from "../components/Toast";
import { api } from "../lib/api";

export function useCrawler() {
  const client = useQueryClient();
  const { showToast } = useToast();
  const invalidatedCompletedRuns = useRef(new Set<string>());
  const previousState = useRef<string | undefined>(undefined);
  const active = useQuery({
    queryKey: ["active-run"],
    queryFn: api.active,
    refetchInterval: (query) => query.state.data?.state === "running" || query.state.data?.state === "queued" ? 2000 : false,
  });
  useEffect(() => {
    const status = active.data;
    if (status?.state === "completed" && status.run_id && !invalidatedCompletedRuns.current.has(status.run_id)) {
      invalidatedCompletedRuns.current.add(status.run_id);
      void client.invalidateQueries({ queryKey: ["latest-run"] });
      void client.invalidateQueries({ queryKey: ["history"] });
      void client.invalidateQueries({ queryKey: ["companies"] });
      void client.invalidateQueries({ queryKey: ["job-changes"] });
      void client.invalidateQueries({ queryKey: ["resume-matches"] });
    }
    if (
      status?.state === "completed" &&
      (previousState.current === "running" || previousState.current === "queued")
    ) {
      showToast({
        title: "Поиск завершён",
        message: `Найдено вакансий: ${status.jobs_found}.`,
        tone: "success",
        dedupeKey: `crawl-completed:${status.run_id ?? "unknown"}`,
      });
    }
    previousState.current = status?.state;
  }, [active.data, client, showToast]);
  const start = useMutation({ mutationFn: api.start, onSuccess: (status, options) => {
    client.setQueryData(["active-run"], status);
    void client.invalidateQueries({ queryKey: ["active-run"] });
    if (status.state === "running" || status.state === "queued") {
      showToast({
        title: "Поиск запущен",
        message: `Компаний в очереди: ${status.total}.`,
        tone: "info",
        dedupeKey: `crawl-started:${status.run_id ?? "unknown"}`,
      });
    } else if (options?.scope === "new" && status.state === "completed" && status.total === 0) {
      showToast({
        title: "Новых компаний нет",
        message: "Все компании из текущей базы уже были обработаны.",
        tone: "warning",
        dedupeKey: "no-new-companies",
      });
    }
  } });
  const stop = useMutation({ mutationFn: api.stop, onSuccess: (status) => {
    client.setQueryData(["active-run"], status);
    void client.invalidateQueries({ queryKey: ["active-run"] });
    showToast({
      title: "Поиск остановлен",
      message: "Предыдущий сохранённый результат не изменён.",
      tone: "warning",
      dedupeKey: `crawl-stopped:${status.run_id ?? "unknown"}`,
    });
  } });
  const isRunning = active.data?.state === "running" || active.data?.state === "queued" || start.isPending;
  return { active, start, stop, isRunning };
}
